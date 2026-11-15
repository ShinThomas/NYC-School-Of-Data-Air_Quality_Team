"""Extract structured air quality info from a text-based PDF using Gemini.

Usage:
    python wrapper.py path/to/document.pdf
    python wrapper.py https://example.com/document.pdf

Needs GEMINI_API_KEY in a .env file next to this script (see .env.example).
"""

import io
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter

load_dotenv(Path(__file__).parent / ".env")

MODEL = "gemini-3.8-flash"  # free tier; change here if Google retires it

# Minimum characters of embedded text before we treat the PDF as a scan.
MIN_TEXT_CHARS = 200

# PDFs larger than this are uploaded through Gemini's File API instead of
# being sent inside the request, which has a size limit.
INLINE_LIMIT_BYTES = 20 * 1024 * 1024

DOWNLOAD_TIMEOUT_SECONDS = 120

# Give up on a Gemini request after this long so a hung call cannot stall a batch.
REQUEST_TIMEOUT_SECONDS = 300

# Paid-tier prices in USD per million tokens, used only to estimate cost.
# Check https://ai.google.dev/gemini-api/docs/pricing; reported to double on 2027-01-01.
INPUT_PRICE_PER_M = 0.75
OUTPUT_PRICE_PER_M = 3.75  # output includes the model's thinking tokens

# Page selection for long PDFs (see select_pages).
SELECT_PAGES_ABOVE = 15  # PDFs with this many pages or fewer are sent whole
FIRST_PAGES = 3  # always keep these, for project name, address, agency, date
MAX_MATCHED_PAGES = 40
AIR_QUALITY_TERMS = re.compile(
    r"air quality|µg/m|μg/m|ug/m3|micrograms per cubic|\bppm\b|PM ?2\.5|PM ?10|"
    r"nitrogen dioxide|\bNO ?2\b|carbon monoxide|sulfur dioxide|\bSO ?2\b|particulate|"
    r"NAAQS|de minimis|AERMOD|AERSCREEN|HVAC|boiler|stack|stationary source|mobile source|"
    r"E-designation|\(E\) designation|receptor|emission",
    re.IGNORECASE,
)
CONCENTRATION_UNITS = re.compile(r"µg/m|μg/m|ug/m3|micrograms per cubic|\bppm\b", re.IGNORECASE)
CONCLUSION_TERMS = re.compile(
    r"negative declaration|positive declaration|significant adverse|determination of significance",
    re.IGNORECASE,
)


class UnusablePDFError(ValueError):
    """The input is not a PDF, or is a scan with no embedded text."""


# PLACEHOLDER SCHEMA: confirm the real fields with the team lead.
# Every field is Optional so the model returns null instead of guessing.
class PollutantConcentration(BaseModel):
    pollutant: str = Field(description="Pollutant name, e.g. PM2.5, NO2")
    value: float = Field(description="Concentration as a number, without units")
    units: str = Field(description="Units of the value, e.g. µg/m³, ppm")
    scenario: Literal["existing", "no-action", "with-action", "not stated"] = Field(
        description="Which condition the value describes: existing conditions, the future No-Action condition "
        "(without the project), or the future With-Action condition (with the project)"
    )
    analysis_year: Optional[int] = Field(None, description="Year the value applies to, e.g. the build year 2030")
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
    "Keep background, project increment, and total values as separate entries. "
    "When a table has separate columns for existing, No-Action, and With-Action conditions, "
    "make one entry per column and set scenario and analysis_year for each."
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
        raise UnusablePDFError(f"{source} is not a PDF.")
    return data


def check_has_text(pdf_bytes: bytes, name: str) -> None:
    """Raise if the PDF looks like a scan with no embedded text."""
    # Look through the whole PDF (some have scanned cover pages before real text),
    # stopping as soon as there is enough text.
    reader = PdfReader(io.BytesIO(pdf_bytes))
    chars = 0
    for page in reader.pages:
        chars += len(page_text(page).strip())
        if chars >= MIN_TEXT_CHARS:
            return
    raise UnusablePDFError(f"{name} has little or no embedded text; it may be a scan.")


def page_text(page) -> str:
    """Text of one page, or "" if the page can't be parsed (e.g. a huge drawing)."""
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def select_pages(pdf_bytes: bytes) -> tuple[bytes, list[int] | None, int]:
    """For long PDFs, keep only the pages likely to matter, to save tokens.

    Returns (pdf_bytes_to_send, original page numbers kept or None if all, total pages).
    Keeps the first pages (project info), every page that mentions air quality or the
    review's conclusion, and the page after each match (tables often continue).
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    if total <= SELECT_PAGES_ABOVE:
        return pdf_bytes, None, total

    scores = {}
    has_concentrations = False
    for i, page in enumerate(reader.pages):
        text = page_text(page)
        score = len(AIR_QUALITY_TERMS.findall(text)) + 5 * len(CONCLUSION_TERMS.findall(text))
        if score:
            scores[i] = score
        if CONCENTRATION_UNITS.search(text):
            has_concentrations = True

    if has_concentrations:
        # Real air quality analysis: keep every matching page, plus the 2 pages after
        # each (tables often continue onto pages with only numbers).
        matched, after = list(scores), 2
    else:
        # Mostly form boilerplate: keep the highest-scoring pages, capped.
        matched, after = sorted(scores, key=scores.get, reverse=True)[:MAX_MATCHED_PAGES], 1
    keep = set(range(min(FIRST_PAGES, total)))
    for i in matched:
        keep.update(range(i, min(i + after, total - 1) + 1))
    keep = sorted(keep)

    writer = PdfWriter()
    for i in keep:
        writer.add_page(reader.pages[i])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), [i + 1 for i in keep], total


def extract_air_quality_info(source: str | Path, all_pages: bool = False) -> dict:
    """Send a PDF (local path or URL) to Gemini and return the extracted fields as a dict.

    By default, long PDFs are trimmed to their relevant pages (see select_pages);
    pass all_pages=True to send the whole document.
    """
    pdf_bytes = load_pdf(source)
    check_has_text(pdf_bytes, str(source))
    if all_pages:
        kept, total = None, len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    else:
        pdf_bytes, kept, total = select_pages(pdf_bytes)

    client = genai.Client(  # reads GEMINI_API_KEY from the environment
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000)
    )
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
    if kept:
        # The model numbered pages within the trimmed PDF; map back to the original.
        for conc in result["concentrations"]:
            page = conc.get("page")
            conc["page"] = kept[page - 1] if page and 1 <= page <= len(kept) else None
    result["source"] = str(source)
    result["total_pages"] = total
    result["pages_sent"] = len(kept) if kept else total

    usage = response.usage_metadata
    input_tokens = (usage.prompt_token_count or 0) if usage else 0
    output_tokens = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
    result["tokens"] = input_tokens + output_tokens
    result["cost_usd"] = round(
        (input_tokens * INPUT_PRICE_PER_M + output_tokens * OUTPUT_PRICE_PER_M) / 1_000_000, 5
    )
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python wrapper.py path/to/document.pdf  (or a URL)")
    print(json.dumps(extract_air_quality_info(sys.argv[1]), indent=2))
