import pandas as pd

ceqr_locations = pd.read_csv("CEQR_Project_Locations.csv")
pluto = pd.read_csv("PLUTO.csv")
zap = pd.read_csv("Zoning_Application_Portal_(ZAP).csv")

# Getting rid of completed projects (we can reexamine this process at the mtg)
zap = zap[(zap["project_status"] == "Active") | (zap["project_status"] == "On-Hold") & (zap["ceqr_number"] != '')]
print(f"ZAP shape: {zap.shape}")

merged = pd.merge(zap, ceqr_locations, how="left", left_on="ceqr_number", right_on="CEQR")
print(f"Merged ZAP and CEQR Locations shape: {merged.shape}")

merged = merged.dropna(subset="CEQR").dropna(subset="Block").dropna(subset="Lot")
print(f"Merged dropping NaN shape: {merged.shape}")

locations_shape = merged.shape

def get_bbl(borough, block, lot):
    
    bbl = ""
    if borough == "Manhattan":
        bbl = bbl + "1"
    elif borough == "Bronx":
        bbl = bbl + "2"
    elif borough == "Brooklyn":
        bbl = bbl + "3"
    elif borough == "Queens":
        bbl = bbl + "4"
    elif borough == "Staten Island":
        bbl = bbl + "5"

    bbl += block.zfill(5)
    bbl += lot.zfill(4)

    return int(bbl)

bbls = []

for _, row in merged.iterrows():
    borough = row["borough"]
    block = str(int(row["Block"]))
    lot = str(int(row["Lot"]))
    bbl = get_bbl(borough, block, lot)
    bbls.append(bbl)

merged["BBL"] = bbls

merged = pd.merge(merged, pluto, on="BBL").dropna(subset="latitude").dropna(subset="longitude")

print(f"Merged with PLUTO shape: {merged.shape}")
print(f"{locations_shape[0]-merged.shape[0]} records lost")
print(f"{((locations_shape[0] - merged.shape[0])/merged.shape[0])*100}% records lost")
print(merged.columns)

cleaned_merge = merged[["project_id", "project_name", "project_status", "ceqr_number", "BBL", "latitude", "longitude"]]

print(cleaned_merge.columns)

cleaned_merge.drop_duplicates(subset="BBL")

print(cleaned_merge.shape)

import geopandas as gpd
from shapely.geometry import Point, Polygon

gdf = gpd.GeoDataFrame(cleaned_merge, geometry=[Point(xy) for xy in zip(cleaned_merge['longitude'], cleaned_merge['latitude'])])

geojson_str = gdf.to_json()

with open("ceqr.geojson", "w") as f:
    f.write(geojson_str)

print("Points written to ceqr.geojson")


tax_lots = pd.read_csv("TAX_LOT_POLYGON.csv")

merged_geometry = pd.merge(left=merged, right=tax_lots, how="left", left_on="BBL", right_on="BBL")

merged_geometry = merged_geometry[["project_id", "project_name", "project_status", "ceqr_number", "borough", "current_milestone_date", "the_geom"]]

from shapely import wkt

merged_geometry = merged_geometry.dropna()

polygons = []

for _, row in merged_geometry.iterrows():
    P = wkt.loads(str(row["the_geom"]))
    polygons.append(P)

merged_geometry["geometry"] = polygons

gpd_tax_lots = gpd.GeoDataFrame(merged_geometry, geometry=merged_geometry["geometry"])

geojson_shapes_str = gpd_tax_lots.to_json()

with open("ceqr_shapes.geojson", "w") as f:
    f.write(geojson_shapes_str)

print("Tax lot shapefiles written to ceqr_shapes.json")