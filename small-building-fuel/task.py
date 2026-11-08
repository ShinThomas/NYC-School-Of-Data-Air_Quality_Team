import pandas as pd

cols = {
    "Calendar Year": "year",
    "Property ID": "pid",
    "Parent Property ID": "parent_pid",
    "NYC Borough, Block and Lot (BBL)": "bbl",
    "Primary Property Type - Portfolio Manager-Calculated": "ptype",
    "Property GFA - Calculated (Buildings) (ft²)": "gfa",
    "Year Built": "year_built",
    "Number of Buildings": "n_bldgs",
    "Latitude": "lat",
    "Longitude": "lon",
    "Natural Gas Use (kBtu)": "gas",
    "Fuel Oil #1 Use (kBtu)": "oil1",
    "Fuel Oil #2 Use (kBtu)": "oil2",
    "Fuel Oil #4 Use (kBtu)": "oil4",
    "Fuel Oil #5 & 6 Use (kBtu)": "oil56",
    "Diesel #2 Use (kBtu)": "diesel",
    "Propane Use (kBtu)": "propane",
    "Kerosene Use (kBtu)": "kerosene",
    "Direct GHG Emissions (Metric Tons CO2e)": "direct_ghg",
    "Alert - Energy Meter has less than 12 full calendar months of data": "alert_short",
    "Alert - Gross Floor Area is 0 ft2": "alert_gfa0",
}

# thousands="," so "51,749" is read as 51749 instead of text
ll84 = pd.read_csv("ll84.csv", low_memory=False,
                   usecols=list(cols), thousands=",")
#print(ll84.shape)              # (rows, columns)
#print(ll84.columns.tolist())   # every column name
#ll84.head()                    # first 5 rows

ll84 = ll84[ll84["Calendar Year"] == 2024]   # pick the latest complete year
df = ll84[list(cols)].rename(columns=cols)

# Campus "parent" rows (parent_pid == own pid) are totals of their child
# buildings, which are also in the data. Drop parents to avoid double counting.
df = df[df["parent_pid"].astype(str) != df["pid"].astype(str)]

# Drop rows with < 12 months of meter data (understated annual fuel) or GFA = 0
df = df[(df["alert_short"] == "Ok") & (df["alert_gfa0"] == "Ok")]

fuels = ["gas", "oil1", "oil2", "oil4", "oil56", "diesel", "propane", "kerosene"]
num_cols = fuels + ["gfa", "direct_ghg", "year_built"]
df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")

df[fuels] = df[fuels].fillna(0)
df["oil_total"] = df[["oil1", "oil2", "oil4", "oil56", "diesel", "kerosene"]].sum(axis=1)
df["fuel"] = df[fuels].sum(axis=1)
# gfa >= 1000: smaller LL84 entries (down to 1 sq ft) are data entry errors
df = df[(df["gfa"] >= 1000) & (df["fuel"] > 0)].copy()
df["intensity"] = df["fuel"] / df["gfa"]   # kBtu per sq ft

q = df.groupby("ptype")["intensity"]
lo = q.transform(lambda s: s.quantile(0.02))
hi = q.transform(lambda s: s.quantile(0.98))
df = df[df["intensity"].between(lo, hi)]

import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

# Plot log10 columns instead of log axes, so lowess smooths in log space (the
# same space polyfit uses) and isn't dragged around by a few huge buildings
df["log_gfa"] = np.log10(df["gfa"])
df["log_intensity"] = np.log10(df["intensity"])
top = df["ptype"].value_counts().head(6).index   # 6 most common types
g = sns.lmplot(data=df[df["ptype"].isin(top)], x="log_gfa", y="log_intensity",
               col="ptype", col_wrap=3, lowess=True,
               scatter_kws={"alpha": 0.2, "s": 8})
plt.show()

# PLUTO building class (first letter) -> property type.
# A/B have no LL84 equivalent and get RECS intensities below.
# G (garages) is left out: LL84 floor area excludes parking.
crosswalk = {
    "A": "One-family home",
    "B": "Two-family home",
    "C": "Multifamily Housing",              # walk-up apartments
    "D": "Multifamily Housing",              # elevator apartments
    "S": "Mixed Use Property",               # residence with store
    "K": "Retail Store",
    "O": "Office",
    "E": "Non-Refrigerated Warehouse",
    "M": "Worship Facility",
    "F": "Manufacturing/Industrial Plant",
    "W": "K-12 School",
    "H": "Hotel",
    "I": "Medical Office",                   # small I lots are mostly clinics
}
# R (condos) mixes homes and businesses, so map by full two-character class
condo = {c: "Multifamily Housing" for c in ["R1", "R2", "R3", "R4", "R6", "R9", "RD", "RR"]}
condo["RM"] = "Mixed Use Property"           # mixed residential & commercial

fits = {}
for t in sorted(set(crosswalk.values())):
    sub = df[df["ptype"] == t]
    if len(sub) < 30 or sub["gfa"].nunique() < 5:
        print(f"{t}: skipped (n = {len(sub)})")
        continue
    b, a = np.polyfit(np.log(sub["gfa"]), np.log(sub["fuel"]), 1)
    fits[t] = (a, b)
    print(f"{t}: b = {b:.2f}, n = {len(sub)}")

pluto = pd.read_csv("Primary_Land_Use_Tax_Lot_Output_(PLUTO)_20261025.csv", low_memory=False, thousands=",",
                    usecols=["BBL", "bldgarea", "bldgclass", "landuse", "yearbuilt",
                             "latitude", "longitude"])
pluto = pluto.rename(columns={"BBL": "bbl"})
pluto["bbl"] = pd.to_numeric(pluto["bbl"], errors="coerce").astype("Int64").astype(str)
df["bbl"] = pd.to_numeric(df["bbl"], errors="coerce").astype("Int64").astype(str)

small = pluto[(pluto["bldgarea"] > 0) & (pluto["bldgarea"] < 25000)].copy()

small["ptype"] = small["bldgclass"].map(condo).fillna(small["bldgclass"].str[0].map(crosswalk))
print(small["ptype"].isna().mean())   # share left unmapped

# 1-2 family homes: RECS 2020 survey homes in urban New York.
# TYPEHUQ 2/3 = single-family detached/attached, 4 = apartment in 2-4 unit building
recs = pd.read_csv("recs2020_public_v7.csv", usecols=[
    "TYPEHUQ", "state_postal", "UATYP10", "NWEIGHT", "TOTSQFT_EN", "BTUNG", "BTUFO", "BTULP"])
recs = recs[(recs["state_postal"] == "NY") & (recs["UATYP10"] == "U")].copy()
recs["ptype"] = recs["TYPEHUQ"].map({2: "One-family home", 3: "One-family home", 4: "Two-family home"})
recs["fuel"] = recs[["BTUNG", "BTUFO", "BTULP"]].sum(axis=1)   # kBtu, on-site combustion
# Each surveyed home stands for NWEIGHT real homes, so weight both totals
w = recs["NWEIGHT"]
recs_int = ((recs["fuel"] * w).groupby(recs["ptype"]).sum()
            / (recs["TOTSQFT_EN"] * w).groupby(recs["ptype"]).sum())
print(recs_int)

# Flat (primary): median LL84 intensity, or RECS intensity for A/B
med = df.groupby("ptype")["intensity"].median()
flat_int = pd.concat([med, recs_int])
small["fuel_flat"] = small["bldgarea"] * small["ptype"].map(flat_int)

# Trend (sensitivity check): fuel = e^a * area^b. Types without a fit fall back to flat
a = small["ptype"].map({t: f[0] for t, f in fits.items()})
b = small["ptype"].map({t: f[1] for t, f in fits.items()})
small["fuel_trend"] = (np.exp(a) * small["bldgarea"] ** b).fillna(small["fuel_flat"])

print(small["fuel_flat"].notna().mean())   # share of small lots with an estimate
print(small.groupby("ptype")[["fuel_flat", "fuel_trend"]].sum().div(1e6).round(1))   # million kBtu

# Split fuel into oil and gas (oil emits far more PM2.5). Oil share = total oil /
# total fuel, so shares x fuel add up correctly. Oil use differs a lot by borough
# (Multifamily: 15% Manhattan vs 2% Brooklyn), so use type x borough shares where
# LL84 has >= 30 buildings, else the citywide share for the type.
df["boro"] = df["bbl"].str[0]       # first BBL digit: 1 MN, 2 BX, 3 BK, 4 QN, 5 SI
small["boro"] = small["bbl"].str[0]
tb = df.groupby(["ptype", "boro"])[["oil_total", "fuel"]].sum()
n_tb = df.groupby(["ptype", "boro"]).size()
share_tb = (tb["oil_total"] / tb["fuel"])[n_tb >= 30]
t = df.groupby("ptype")[["oil_total", "fuel"]].sum()
# RECS has no borough, so 1-2 family homes get one share each
recs_oil = ((recs["BTUFO"] * w).groupby(recs["ptype"]).sum()
            / (recs["fuel"] * w).groupby(recs["ptype"]).sum())
share_t = pd.concat([t["oil_total"] / t["fuel"], recs_oil])

idx = pd.MultiIndex.from_arrays([small["ptype"], small["boro"]])
small["oil_share"] = share_tb.reindex(idx).to_numpy()
small["oil_share"] = small["oil_share"].fillna(small["ptype"].map(share_t))
small["oil_flat"] = small["fuel_flat"] * small["oil_share"]
small["gas_flat"] = small["fuel_flat"] - small["oil_flat"]     # gas + small propane
small["oil_trend"] = small["fuel_trend"] * small["oil_share"]
small["gas_trend"] = small["fuel_trend"] - small["oil_trend"]

print(small.groupby("boro")[["gas_flat", "oil_flat"]].sum().div(1e6).round(0))   # million kBtu

# Save one row per small lot with an estimate. Fuel columns are kBtu per year.
out_cols = ["bbl", "boro", "latitude", "longitude", "bldgclass", "ptype", "bldgarea",
            "yearbuilt", "gas_flat", "oil_flat", "fuel_flat", "oil_share",
            "gas_trend", "oil_trend", "fuel_trend"]
out = small.loc[small["fuel_flat"].notna(), out_cols].round(
    {"gas_flat": 0, "oil_flat": 0, "fuel_flat": 0, "oil_share": 3,
     "gas_trend": 0, "oil_trend": 0, "fuel_trend": 0})
out.to_csv("small_building_fuel_2024.csv", index=False)
print(f"saved {len(out)} rows to small_building_fuel_2024.csv")