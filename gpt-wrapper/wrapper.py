"""Extract structured air quality info from a text-based PDF using Gemini.

Usage:
    python wrapper.py path/to/document.pdf
    python wrapper.py https://example.com/document.pdf

Needs GEMINI_API_KEY in a .env file next to this script (see .env.example).
"""

import io
import json
import sys
import urllib.request
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader

load_dotenv(Path(__file__).parent / ".env")

MODEL = "gemini-3.8-flash"  # free tier; change here if Google retires it

# Minimum characters of embedded text before we treat the PDF as a scan.
MIN_TEXT_CHARS = 200

# PDFs larger than this are uploaded through Gemini's File API instead of
# being sent inside the request, which has a size limit.
INLINE_LIMIT_BYTES = 20 * 1024 * 1024

DOWNLOAD_TIMEOUT_SECONDS = 120


# PLACEHOLDER SCHEMA: confirm the real fields with the team lead.
# Every field is Optional so the model returns null instead of guessing.
class PollutantConcentration(BaseModel):
    pollutant: str = Field(description="Pollutant name, e.g. PM2.5, NO2")
    value: float = Field(description="Concentration as a number, without units")
    units: str = Field(description="Units of the value, e.g. µg/m³, ppm")
    value_type: Optional[str] = Field(
        None,
        description="What the number represents: background, project increment, or total (background + project)",
    )
    averaging_period: Optional[str] = Field(None, description="Averaging period, e.g. 1-hour, 24-hour, annual")
    location: Optional[str] = Field(None, description="Receptor or monitoring location the value applies to, if given")
    standard: Optional[float] = Field(None, description="Regulatory standard or threshold it is compared to, same units")
    exceeds_standard: Optional[bool] = Field(None, description="True only if the document says the value exceeds the standard")
    page: Optional[int] = Field(None, description="PDF page number where the value appears, for checking")


class AirQualityProject(BaseModel):
    document_type: Literal["EAS", "EIS", "other", "not stated"] = Field(
        description="EAS (Environmental Assessment Statement), EIS (Environmental Impact Statement), or other"
    )
    project_name: Optional[str] = Field(None, description="Official name of the project")
    address: Optional[str] = Field(None, description="Street address of the project site")
    borough: Optional[str] = Field(None, description="NYC borough, e.g. Brooklyn")
    lead_agency: Optional[str] = Field(None, description="Agency responsible for the review or permit")
    project_status: Optional[str] = Field(None, description="Status, e.g. proposed, under review, approved")
    document_date: Optional[str] = Field(None, description="Date of the document, YYYY-MM-DD")
    significant_adverse_impact: Literal["yes", "no", "not stated"] = Field(
        description="The document's own conclusion on whether the project has a significant adverse air quality impact"
    )
    impact_conclusion_quote: Optional[str] = Field(
        None, description="Short quote from the document stating its air quality impact conclusion"
    )
    pollutants: list[str] = Field(default_factory=list, description="Pollutants discussed, e.g. PM2.5, NO2")
    concentrations: list[PollutantConcentration] = Field(
        default_factory=list,
        description="Every pollutant concentration reported in the document's tables or text, one entry per value",
    )
    emission_sources: list[str] = Field(default_factory=list, description="Sources of emissions, e.g. boilers, traffic")
    mitigation_measures: list[str] = Field(default_factory=list, description="Measures proposed to reduce air impacts")
    summary: Optional[str] = Field(None, description="Two or three sentence summary of the air quality findings")


PROMPT = (
    "Extract the requested fields from this air quality document. "
    "Use only information stated in the document. "
    "If a field is not present, return null (or an empty list). "
    "For significant_adverse_impact, report the document's own conclusion, not your own judgment. "
    "For concentrations, copy numbers exactly as written; do not calculate, convert units, or round. "
    "Keep background, project increment, and total values as separate entries."
)


def load_pdf(source: str | Path) -> bytes:
    """Return the PDF's bytes from a local path or an http(s) URL."""
    source = str(source)
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "air-quality-pdf-extractor"})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            data = response.read()
    else:
        data = Path(source).read_bytes()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"{source} is not a PDF.")
    return data


def check_has_text(pdf_bytes: bytes, name: str) -> None:
    """Raise if the PDF looks like a scan with no embedded text."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "".join(page.extract_text() or "" for page in reader.pages[:5])
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise ValueError(f"{name} has little or no embedded text; it may be a scan.")


def extract_air_quality_info(source: str | Path) -> dict:
    """Send a PDF (local path or URL) to Gemini and return the extracted fields as a dict."""
    pdf_bytes = load_pdf(source)
    check_has_text(pdf_bytes, str(source))

    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    uploaded = None
    if len(pdf_bytes) > INLINE_LIMIT_BYTES:
        uploaded = client.files.upload(
            file=io.BytesIO(pdf_bytes),
            config=types.UploadFileConfig(mime_type="application/pdf"),
        )
        pdf_part = uploaded
    else:
        pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[pdf_part, PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AirQualityProject,
            ),
        )
    finally:
        if uploaded is not None:
            client.files.delete(name=uploaded.name)

    result = response.parsed.model_dump()
    result["source"] = str(source)
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python wrapper.py path/to/document.pdf  (or a URL)")
    print(json.dumps(extract_air_quality_info(sys.argv[1]), indent=2))
