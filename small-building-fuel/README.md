# Small-building fuel use estimates (NYC)

Estimates annual on-site fuel use (natural gas and oil) for NYC buildings under
25,000 sq ft. These buildings are not covered by Local Law 84 (LL84) energy
benchmarking.

## Method

1. **LL84 (2024)**: clean the benchmarking data and compute fuel intensity
   (kBtu per sq ft) for each property type. Cleaning drops campus parent rows,
   rows with under 12 months of meter data, GFA under 1,000 sq ft, and the top
   and bottom 2% of intensity within each type.
2. **RECS 2020**: compute weighted fuel intensity for one- and two-family homes
   in urban New York, since LL84 has no equivalent for these.
3. **PLUTO**: take every lot with building area under 25,000 sq ft and map its
   building class to a property type.
4. **Estimate fuel**:
   - `fuel_flat` (primary estimate): building area × median intensity for the type.
   - `fuel_trend` (sensitivity check): a log-log fit of fuel against floor area,
     fit for each type. Types with too little data fall back to the flat estimate.
5. **Split into oil and gas**: use oil shares by property type and borough from
   LL84, where a group has at least 30 buildings. Otherwise use the citywide
   share for the type. One- and two-family homes use the RECS share.

## Data

The data files are not in this repo because they are too large for GitHub.
Download them and put them in the same folder as `task.py`, with exactly these
names:

| File | Source |
|---|---|
| `ll84.csv` | NYC Open Data: Energy and Water Data Disclosure for Local Law 84 |
| `Primary_Land_Use_Tax_Lot_Output_(PLUTO)_20261025.csv` | NYC Open Data: Primary Land Use Tax Lot Output (PLUTO) |
| `recs2020_public_v7.csv` | EIA Residential Energy Consumption Survey 2020 microdata: https://www.eia.gov/consumption/residential/data/2020/ |

## Running

```
pip install -r requirements.txt
python task.py
```

The script shows a plot of fuel intensity against floor area for the six most
common property types (`Figure_1.png`). It then writes
`small_building_fuel_2024.csv`, with one row per small lot. Fuel columns in that
file are kBtu per year.
