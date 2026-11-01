import calendar
import json
import os
import time
from pathlib import Path

import sys
print("Python location:", sys.executable)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
EMAIL, KEY = os.getenv('EPA_AQS_EMAIL'), os.getenv('EPA_AQS_KEY')
if not EMAIL or not KEY:
    raise SystemExit('Put EPA_AQS_EMAIL and EPA_AQS_KEY in .env')

OUT = ROOT / 'epa_top5_simple_results'
OUT.mkdir(exist_ok=True)
API = 'https://aqs.epa.gov/data/api/dailyData/byCounty'
COUNTIES = {'005': 'Bronx', '047': 'Brooklyn', '061': 'Manhattan',
            '081': 'Queens', '085': 'Staten Island'}
YEARS = range(2016, 2027)
last_call = 0.0


def fetch(year, county, code):
    global last_call
    name = f'epa_{year}_{county}'
    cache = OUT / (name + ('.json' if code == '88101' else '_temperature.json'))
    if not cache.exists() and code == '88101':
        old = ROOT / 'epa_nyc_monthly_air_quality' / 'cache' / f'{name}_88101.json'
        if old.exists():
            cache = old
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))

    time.sleep(max(0, 6.5 - (time.monotonic() - last_call)))
    last_call = time.monotonic()
    print(f'  Fetching {year} {COUNTIES[county]} ({code})', flush=True)
    response = requests.get(API, params={
        'email': EMAIL, 'key': KEY, 'param': code,
        'bdate': f'{year}0101', 'edate': f'{year}0930' if year == 2026 else f'{year}1231',
        'state': '36', 'county': county,
    }, timeout=90)
    response.raise_for_status()
    result = response.json()
    rows = result.get('Data', [])
    target = OUT / (name + ('.json' if code == '88101' else '_temperature.json'))
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(rows), encoding='utf-8')
    temp.replace(target)
    return rows


def monthly(year, code):
    """One site/day value first, then a monthly mean at that same site."""
    records = []
    for county, borough in COUNTIES.items():
        for r in fetch(year, county, code):
            duration = str(r.get('sample_duration', '')).upper()
            if code == '88101' and '24' not in duration:
                continue
            if code == '62101' and not ('HOUR' in duration or 'HR' in duration):
                continue
            try:
                value = float(r['arithmetic_mean'])
                if code == '88101' and value < 0:
                    continue
                if code == '62101':
                    continue
                if not pd.notna(value) or value in (float('inf'), float('-inf')):
                    continue
                day = pd.Timestamp(r['date_local'])
            except (KeyError, TypeError, ValueError):
                continue
            records.append({
                'county': county, 'borough': borough,
                'site': str(r['site_number']).zfill(4),
                'station': r.get('local_site_name') or f'{borough} site {r["site_number"]}',
                'day': day, 'poc': r.get('poc', 1), 'value': value,
                'duration': duration,
            })

    if not records:
        return pd.DataFrame(columns=['county', 'site', 'month',
                                     #creates a column for pm or temp/ deals with empty data by putting nothing
                                     'pm25' if code == '88101' else 'temperature'])
    df = pd.DataFrame(records)
    keys = ['county', 'site']
    if code == '62101':
        df['priority'] = df['duration'].str.contains('1 HOUR|1-HR', regex=True).astype(int)
        df = df[df['priority'] == df.groupby(keys + ['day'])['priority'].transform('max')]
    monitors = df.groupby(keys + ['day', 'poc'], as_index=False)['value'].mean()
    daily = monitors.groupby(keys + ['day'], as_index=False)['value'].mean()
    daily['month'] = daily['day'].dt.month
    name = 'pm25' if code == '88101' else 'temperature'
    result = daily.groupby(keys + ['month'], as_index=False).agg(
        **{name: ('value', 'mean'), name + '_days': ('day', 'nunique')})
    if code == '88101':  #adds the new data into result dataframe
        sites = df.groupby(keys, as_index=False)[['borough', 'station']].first()
        result = result.merge(sites, on=keys)
    return result


def make_graph(year, data):
    top = data.sort_values('pm25', ascending=False).groupby('month').head(5)
    fig, axes = plt.subplots(4, 3, figsize=(21, 19))
    for month, ax in enumerate(axes.flat, 1):
        if year == 2026 and month > 9:
            ax.axis('off')
            continue
        best = top[top['month'] == month].sort_values('pm25')
        ax.set_title(calendar.month_name[month])
        if best.empty:
            ax.text(.5, .5, 'No PM2.5 data', ha='center', transform=ax.transAxes)
            continue
        labels = [f'{r.station[:23]} ({r.borough})' for r in best.itertuples()]
        bars = ax.barh(labels, best['pm25'])
        limit = best['pm25'].max() * 1.65
        ax.set_xlim(0, limit or 1)
        for bar, r in zip(bars, best.itertuples()):
            ax.text(bar.get_width() + limit * .02,
                    bar.get_y() + bar.get_height() / 2,
                    f'{r.pm25:.2f} ({r.pm25_days} days)', va='center', fontsize=9)
        ax.tick_params(axis='y', labelsize=8)
    fig.suptitle(f'NYC EPA Top 5 Monthly PM2.5 — {year}', fontsize=20)
    fig.text(.5, .02, 'PM2.5 in µg/m³; no minimum measurement-day requirement.', ha='center')
    fig.subplots_adjust(left=.19, right=.98, top=.95, bottom=.055, hspace=.6, wspace=.8)
    fig.savefig(OUT / f'epa_top5_{year}.png', dpi=150)
    plt.close(fig)


def main():
    results = []
    for year in YEARS:
        print(f'Year {year}...')
        pm = monthly(year, '88101')
        temp = monthly(year, '62101')
        if pm.empty:
            continue
        joined = pm.merge(temp[['county', 'site', 'month', 'temperature']],
                          on=['county', 'site', 'month'], how='left')
        joined.insert(0, 'year', year)
        results.append(joined)
        make_graph(year, joined)
        all_sites = pd.concat(results, ignore_index=True)
        all_sites.to_csv(OUT / 'all_station_monthly_means.csv', index=False)
        top5 = all_sites.sort_values('pm25', ascending=False).groupby(['year', 'month']).head(5)
        top5.to_csv(OUT / 'top5_by_month.csv', index=False)
    print(f'Done. Check {OUT}')


if __name__ == '__main__':
    main()
