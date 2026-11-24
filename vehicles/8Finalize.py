import csv
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
TRAFFIC = FOLDER / "TRAPPA_corrected_traffic_tons_ready.csv"
RATES = FOLDER / "NYC_2023_emissions_per_registered_vehicle(1).csv"
if not RATES.exists():
    RATES = FOLDER / "NYC_2023_emissions_per_registered_vehicle.csv"
OUTPUT = FOLDER / "TRAPPA_traffic_with_estimated_emissions_tons_per_year.csv"

POLLUTANTS = {
    "NH3": "NH3",
    "NOX": "NOx",
    "PM25-PRI": "PM2.5",
    "SO2": "SO2",
    "VOC": "VOC",
}


with RATES.open(newline="", encoding="utf-8-sig") as f:
    rates = {
        (r["Borough"].strip(), r["Pollutant"].strip().upper()):
        float(r["Tons per Registered Vehicle per Year"])
        for r in csv.DictReader(f)
    }

with TRAFFIC.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    columns = reader.fieldnames[:]
    rows = list(reader)

calculated = 0
for row in rows:
    borough = row["borough"].strip()
    amount = row["traffic_change_in_selected_period"].strip()

    for code, label in POLLUTANTS.items():
        column = f"{label}_annual_emissions_change_tons_per_year"
        if column not in columns:
            columns.append(column)

        rate = rates.get((borough, code))
        if amount and rate is not None:
            # Same formula as before, now expressed in U.S. tons/year.
            row[column] = f"{float(amount) * rate:.10f}"
        else:
            row[column] = ""

    if not amount:
        row["annual_emissions_status"] = "NOT CALCULATED: no numeric traffic change"
    elif (borough, "NH3") not in rates:
        row["annual_emissions_status"] = "NOT CALCULATED: no single borough-specific rate"
    else:
        calculated += 1
        row["annual_emissions_status"] = (
            "ROUGH PROXY ONLY: selected-period trips x "
            "2023 tons/registered vehicle/year; not actual annual project emissions"
        )

with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)

print(f"Saved: {OUTPUT.name}")
print(f"Projects: {len(rows)}; with estimates: {calculated}; without estimates: {len(rows)-calculated}")