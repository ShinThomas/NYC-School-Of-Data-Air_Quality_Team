import pandas as pd

# Read CSV
df = pd.read_csv("traffic_trappa.csv")

# Find rows to delete
remove = (
    df["trappa_vehicle_type"].isna() &
    df["trappa_flag"].fillna("").str.contains(
        "total of all vehicle", case=False
    )
)

# Delete matching rows
df = df[~remove]

# Save cleaned CSV
df.to_csv("traffic_trappa_cleaned.csv", index=False)

print(f"Removed {remove.sum()} rows")
print(f"Remaining {len(df)} rows")