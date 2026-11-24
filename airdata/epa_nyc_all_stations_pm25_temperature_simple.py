import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
EMAIL, KEY = os.getenv('EPA_AQS_EMAIL'), os.getenv('EPA_AQS_KEY')
if not EMAIL or not KEY:
    raise SystemExit('Put EPA_AQS_EMAIL and EPA_AQS_KEY in .env')

OUT = ROOT / 'epa_nyc_monthly_pm25_temperature'
OUT.mkdir(exist_ok=True)
CACHE = ROOT / 'epa_top5_simple_results'  # Shared with the Top 5 program.
CACHE.mkdir(exist_ok=True)
API = 'https://aqs.epa.gov/data/api/dailyData/byCounty'
COUNTIES = {'005': 'Bronx', '047': 'Brooklyn', '061': 'Manhattan',
            '081': 'Queens', '085': 'Staten Island'}
YEARS = range(2016, 2027)
last_call = 0.0


def fetch(year, county, code):
    """Download a county/year only once, then use its cached JSON."""
    global last_call
    name = f'epa_{year}_{county}'
    file = CACHE / (name + ('.json' if code == '88101' else '_temperature.json'))
    if not file.exists() and code == '88101':
        old = ROOT / 'epa_nyc_monthly_air_quality' / 'cache' / f'{name}_88101.json'
        if old.exists():
            file = old
    if file.exists():
        return json.loads(file.read_text(encoding='utf-8'))

    time.sleep(max(0, 6.5 - (time.monotonic() - last_call)))
    last_call = time.monotonic()
    print(f'  Download {year} {COUNTIES[county]} ({code})', flush=True)
    response = requests.get(API, params={
        'email': EMAIL, 'key': KEY, 'param': code,
        'bdate': f'{year}0101', 'edate': f'{year}0930' if year == 2026 else f'{year}1231',
        'state': '36', 'county': county,
    }, timeout=90)
    response.raise_for_status()
    payload = response.json()
    header = payload.get('Header') or [{}]
    status = str(header[0].get('status', 'Success')).lower()
    if status != 'success' and 'no data' not in status:
        raise RuntimeError(f'EPA API returned: {status}')
    rows = payload.get('Data', [])
    if not isinstance(rows, list):
        raise RuntimeError('Unexpected EPA API response')
    target = CACHE / (name + ('.json' if code == '88101' else '_temperature.json'))
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(rows), encoding='utf-8')
    temporary.replace(target)
    return rows


def monthly(year, code):
    """Mean of daily values for each monitoring site and month."""
    records = []
    for county, borough in COUNTIES.items():
        for r in fetch(year, county, code):
            duration = str(r.get('sample_duration', '')).upper()
            if code == '88101' and '24' not in duration:
                continue
            if code == '62101' and 'HOUR' not in duration and 'HR' not in duration:
                continue
            try:
                value = float(r['arithmetic_mean'])
                if code == '88101' and value < 0:
                    continue
                if code == '62101':
                    unit = str(r.get('units_of_measure', '')).lower()
                    if 'fahrenheit' in unit:
                        value = (value - 32) * 5 / 9
                    elif 'centigrade' not in unit and 'celsius' not in unit:
                        continue
                if not pd.notna(value) or value in (float('inf'), float('-inf')):
                    continue
                day = pd.Timestamp(r['date_local'])
            except (KeyError, ValueError, TypeError):
                continue
            records.append({
                'county': county, 'borough': borough,
                'site': str(r['site_number']).zfill(4),
                'station': r.get('local_site_name') or f'{borough} site {r["site_number"]}',
                'day': day, 'poc': r.get('poc', 1),
                'duration': duration, 'value': value,
            })
    if not records:
        return pd.DataFrame(columns=['county', 'site', 'month',
                                     'pm25' if code == '88101' else 'temperature'])
    df = pd.DataFrame(records)
    keys = ['county', 'site']
    if code == '62101':
        hourly = df['duration'].str.contains('1 HOUR|1-HR', regex=True).astype(int)
        df = df[hourly == hourly.groupby([df['county'], df['site'], df['day']]).transform('max')]
    monitors = df.groupby(keys + ['day', 'poc'], as_index=False)['value'].mean()
    days = monitors.groupby(keys + ['day'], as_index=False)['value'].mean()
    days['month'] = days['day'].dt.month
    name = 'pm25' if code == '88101' else 'temperature'
    result = days.groupby(keys + ['month'], as_index=False).agg(
        **{name: ('value', 'mean'), name + '_days': ('day', 'nunique')})
    if code == '88101':
        stations = df.groupby(keys, as_index=False)[['borough', 'station']].first()
        result = result.merge(stations, on=keys)
    return result


def main():
    yearly = []
    for year in YEARS:
        print(f'Processing {year}...', flush=True)
        pm = monthly(year, '88101')
        temp = monthly(year, '62101')
        if pm.empty and temp.empty:
            continue
        merged = pm.merge(temp[['county', 'site', 'month', 'temperature']],
                          on=['county', 'site', 'month'], how='outer')
        merged.insert(0, 'year', year)
        yearly.append(merged)

    if not yearly:
        raise SystemExit('No PM2.5 data returned by EPA.')
    values = pd.concat(yearly, ignore_index=True)
    stations = values.dropna(subset=['station'])[['county', 'site', 'borough', 'station']].drop_duplicates(['county', 'site'])
    months = pd.DataFrame([(y, m) for y in YEARS for m in range(1, 10 if y == 2026 else 13)],
                          columns=['year', 'month'])
    # Include blank months for a station that has no PM2.5 observations.
    result = stations.merge(months, how='cross').merge(
        values[['year', 'month', 'county', 'site', 'pm25', 'temperature', 'pm25_days']],
        on=['year', 'month', 'county', 'site'], how='left')
    result['pm25_days'] = result['pm25_days'].fillna(0).astype(int)
    result = result[['year', 'month', 'county', 'borough', 'site', 'station',
                     'pm25', 'temperature', 'pm25_days']]
    result = result.sort_values(['year', 'month', 'borough', 'site'])
    output = OUT / 'epa_nyc_all_stations_monthly_2016_sep2026.csv'
    result.to_csv(output, index=False, na_rep='')
    print(f'Done: {len(result)} rows saved to {output}', flush=True)


if __name__ == '__main__':
    main()
