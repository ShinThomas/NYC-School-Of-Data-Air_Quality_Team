from pathlib import Path
import pandas as pd

folder = Path(__file__).resolve().parent
source = folder / "NYC_2023_NEI_TRAPPA_mapped_no_refueling.csv"
output = folder / "NYC_2023_TRAPPA_emissions_by_county_vehicle_pollutant.csv"

df = pd.read_csv(source)

# The input file already excludes Refueling; this is an extra safeguard.
df = df[df["scc level-3"] != "Refueling"].copy()

if not (df["emissions uom"] == "TON").all():
    raise ValueError("Some emissions are not in tons. Check the source file.")

df["total emissions"] = pd.to_numeric(df["total emissions"], errors="raise")

# Add together emissions for the same county, vehicle type, and pollutant.
result = df.groupby(
    ["county", "borough", "trappa_vehicle_type", "pollutant code"],
    as_index=False
)["total emissions"].sum()

result = result.rename(columns={
    "trappa_vehicle_type": "TRAPPA Vehicle Type",
    "pollutant code": "Pollutant",
    "total emissions": "2023 Emissions (tons/year)",
    "county": "County",
    "borough": "Borough",
})
result = result.sort_values(["County", "TRAPPA Vehicle Type", "Pollutant"])
result.to_csv(output, index=False)

print(f"Saved {len(result)} rows to {output.name}")