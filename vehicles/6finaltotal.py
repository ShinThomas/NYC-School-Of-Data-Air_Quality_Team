import csv
from pathlib import Path

FOLDER = Path(__file__).resolve().parent


def find_csv(name):
    # Accept either the original filename or a downloaded copy ending in (1), (2), etc.
    stem = Path(name).stem
    candidates = [FOLDER / (stem + '(1).csv'), FOLDER / name] + sorted(FOLDER.glob(stem + '(*)' + '.csv'))
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f'Put {name} beside this Python script in {FOLDER}')


TRAFFIC = find_csv('traffic_trappa_grouped_by_project.csv')
RATES = find_csv('NYC_2023_emissions_per_registered_vehicle.csv')
OUTPUT = FOLDER / 'traffic_trappa_projects_with_estimated_emissions.csv'

# First five digits of an NYC census tract identify the county.
COUNTIES = {
    '36005': 'Bronx', '36047': 'Brooklyn', '36061': 'Manhattan',
    '36081': 'Queens', '36085': 'Staten Island'
}
POLLUTANTS = {
    'NH3': 'NH3', 'NOX': 'NOx', 'PM25-PRI': 'PM2.5',
    'SO2': 'SO2', 'VOC': 'VOC'
}

with RATES.open(encoding='utf-8-sig', newline='') as f:
    rate_rows = list(csv.DictReader(f))

# (borough, pollutant) -> 2023 kg per registered vehicle per year
rates = {
    (r['Borough'].strip(), r['Pollutant'].strip().upper()):
        float(r['Kg per Registered Vehicle per Year'])
    for r in rate_rows
}

with TRAFFIC.open(encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    original_columns = reader.fieldnames
    projects = list(reader)

new_columns = ['emissions_borough', 'vehicle_amount_used', 'amount_source'] + [
    f'estimated_{label}_change_kg_per_year' for label in POLLUTANTS.values()
]

for row in projects:
    # Do not guess a borough for citywide or unmatched projects.
    tract = (row.get('tract_2020') or row.get('tract_2010') or '').split('.')[0]
    borough = COUNTIES.get(tract[:5], '') if len(tract) == 11 and tract.isdigit() else ''
    row['emissions_borough'] = borough

    # Zero is a valid change; only fall back when change is blank/non-numeric.
    amount, source = None, ''
    for col in ('change', 'increment'):
        try:
            amount = float(row[col].replace(',', '').strip())
            source = col
            break
        except (ValueError, TypeError, KeyError):
            pass

    row['vehicle_amount_used'] = amount if amount is not None else ''
    row['amount_source'] = source

    for code, label in POLLUTANTS.items():
        column = f'estimated_{label}_change_kg_per_year'
        rate = rates.get((borough, code))
        row[column] = round(amount * rate, 6) if amount is not None and rate is not None else ''

with OUTPUT.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=original_columns + new_columns)
    writer.writeheader()
    writer.writerows(projects)

complete = sum(r['estimated_PM2.5_change_kg_per_year'] != '' for r in projects)
missing_geo = sum(not r['emissions_borough'] for r in projects)
missing_amount = sum(r['vehicle_amount_used'] == '' for r in projects)
print('Traffic input:', TRAFFIC.name)
print('Rates input:', RATES.name)
print(f'Saved {len(projects)} projects to {OUTPUT.name}')
print(f'Projects with estimates: {complete}; no borough: {missing_geo}; no change/increment: {missing_amount}')