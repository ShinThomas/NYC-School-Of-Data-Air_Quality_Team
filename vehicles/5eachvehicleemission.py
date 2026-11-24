import csv
from collections import defaultdict
from pathlib import Path

folder = Path(__file__).resolve().parent
registrations_csv = folder / "Vehicle_and_Boat_Registrations_by_Fuel_Type_per_County_20261123.csv"
emissions_csv = folder / "NYC_2023_TRAPPA_emissions_by_county_vehicle_pollutant.csv"
if not emissions_csv.exists():
    emissions_csv = folder / "NYC_2023_TRAPPA_emissions_by_county_vehicle_pollutant(1).csv"
output_csv = folder / "NYC_2023_emissions_per_registered_vehicle.csv"

# DMV county names -> borough names
nyc = {
    "BRONX": "Bronx",
    "KINGS": "Brooklyn",
    "NEW YORK": "Manhattan",
    "QUEENS": "Queens",
    "RICHMOND": "Staten Island",
}

# Sum VEH registrations across fuel types; exclude boats and trailers.
vehicles = defaultdict(int)
with registrations_csv.open(newline="", encoding="utf-8-sig") as file:
    for row in csv.DictReader(file):
        county = row["County"].strip().upper()
        if county in nyc and row["Record Type"].strip().upper() == "VEH":
            vehicles[county] += int(row["Count of rows of Registration Class"].replace(",", ""))

# Sum 2023 emissions across all TRAPPA types for each county and pollutant.
emissions = defaultdict(float)
with emissions_csv.open(newline="", encoding="utf-8-sig") as file:
    for row in csv.DictReader(file):
        county = row["County"].strip().upper()
        if county in nyc:
            emissions[(county, row["Pollutant"].strip())] += float(
                row["2023 Emissions (tons/year)"]
            )

rows = []
for (county, pollutant), tons in sorted(emissions.items()):
    count = vehicles[county]
    if count == 0:
        raise ValueError(f"No vehicle registrations found for {county}")
    rows.append({
        "County": county.title(),
        "Borough": nyc[county],
        "Pollutant": pollutant,
        "2023 Total Emissions (tons/year)": round(tons, 8),
        "Registered Vehicles": count,
        "Tons per Registered Vehicle per Year": round(tons / count, 12),
        "Kg per Registered Vehicle per Year": round(tons * 907.18474 / count, 8),
    })

with output_csv.open("w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

print(f"Saved {len(rows)} county-pollutant rows to {output_csv.name}")
for county in nyc:
    print(f"{nyc[county]}: {vehicles[county]:,} registered vehicles")