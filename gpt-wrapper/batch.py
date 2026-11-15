"""Run the air quality wrapper on every PDF in a folder, one at a time.

Usage:
    python batch.py INPUT_FOLDER [--out results] [--delay 5] [--retry-errors]
                    [--min-year 2010] [--max-year 2027] [--agency DCP DEP] [--dry-run]

For each PDF it writes one JSON file to the output folder. Re-running the
same command skips PDFs that already finished, so you can stop it (Ctrl+C)
and pick up where it left off. After each run it rebuilds:
    summary.csv         one row per PDF: status, key fields, error message
    concentrations.csv  one row per extracted concentration value

File names start with the CEQR number, e.g. 22DCP188Q = fiscal year 2022,
Department of City Planning. --min-year, --max-year and --agency use that to
pick which PDFs to run. --dry-run counts text PDFs vs scans without calling
the API, so you can see how many Gemini calls a run will take.
"""

import argparse
import csv
import json
import logging
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from google.genai import errors

from projects import build_projects_csv

from wrapper import (
    PollutantConcentration,
    UnusablePDFError,
    check_has_text,
    extract_air_quality_info,
    load_pdf,
)

# Hide the PDF library's harmless font warnings ("fontTools is required...").
logging.getLogger("pypdf").setLevel(logging.ERROR)

RETRYABLE_CODES = {429, 500, 502, 503, 504}  # rate limits and server overload
RETRY_WAITS_SECONDS = [30, 60, 120]

SUMMARY_FIELDS = [
    "file", "status", "document_type", "project_name", "borough", "document_date",
    "significant_adverse_impact", "n_concentrations", "error", "seconds", "total_pages", "pages_sent", "tokens", "cost_usd",
    "processed_at",
]
CONCENTRATION_FIELDS = ["file", *PollutantConcentration.model_fields]

CEQR_NAME = re.compile(r"^(\d{2})([A-Z]{3})")


def parse_name(pdf: Path) -> tuple[int | None, str | None]:
    """Fiscal year and agency code from a CEQR-style file name, e.g. 22DCP188Q -> (2022, "DCP")."""
    match = CEQR_NAME.match(pdf.name.upper())
    if not match:
        return None, None
    yy = int(match.group(1))
    return (1900 + yy if yy >= 80 else 2000 + yy), match.group(2)


def in_scope(pdf: Path, min_year: int | None, max_year: int | None, agencies: set[str] | None) -> bool:
    if min_year is None and max_year is None and agencies is None:
        return True
    year, agency = parse_name(pdf)
    if year is None:
        return False  # name doesn't follow the CEQR pattern, so we can't tell
    if min_year is not None and year < min_year:
        return False
    if max_year is not None and year > max_year:
        return False
    return agencies is None or agency in agencies


def dry_run(pdfs: list[Path]) -> None:
    """Count text PDFs vs scans by year, without calling the API."""
    totals = Counter()
    by_year = {}
    start = time.time()
    for i, pdf in enumerate(pdfs, 1):
        try:
            check_has_text(load_pdf(pdf), pdf.name)
            kind = "text"
        except UnusablePDFError:
            kind = "scan"
        except Exception:
            kind = "unreadable"
        totals[kind] += 1
        year = parse_name(pdf)[0] or "unknown"
        by_year.setdefault(year, Counter())[kind] += 1
        if i % 100 == 0:
            print(f"  checked {i}/{len(pdfs)} ({time.time() - start:.0f}s)")

    print(f"\n{'year':>8} {'text':>6} {'scan':>6} {'unreadable':>11}")
    for year in sorted(by_year, key=str):
        c = by_year[year]
        print(f"{year:>8} {c['text']:>6} {c['scan']:>6} {c['unreadable']:>11}")
    print(f"\nTotal: {totals['text']} text PDFs (these need a Gemini call), "
          f"{totals['scan']} scans, {totals['unreadable']} unreadable.")


def result_path(pdf: Path, input_dir: Path, out_dir: Path) -> Path:
    """One JSON per PDF, named after its path inside the input folder."""
    relative = pdf.relative_to(input_dir).with_suffix("")
    return out_dir / ("__".join(relative.parts) + ".json")


def already_done(path: Path, retry_errors: bool, retry_skipped: bool = False) -> bool:
    if not path.exists():
        return False
    status = json.loads(path.read_text(encoding="utf-8")).get("status")
    if status == "ok":
        return True
    if status == "skipped":  # scan / not a PDF: won't change unless the check changes
        return not retry_skipped
    return not retry_errors


def newest_first(pdf: Path) -> tuple:
    """Sort key: newest fiscal year first; names without a year go last."""
    year = parse_name(pdf)[0]
    return (-(year or 0), pdf.name)


def process_one(pdf: Path, all_pages: bool = False) -> dict:
    """Run the wrapper on one PDF, retrying on rate limits and server overload."""
    for attempt, wait in enumerate([0, *RETRY_WAITS_SECONDS]):
        if wait:
            print(f"    {pdf.name}: busy, retrying in {wait}s (attempt {attempt + 1})")
            time.sleep(wait)
        try:
            return {"status": "ok", "result": extract_air_quality_info(pdf, all_pages=all_pages)}
        except UnusablePDFError as e:  # scan or not a PDF: retrying won't help
            return {"status": "skipped", "error": str(e)}
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES or attempt == len(RETRY_WAITS_SECONDS):
                return {"status": "error", "error": f"{e.code}: {e.message}"}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def run_one(pdf: Path, input_dir: Path, out_dir: Path, delay: float, all_pages: bool) -> dict:
    """Process one PDF, save its result file, and return the saved record."""
    started = time.time()
    outcome = process_one(pdf, all_pages)
    record = {
        "file": pdf.relative_to(input_dir).as_posix(),
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "seconds": round(time.time() - started),
        **outcome,
    }
    if outcome["status"] == "ok":
        for key in ("total_pages", "pages_sent", "tokens", "cost_usd"):
            record[key] = outcome["result"].get(key)
    write_json(result_path(pdf, input_dir, out_dir), record)
    time.sleep(delay)  # per-worker pause, to stay under rate limits
    return record


def write_json(path: Path, data: dict) -> None:
    """Write via a temp file so a crash never leaves a half-written result."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def build_csvs(out_dir: Path) -> dict:
    counts = {}
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8-sig") as s, \
         open(out_dir / "concentrations.csv", "w", newline="", encoding="utf-8-sig") as c:
        summary = csv.DictWriter(s, SUMMARY_FIELDS, extrasaction="ignore")
        concs = csv.DictWriter(c, CONCENTRATION_FIELDS, extrasaction="ignore")
        summary.writeheader()
        concs.writeheader()
        for path in sorted(out_dir.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            result = record.get("result") or {}
            counts[record["status"]] = counts.get(record["status"], 0) + 1
            summary.writerow({**record, **result, "n_concentrations": len(result.get("concentrations", []))})
            for conc in result.get("concentrations", []):
                concs.writerow({"file": record["file"], **conc})
    build_projects_csv(out_dir)
    return counts


def folder_cost(out_dir: Path) -> float:
    """Estimated cost of all results saved in the output folder so far."""
    return sum(json.loads(p.read_text(encoding="utf-8")).get("cost_usd") or 0 for p in out_dir.glob("*.json"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_dir", type=Path, help="Folder of PDFs (subfolders included)")
    parser.add_argument("--out", type=Path, default=Path("results"), help="Output folder (default: results)")
    parser.add_argument("--delay", type=float, default=5, help="Seconds to wait between PDFs (default: 5)")
    parser.add_argument("--retry-errors", action="store_true", help="Re-run PDFs that failed last time")
    parser.add_argument("--retry-skipped", action="store_true", help="Re-check PDFs skipped as scans last time")
    parser.add_argument("--min-year", type=int, help="Only PDFs from this fiscal year on, e.g. 2010")
    parser.add_argument("--max-year", type=int, help="Only PDFs up to this fiscal year, e.g. 2027")
    parser.add_argument("--agency", nargs="+", help="Only these agency codes, e.g. DCP DEP")
    parser.add_argument("--dry-run", action="store_true", help="Count text PDFs vs scans; no API calls")
    parser.add_argument("--workers", type=int, default=1, help="PDFs to process at the same time (default: 1)")
    parser.add_argument("--limit", type=int, help="Stop after this many PDFs, e.g. 10 for a test")
    parser.add_argument("--all-pages", action="store_true", help="Send whole PDFs instead of only relevant pages")
    parser.add_argument("--budget", type=float,
                        help="Stop once the estimated cost of everything in --out reaches this many dollars")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    agencies = {a.upper() for a in args.agency} if args.agency else None
    all_pdfs = sorted((p for p in input_dir.rglob("*") if p.suffix.lower() == ".pdf"), key=newest_first)
    pdfs = [p for p in all_pdfs if in_scope(p, args.min_year, args.max_year, agencies)]
    print(f"{len(all_pdfs)} PDFs found, {len(pdfs)} match the filters (newest first).")

    if args.dry_run:
        dry_run(pdfs)
        return

    args.out.mkdir(parents=True, exist_ok=True)
    todo = [p for p in pdfs if not already_done(result_path(p, input_dir, args.out), args.retry_errors, args.retry_skipped)]
    remaining = len(todo)
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"{len(pdfs) - remaining} already done, {remaining} left; processing {len(todo)} "
          f"with {args.workers} worker(s).\n")

    spent = folder_cost(args.out)
    if args.budget is not None:
        print(f"Budget: ${args.budget:.2f}, already spent in this folder: ${spent:.2f}\n")
        if spent >= args.budget:
            print("Budget already reached; nothing to do.")
            return

    records = []
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [pool.submit(run_one, pdf, input_dir, args.out, args.delay, args.all_pages) for pdf in todo]
        for done, future in enumerate(as_completed(futures), 1):
            record = future.result()
            records.append(record)
            spent += record.get("cost_usd") or 0
            line = f"[{done}/{len(todo)}] {record['file']}: {record['status']} ({record['seconds']}s)"
            if "error" in record:
                line += f": {record['error']}"
            if args.budget is not None:
                line += f"  [${spent:.2f} of ${args.budget:.2f}]"
            print(line)
            if args.budget is not None and spent >= args.budget:
                print(f"\nBudget of ${args.budget:.2f} reached; finishing PDFs already in progress and stopping.")
                pool.shutdown(wait=True, cancel_futures=True)
                break
        pool.shutdown()
    except KeyboardInterrupt:
        print("\nStopping: letting PDFs already in progress finish (press Ctrl+C again to quit now)...")
        pool.shutdown(wait=True, cancel_futures=True)
        print("Stopped. Run the same command again to continue where you left off.")
    finally:
        counts = build_csvs(args.out)
        print(f"\nTotals in {args.out}: {counts}. See {args.out / 'summary.csv'}")
        ok = [r for r in records if r["status"] == "ok"]
        if ok:
            avg_min = sum(r["seconds"] for r in ok) / len(ok) / 60
            tokens = [r["tokens"] for r in ok if r.get("tokens")]
            print(f"This run: {len(ok)} PDFs processed, average {avg_min:.1f} min each.")
            if tokens:
                print(f"Tokens this run: {sum(tokens):,} total, {sum(tokens) // len(tokens):,} per PDF on average.")
            cost = sum(r.get("cost_usd") or 0 for r in ok)
            print(f"Estimated cost this run: ${cost:.2f}")
        print(f"Estimated cost of everything in {args.out}: ${folder_cost(args.out):.2f} "
              "(runs before cost tracking was added are not counted)")


if __name__ == "__main__":
    main()
