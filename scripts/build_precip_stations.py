#!/usr/bin/env python3
"""Build comparable station precipitation series from SMHI MetObs parameter 5 (24h sum).
Only completed, sufficiently observed months are published. Never equate missing with zero.
"""
import calendar
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from fetch_smhi import fetch_period

STATIONS=[
    {'id':'162860','name':'Luleå-Kallax Flygplats'},
    {'id':'161680','name':'Sunderbyn'},
    {'id':'162960','name':'Råneå'},
    {'id':'161900','name':'Klöverträsk D'},
    {'id':'162790','name':'Rödkallen A'},
    {'id':'162970','name':'Högsön'},
    {'id':'162980','name':'Orrbyn'},
    {'id':'162990','name':'Niemisel'},
]
PARAM={'id':'5','name':'Nederbördsmängd per dygn'}
OUT=ROOT/'docs'/'precip_stations.json'

def main():
    now=datetime.now(timezone.utc)
    station_data={}
    warnings=[]
    for station in STATIONS:
        daily={}
        for period in ('corrected-archive','latest-months'):
            try:
                rows,_,_=fetch_period(PARAM,station,period)
                for row in rows:
                    raw=row.get('value_numeric') or row.get('value')
                    if raw in (None,''):continue
                    try:
                        d=datetime.fromisoformat(row['datetime_local']).date()
                        v=float(str(raw).replace(',','.'))
                    except (ValueError,TypeError,KeyError):continue
                    if v<0:continue
                    # Parameter 5: 24-hour total, reported on observation date.
                    # Historical consistency: aggregate by reporting calendar month.
                    daily[d.isoformat()]=v
            except Exception as exc:
                warnings.append(f"{station['name']} {period}: {exc}")
        groups=defaultdict(list)
        for dt,v in daily.items():
            y,m=map(int,dt[:7].split('-'))
            groups[(y,m)].append(v)
        monthly=[]
        for (y,m),values in sorted(groups.items()):
            count=len(values)
            days=calendar.monthrange(y,m)[1]
            if (y,m)>=(now.year,now.month):continue
            if count<days-2:continue
            monthly.append({'year':y,'month':m,'sum':round(sum(values),2),'days':count,'expected_days':days})
        station_data[station['id']]={'id':station['id'],'name':station['name'],'monthly':monthly}
        print(station['name'],len(daily),'daily observations',len(monthly),'complete months')
    groups=defaultdict(list)
    for st in station_data.values():
        for item in st['monthly']:
            groups[(item['year'],item['month'])].append(item['sum'])
    municipal=[{'year':y,'month':m,'sum':round(sum(vals)/len(vals),2),'stations':len(vals)}
               for (y,m),vals in sorted(groups.items())]
    payload={'generated_at':now.isoformat(),'parameter_id':5,'method':'Oviktat stationsmedel av kompletta månadsdygnssummor',
             'required_days':'Minst antal kalenderdagar minus 2; innevarande månad exkluderas',
             'stations':list(station_data.values()),'municipal':municipal,'warnings':warnings}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('Wrote',OUT,len(municipal),'municipal months')
    if not municipal:raise RuntimeError('No usable station months: refusing empty output')

if __name__=='__main__':main()
