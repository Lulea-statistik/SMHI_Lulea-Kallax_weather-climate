#!/usr/bin/env python3
"""Probe SMHI MetObs air pressure (parameter 9) for Lulea precipitation stations.

The active/default Lulea-Kallax archive is already in data/parameter_9/*.csv.
All other stations are admitted ONLY after the official parameter-9 inventory
lists them and their own observations pass basic completeness checks.
"""
from __future__ import annotations

import calendar
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from fetch_smhi import BASE_URL, fetch_period, request_json
from build_precip_stations import STATIONS

OUT = ROOT / 'docs' / 'pressure_stations.json'
PARAM = {'id': '9', 'name': 'Lufttryck reducerat till havsytans nivå'}
SOURCE = BASE_URL + '/parameter/9.json'

def numeric_rows(rows):
    observations = {}
    for r in rows:
        try:
            dt = datetime.fromisoformat(str(r['datetime_local']).replace('Z', '+00:00'))
            pressure = float(str(r.get('value_numeric') or r.get('value')).replace(',', '.'))
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(pressure) or not 850 <= pressure <= 1100:
            continue
        observations[dt.isoformat()] = (dt, pressure)
    return list(observations.values())

def local_kallax_rows():
    rows = []
    for path in sorted((ROOT / 'data' / 'parameter_9').glob('*.csv')):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows.extend(csv.DictReader(handle))
    return rows

def aggregates(raw):
    groups = defaultdict(list)
    for dt, pressure in numeric_rows(raw):
        groups[(dt.year, dt.month)].append((dt, pressure))
    monthly = []
    for (y, m), observations in sorted(groups.items()):
        days = len({d.date() for d, _ in observations})
        expected = calendar.monthrange(y, m)[1]
        # Exclude months where most days were not observed, but allow historic
        # synoptic observations (e.g., only 3 per day) without weighting them
        # as if they were hourly measurements.
        if days < max(15, math.ceil(expected * .65)):
            continue
        avg = sum(p for _, p in observations) / len(observations)
        monthly.append({'year': y, 'month': m, 'avg': round(avg, 2),
                        'min': round(min(p for _, p in observations), 2),
                        'max': round(max(p for _, p in observations), 2),
                        'days': days, 'expected_days': expected,
                        'observations': len(observations)})
    yearly = defaultdict(list)
    for row in monthly:
        yearly[row['year']].append(row)
    annual = []
    for y, months in sorted(yearly.items()):
        if len(months) < 9:
            continue
        # Equal weight for each sufficiently observed month, not hourly count.
        annual.append({'year': y, 'avg': round(sum(m['avg'] for m in months) / len(months), 2),
                       'months': len(months),
                       'min': min(m['min'] for m in months),
                       'max': max(m['max'] for m in months)})
    return annual, monthly, len(numeric_rows(raw))

def main():
    inventory = request_json(SOURCE)
    stations = inventory.get('station', []) if isinstance(inventory, dict) else []
    if not stations:
        raise RuntimeError('Official parameter-9 station inventory unavailable: cannot verify additional stations')
    byid = {str(st.get('key') or st.get('id') or ''): st for st in stations}
    print('SMHI parameter-9 inventory: ', len(byid), 'stations', flush=True)
    result = []
    audit = []
    for station in STATIONS:
        sid, name = station['id'], station['name']
        status = {'id': sid, 'name': name, 'listed_for_pressure': sid in byid}
        rows = []
        if sid == '162860':
            rows = local_kallax_rows()
            status['probe'] = 'local SMHI parameter-9 historical archive'
        elif sid in byid:
            print('Testing other Lulea station:', sid, name, flush=True)
            for period in ('corrected-archive', 'latest-months'):
                try:
                    part, _, _ = fetch_period(PARAM, station, period)
                    rows.extend(part)
                    print(' ', period, len(part), 'records', flush=True)
                except Exception as exc:
                    status[period + '_error'] = str(exc)[:300]
                    print(' ', period, 'unavailable:', str(exc)[:160], flush=True)
            status['probe'] = 'SMHI parameter-9 station inventory + observed values'
        else:
            status['probe'] = 'not listed for SMHI parameter 9'
        annual, monthly, count = aggregates(rows)
        status['observations'] = count
        status['complete_months'] = len(monthly)
        status['annual_years'] = len(annual)
        audit.append(status)
        if monthly:
            result.append({'id': sid, 'name': name,
                           'is_kallax': sid == '162860',
                           'annual': annual, 'monthly': monthly})
        print(sid, name, 'valid pressure observations', count,
              'complete months', len(monthly), 'years', len(annual), flush=True)

    if not any(s['id'] == '162860' and s['annual'] for s in result):
        raise RuntimeError('Missing verified Kallax pressure history')
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': 'SMHI MetObs, parameter 9, air pressure reduced to sea level',
        'unit': 'hPa', 'default_station': '162860',
        'method': 'Monthly average of observations with at least 65% observed days (minimum 15); '
                  'annual mean of monthly means if at least nine valid months. '
                  'Stations are not assumed to measure pressure merely because they measure precipitation.',
        'stations': result, 'station_audit': audit,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')
    print('Saved', OUT, 'verified stations', [s['name'] for s in result], flush=True)

if __name__ == '__main__':
    main()
