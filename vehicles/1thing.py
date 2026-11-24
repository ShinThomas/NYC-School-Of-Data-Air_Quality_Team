from pathlib import Path
import pandas as pd

folder = Path(__file__).resolve().parent
input_csv = folder / 'NYC_2023_NEI_NH3_NOx_PM25_SO2_VOC.csv'
output_csv = folder / 'NYC_2023_NEI_TRAPPA_mapped_no_refueling.csv'

# SCC Level-3 category -> closest TRAPPA vehicle category
mapping = {
    'Passenger Car': 'Car',
    'Passenger Truck': 'Car',
    'Motorcycle': 'Car',                   # Approximation; TRAPPA has no motorcycle class
    'Light Commercial Truck': 'Small Commercial Truck',
    'Single Unit Short-haul Truck': 'Medium Truck',
    'Motor Home': 'Medium Truck',          # Approximation; motor homes vary in weight
    'Single Unit Long-haul Truck': 'Heavy Truck',
    'Combination Short-haul Truck': 'Heavy Truck',
    'Combination Long-haul Truck': 'Heavy Truck',
    'Refuse Truck': 'Heavy Truck',
    'Transit Bus': 'Bus',
    'School Bus': 'Bus',
    'Other Buses': 'Bus',
}

# Load the original records and remove refueling (not a vehicle class).
df = pd.read_csv(input_csv, dtype={'fips code': str, 'scc': str})
df = df[df['scc level-3'] != 'Refueling'].copy()

df['trappa_vehicle_type'] = df['scc level-3'].map(mapping)
if df['trappa_vehicle_type'].isna().any():
    missing = df.loc[df['trappa_vehicle_type'].isna(), 'scc level-3'].unique()
    raise ValueError(f'Unmapped vehicle categories: {missing}')

# Make approximate classifications visible for future emissions analysis.
df['mapping_note'] = ''
df.loc[df['scc level-3'] == 'Motorcycle', 'mapping_note'] = 'Approximation: motorcycle grouped with cars'
df.loc[df['scc level-3'] == 'Motor Home', 'mapping_note'] = 'Approximation: motor home size varies'

# Group similar vehicle records together; retain all EPA data and emission values.
order = ['Car', 'Small Commercial Truck', 'Medium Truck', 'Heavy Truck', 'Bus']
df['trappa_vehicle_type'] = pd.Categorical(df['trappa_vehicle_type'], categories=order, ordered=True)
df = df.sort_values(['trappa_vehicle_type', 'borough', 'scc level-3'])
df.to_csv(output_csv, index=False)

print(f'Saved {len(df)} rows to {output_csv.name}')
print(df['trappa_vehicle_type'].value_counts(sort=False))