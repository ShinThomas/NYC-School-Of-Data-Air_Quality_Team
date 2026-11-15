"""Build projects.csv from a batch.py results folder: one row per PDF that was read.

Usage:
    python projects.py path/to/results

No API calls; it only reads the per-PDF JSON files that batch.py wrote.
"""

import csv
import json
import re
import sys
from pathlib import Path

CEQR_NAME = re.compile(r"^(\d{2})([A-Z]{3})\d+([A-Z])")
BOROUGHS = {"M": "Manhattan", "K": "Brooklyn", "Q": "Queens", "X": "Bronx", "R": "Staten Island"}
E_DESIGNATION = re.compile(r"E-designation|\(E\) designation|E designation|\(E\)", re.IGNORECASE)

FIELDS = [
    "ceqr_number", "fiscal_year", "agency", "detail_level", "significant_adverse_impact",
    "e_designation", "n_concentrations", "project_name", "address", "borough", "lead_agency",
    "document_type", "document_date", "pollutants", "emission_sources", "mitigation_measures",
    "impact_conclusion_quote", "summary", "total_pages", "file",
]

# Most useful first: full analyses, then qualitative reviews, then short notices.
DETAIL_ORDER = {"full analysis": 0, "screened / qualitative": 1, "short notice": 2}


def detail_level(result: dict) -> str:
    """How much air quality content the document has."""
    if result.get("concentrations"):
        return "full analysis"  # reports modeled or measured concentrations
    if int(result.get("total_pages") or 0) <= 3:
        return "short notice"  # cover letter, notice or determination
    return "screened / qualitative"  # discusses air quality without numbers


def build_row(record: dict) -> dict:
    result = record["result"]
    file = record["file"]
    match = CEQR_NAME.match(Path(file).name)
    year = agency = borough_code = None
    if match:
        yy = int(match.group(1))
        year = (1900 if yy >= 80 else 2000) + yy
        agency, borough_code = match.group(2), match.group(3)

    text = " ".join(
        [result.get("summary") or "", result.get("impact_conclusion_quote") or ""]
        + result.get("mitigation_measures", [])
    )
    return {
        "ceqr_number": Path(file).stem,
        "fiscal_year": year,
        "agency": agency,
        "detail_level": detail_level(result),
        "significant_adverse_impact": result.get("significant_adverse_impact"),
        "e_designation": "yes" if E_DESIGNATION.search(text) else "",
        "n_concentrations": len(result.get("concentrations", [])),
        "project_name": result.get("project_name"),
        "address": result.get("address"),
        # Fall back to the borough letter in the CEQR number.
        "borough": result.get("borough") or BOROUGHS.get(borough_code),
        "lead_agency": result.get("lead_agency"),
        "document_type": result.get("document_type"),
        "document_date": result.get("document_date"),
        "pollutants": "; ".join(result.get("pollutants", [])),
        "emission_sources": "; ".join(result.get("emission_sources", [])),
        "mitigation_measures": "; ".join(result.get("mitigation_measures", [])),
        "impact_conclusion_quote": result.get("impact_conclusion_quote"),
        "summary": result.get("summary"),
        "total_pages": result.get("total_pages"),
        "file": file,
    }


def build_projects_csv(out_dir: Path) -> tuple[Path, list[dict]]:
    rows = []
    for path in sorted(out_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") == "ok" and record.get("result"):
            rows.append(build_row(record))
    rows.sort(key=lambda r: (DETAIL_ORDER[r["detail_level"]], -(r["fiscal_year"] or 0), r["ceqr_number"]))

    csv_path = out_dir / "projects.csv"
    # utf-8-sig so Excel shows µ and other characters correctly.
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path, rows


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python projects.py path/to/results")
    csv_path, rows = build_projects_csv(Path(sys.argv[1]))
    counts = {}
    for r in rows:
        counts[r["detail_level"]] = counts.get(r["detail_level"], 0) + 1
    print(f"Wrote {len(rows)} projects to {csv_path}")
    for level in DETAIL_ORDER:
        print(f"  {level}: {counts.get(level, 0)}")
    print(f"  significant impact (yes): {sum(r['significant_adverse_impact'] == 'yes' for r in rows)}")
    print(f"  E-designation mentioned: {sum(r['e_designation'] == 'yes' for r in rows)}")
