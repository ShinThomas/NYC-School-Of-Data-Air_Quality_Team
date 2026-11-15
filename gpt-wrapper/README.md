# Air quality PDF extractor

Takes an air quality document (PDF) and returns structured JSON: project
details, pollutants, reported concentrations, emission sources and mitigation
measures. It uses Google Gemini's structured output, so the response always
matches a fixed schema.

It only works on PDFs with embedded text (newer documents). Scanned PDFs are
rejected before any API call is made.

> **The schema is a draft.** The fields below are a first pass and still need
> to be confirmed with the team.

## Setup

1. Get a free Gemini API key at https://aistudio.google.com.
2. Copy `.env.example` to `.env` and add your key:
   ```
   GEMINI_API_KEY=your-key-here
   ```
   `.env` is in `.gitignore`. Never commit it.
3. From this folder, create a virtual environment and install the packages:
   ```
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # Mac/Linux
   pip install -r requirements.txt
   ```

## Running

From the command line:
```
python wrapper.py path/to/document.pdf
python wrapper.py https://example.com/document.pdf
```

From Python:
```python
from wrapper import extract_air_quality_info

result = extract_air_quality_info("path/to/document.pdf")  # returns a dict
result = extract_air_quality_info("https://example.com/document.pdf")
```

The input can be a local path or a URL, such as a link to an EAS or EIS PDF
from CEQR Access. PDFs over 20 MB are uploaded through Gemini's File API and
deleted after the request.

## Output fields

Any field the document doesn't mention is returned as `null` or an empty list.

| Field | Description |
|---|---|
| `source` | The path or URL the PDF came from |
| `document_type` | EAS, EIS, other, or not stated |
| `project_name` | Name of the project |
| `address` | Street address of the project site |
| `borough` | NYC borough |
| `lead_agency` | Agency responsible for the review or permit |
| `project_status` | e.g. proposed, under review, approved |
| `document_date` | Date of the document (YYYY-MM-DD) |
| `significant_adverse_impact` | The document's own conclusion on air quality impact: yes, no, or not stated |
| `impact_conclusion_quote` | Short quote from the document stating that conclusion |
| `pollutants` | Names of the pollutants discussed, e.g. PM2.5, NO2 |
| `concentrations` | One entry per reported concentration value (see below) |
| `emission_sources` | Sources of emissions, e.g. boilers, traffic |
| `mitigation_measures` | Measures proposed to reduce air impacts |
| `summary` | Two or three sentence summary of the air quality findings |

Each entry in `concentrations` has these fields:

| Field | Description |
|---|---|
| `pollutant` | e.g. PM2.5 |
| `value` | The number as written in the document |
| `units` | e.g. µg/m³, ppm |
| `scenario` | existing, no-action, with-action, or not stated |
| `analysis_year` | Year the value applies to, e.g. the build year |
| `value_type` | background, project increment, or total |
| `averaging_period` | e.g. 24-hour, annual |
| `location` | Receptor or monitoring location, if given |
| `standard` | The standard or threshold it is compared to, if given |
| `exceeds_standard` | Whether the document says it exceeds the standard |
| `page` | PDF page where the value appears, for checking |

## Limitations

- **Check concentration values by hand.** Documents often report several
  numbers per pollutant (background, increment, total, different locations),
  and the model can mix them up or skip table rows. Use `page` to find each
  value in the PDF. Page numbers can also be slightly off.
- **Large EIS documents.** A full EIS can run to hundreds of pages. Sending
  only the air quality chapter is cheaper and gives more accurate results.
- **Model names change.** Google retires models regularly. If you get a
  "model not found" error, update `MODEL` at the top of `wrapper.py` to the
  current Flash model listed in AI Studio.
- **Free tier limits.** The free tier has rate limits. If you get a quota
  error, wait a minute and try again.

## Running on a folder of PDFs

```
python batch.py "E:\path\to\pdfs" --out results
```

`batch.py` processes every PDF in the folder (subfolders included) one at a
time and writes one JSON file per PDF to `results/`. It also builds:

- `results/summary.csv`: one row per PDF with its status (`ok`, `skipped`
  for scans and non-PDFs, or `error`), key fields, and any error message
- `results/concentrations.csv`: one row per extracted concentration value,
  with the PDF it came from
- `results/projects.csv`: one row per PDF that was read, with address,
  conclusion, conclusion quote, summary, emission sources, mitigation and
  whether an E-designation is mentioned. `detail_level` sorts each PDF into
  `full analysis` (reports concentrations), `screened / qualitative`
  (discusses air quality without numbers) or `short notice` (3 pages or
  fewer), with full analyses listed first. Rebuild it on its own with
  `python projects.py results`.

[DATA_DICTIONARY.md](DATA_DICTIONARY.md) explains every column and how to
read the scenarios and values.

You can stop it at any time with Ctrl+C. Running the same command again skips
PDFs that already finished. Add `--retry-errors` to re-run the ones that
failed. Rate-limit and overload errors (429, 503) are retried automatically
with increasing waits. `--delay` sets the pause between PDFs (default 5
seconds) to stay under the free tier's rate limit.

### Choosing which PDFs to run

File names start with the CEQR number: `22DCP188Q` is fiscal year 2022,
Department of City Planning. You can filter on that:

```
python batch.py "D:/easpdfs" --min-year 2010 --max-year 2027 --agency DCP DEP
```

Files whose names don't follow this pattern are left out when a filter is
set.

### Estimating a run first

`--dry-run` checks every matching PDF for embedded text and prints how many
are text PDFs (each needs one Gemini call) and how many are scans (skipped).
It makes no API calls:

```
python batch.py "D:/easpdfs" --min-year 2010 --dry-run
```

During a real run, each result records how many seconds and tokens it took,
and the run ends by printing the averages. Multiply them by the dry-run's text
count to estimate the full run's time and cost.

### Page selection (saves tokens)

PDFs over 15 pages are trimmed before sending: the first 3 pages (project
info), every page that mentions air quality terms or the review's conclusion,
and the page(s) after each match. If a PDF contains concentration units
(µg/m³, ppm), all of its matching pages are kept, plus 2 pages after each, so
air quality tables are sent in full. Concentration `page` numbers are mapped
back to the original PDF.

In testing, a 282-page form with no air quality data went from 325,000 to
17,000 tokens with the same results, and an 85-page EAS with air quality
tables kept every table page and found the same values. Use `--all-pages` to
send whole PDFs instead (Gemini rejects PDFs over 1,000 pages).

Each result records `total_pages`, `pages_sent`, `tokens` and an estimated
`cost_usd` (prices are set at the top of `wrapper.py`).

`--budget 18` stops the run once the estimated cost of everything in the
output folder reaches $18. PDFs already in progress still finish, so it can go
slightly over. The estimate isn't a bill: check real spend on the billing page.

### Speed and order

- PDFs are processed newest fiscal year first.
- `--workers 3` processes 3 PDFs at the same time. Use this only on a paid
  API key; the free tier's rate limits are too low.
- `--limit 10` stops after 10 PDFs, which is useful for a test run.
- With more than one worker, Ctrl+C lets the PDFs already in progress finish
  before stopping (up to 5 minutes). Press Ctrl+C again to quit immediately;
  those PDFs will be redone on the next run.

`results/` and PDFs are in `gpt-wrapper/.gitignore`, so they won't be
committed.
