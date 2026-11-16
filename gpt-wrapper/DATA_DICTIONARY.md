# Data dictionary: CEQR air quality extraction

This explains the CSVs produced by `batch.py`: what each file and column
means and how to read the numbers. For how to run the code, see
[README.md](README.md).

## What was covered

The first run (November 2026) covered CEQR environmental review PDFs from
**fiscal years 2010–2027** on the team's flash drive:

| | PDFs |
|---|---|
| Total | 3,163 |
| Read by Gemini | 1,735 |
| Skipped (scans with no embedded text) | 1,428 |

Each PDF was read by Gemini (`gemini-3.8-flash`), which filled in a fixed
set of fields. Estimated cost: about $15. PDFs from before FY2010 were not
included.

## The three files

| File | One row per | Use it for |
|---|---|---|
| `projects.csv` | PDF that was read | What the city concluded about each project, and why |
| `concentrations.csv` | Number reported in a PDF | The city's air quality numbers |
| `summary.csv` | PDF on the drive, including skipped ones | Checking the run: status, errors, cost |

The files link through the PDF name: `file` in `concentrations.csv` and
`summary.csv`, and `ceqr_number` (the name without `.pdf`) in `projects.csv`.

## Reading a CEQR number

`10DCP001K` = fiscal year **20**10, Department of City Planning (**DCP**),
project **001**, borough **K**.

| Borough letter | Borough |
|---|---|
| M | Manhattan |
| K | Brooklyn |
| Q | Queens |
| X | Bronx |
| R | Staten Island |
| Y | Citywide or more than one borough |

Common agencies: DCP (City Planning), BSA (Board of Standards and Appeals),
DEP (Environmental Protection), HPD (Housing Preservation and Development),
DHS (Homeless Services), DME (Deputy Mayor for Economic Development), DPR
(Parks), DOT (Transportation).

## Three kinds of year

| Year | Where | Meaning |
|---|---|---|
| Fiscal year | First two digits of the file name; `fiscal_year` in `projects.csv` | When the project was filed. NYC's fiscal year starts July 1, so FY2027 began July 2026. |
| Document date | `document_date` | When the PDF was written |
| Analysis year | `analysis_year` in `concentrations.csv` | The year a number refers to: a past year for monitor data, a future build year for predictions |

For example, a FY2010 document can report 2007 monitor data and a prediction
for 2014.

## Scenarios: existing, No-Action, With-Action

Environmental reviews compare scenarios. Take a building finished in 2030:

| Scenario | Question | Example (PM2.5) |
|---|---|---|
| **Existing** | What is the air like today? | Nearest monitor reads 9.0 µg/m³ |
| **No-Action** | What will it be in 2030 without the project? | 9.5 |
| **With-Action** | What will it be in 2030 with the project built? | 9.8 |

The project's impact, called the **increment**, is With-Action minus
No-Action: 9.8 − 9.5 = 0.3. The city judges whether the increment is
significant and whether the With-Action total stays under the standard.

Most reviews of a building's boiler or HVAC skip the No-Action scenario.
They add the project's increment to today's background instead:

> background 9.0 + project increment 0.3 = total 9.3, compared to the standard

That is why only 44 of 2,401 values are No-Action. Full No-Action vs.
With-Action tables appear mainly in large traffic studies, such as
rezonings.

## concentrations.csv

One row per number reported in a PDF: 2,401 values from 83 PDFs.

| Column | Meaning |
|---|---|
| `file` | PDF the number came from |
| `pollutant` | e.g. PM2.5, NO2, CO. Names aren't standardized: "CO" and "Carbon Monoxide" both appear. |
| `value` | The number as written in the document |
| `units` | e.g. µg/m³, ppm |
| `scenario` | `existing`, `no-action`, `with-action` or `not stated` (see above) |
| `analysis_year` | Year the number refers to (blank for 38% of values) |
| `value_type` | `background` (today's air), `project increment` (only what the project adds) or `total` (background + project) |
| `averaging_period` | Time window the concentration is averaged over, e.g. 1-hour, 24-hour, annual. Standards are set per window. |
| `location` | Air monitor, intersection or receptor (modeled point) the number applies to |
| `standard` | The limit the document compares it to, in the same units |
| `exceeds_standard` | TRUE if the document says the value is over the limit |
| `page` | PDF page to check the number against |

**Which rows to compare with a model:**

| Want | Filter |
|---|---|
| Predicted air level with the project | `scenario = with-action` and `value_type = total` |
| Today's air near the site | `value_type = background` |
| How much the project adds | `value_type = project increment` |

**Don't treat increments as air levels.** An increment of 0.3 means "the
project adds 0.3", not "the air will be 0.3".

**Example row:**

| file | pollutant | value | units | scenario | analysis_year | value_type | averaging_period | location | standard | exceeds_standard | page |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10DCP001K.pdf | Sulfur Dioxide | 0.035 | ppm | existing | 2007 | background | 3-hour average | Queens College 2, Queens | 0.5 | FALSE | 107 |

The Queens College 2 monitor measured SO2 at 0.035 ppm (3-hour average) in
2007, well under the 0.5 ppm standard. It is background air near the site,
not an effect of the project.

## projects.csv

One row per PDF that was read (1,735 rows), with full analyses first.

| Column | Meaning |
|---|---|
| `ceqr_number` | CEQR number (PDF name without `.pdf`) |
| `fiscal_year` | From the CEQR number |
| `agency` | Agency code from the CEQR number |
| `detail_level` | How much air quality content the PDF has (see below) |
| `significant_adverse_impact` | The document's own conclusion: `yes`, `no` or `not stated` |
| `e_designation` | `yes` if an E-designation is mentioned. An E-designation is a restriction on the site, e.g. on heating fuel or stack location. |
| `n_concentrations` | Number of values in `concentrations.csv` from this PDF |
| `project_name`, `address`, `borough`, `lead_agency` | Project details. `address` is blank for 275 rows. |
| `document_type` | `EAS` (Environmental Assessment Statement), `EIS` (Environmental Impact Statement), `other` or `not stated` |
| `document_date` | Date of the document |
| `pollutants` | Pollutants discussed, separated by `;` |
| `emission_sources` | e.g. boilers, traffic, HVAC |
| `mitigation_measures` | Measures to reduce air impacts, including E-designations |
| `impact_conclusion_quote` | Short quote of the document's conclusion |
| `summary` | Two or three sentence summary of the air quality findings |
| `total_pages` | Pages in the PDF |
| `file` | Path to the original PDF |

| `detail_level` | Rows | Meaning |
|---|---|---|
| `full analysis` | 83 | Reports concentrations (in `concentrations.csv`) |
| `screened / qualitative` | 637 | Gives a conclusion and reasons but no numbers. Usually the project fell below a screening threshold (e.g. too few new vehicle trips), so no modeling was done. |
| `short notice` | 1,015 | 3 pages or fewer: cover letters, notices, determinations |

## summary.csv

One row per PDF on the drive, used to check the run.

| Column | Meaning |
|---|---|
| `status` | `ok` (read), `skipped` (scan or not a PDF) or `error` (failed; can be retried) |
| `error` | Reason for a skip or error |
| `document_type`, `project_name`, `borough`, `document_date`, `significant_adverse_impact`, `n_concentrations` | Same as in `projects.csv` |
| `total_pages`, `pages_sent` | Pages in the PDF, and how many were sent to Gemini. Long PDFs are trimmed to the pages that mention air quality. |
| `seconds`, `tokens`, `cost_usd`, `processed_at` | Time, tokens, estimated cost and time of processing |

## Known issues

- **Values were extracted by AI and haven't been checked by hand.** Check
  important values against the PDF using `page`.
- **Increments are labeled `with-action`.** Strictly, an increment is
  With-Action minus No-Action. Filter on `value_type`, not only `scenario`.
- **"existing" mixes two things.** Mostly it holds background monitor
  readings. But 64 values (from `14DCP027Q`, `20DCP083Q`, `18DCP177K` and
  `17DME003Q`) are pollution from existing nearby sources (dry cleaners,
  spray booths, factories) reaching the new project. Those are labeled
  `existing` with `value_type = project increment`.
- **Increment mismatches.** Where No-Action, With-Action and increment all
  appear, 15 of 18 sets add up. The 3 that don't (`20DCP083Q` annual PM2.5 at
  38th Ave Ext/Janet Pl, and `17DCP069R` 24-hour PM10 and PM2.5 at Edgewater
  St/Lynhurst Ave) need checking against the PDF.
- **One probable false "yes".** `16DCP031M` is marked as having a significant
  impact, but its quote is the form's generic definition of a Positive
  Declaration. The other "yes" projects are `21DCP020M`, `12NYP001M` and
  `10DCP017X` (the last says further study is needed).
- **Pollutant names aren't standardized** (CO vs. Carbon Monoxide, NO2 vs.
  Nitrogen Dioxide).
- **Missing data:** 38% of values have no `analysis_year`, and 275 projects
  have no address.
- **Scans weren't read.** 1,428 PDFs, mostly from 2010–2020, were skipped
  because they have no embedded text.
