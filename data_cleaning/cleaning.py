import pandas as pd

ceqr_locations = pd.read_csv("CEQR_Project_Locations.csv")
pluto = pd.read_csv("PLUTO.csv")
zap = pd.read_csv("Zoning_Application_Portal_(ZAP).csv")

joined = pd.merge(ceqr_locations, pluto, how="outer", left_on="Lot", right_on="Tax lot")

print(joined.head())