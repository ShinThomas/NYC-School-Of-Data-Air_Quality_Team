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
