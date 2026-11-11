#!/usr/bin/env python3
"""Find real SMHI MetObs relative-humidity series in Lulea municipality.

Uses parameter 6 official station inventory and observed data, not station names
alone. Excludes Kallax from supplemental output: its long series is already in
dashboard_data.json. The NMD project's municipality polygon is GeoJSON WGS84.
"""
from __future__ import annotations
import calendar
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point, shape

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from fetch_smhi import BASE_URL, request_json, fetch_period
from build_weather_stations import clean_rows

OUT=ROOT/'docs'/'humidity_stations.json'
GEO=ROOT/'data'/'lightning'/'geography.geojson'
PID=6
PARAM={'id':'6','name':'Relativ luftfuktighet'}
MASK=json.loads(GEO.read_text(encoding='utf-8'))
MUNICIPAL=[f for f in MASK['features'] if (f.get('properties') or {}).get('class')=='municipality']
if len(MUNICIPAL)!=1:raise RuntimeError('Expected one Lulea municipal polygon')
municipality=shape(MUNICIPAL[0]['geometry'])
if municipality.is_empty or not municipality.is_valid:raise RuntimeError('Invalid municipality polygon')
if not (19<municipality.bounds[0]<25 and 64<municipality.bounds[1]<67):
    raise RuntimeError('Unexpected municipality coordinates: verify EPSG:4326')

def number(obj,*names):
    for name in names:
        v=obj.get(name)
        if v is not None:
            try:return float(str(v).replace(',','.'))
            except (ValueError,TypeError):pass
    return None

def station_inside(item):
    lon=number(item,'longitude','lon')
    lat=number(item,'latitude','lat')
    if lon is None or lat is None:return False
    if not (19<=lon<=26 and 64<=lat<=67):return False
    return municipality.covers(Point(lon,lat))

def build_series(rows):
    months=defaultdict(list)
    for dt,v in rows:
        if 0<=v<=100:
            months[(dt.year,dt.month)].append((dt,v))
    monthly=[]
    byyear=defaultdict(list)
    for (y,m),obs in sorted(months.items()):
        days=len({dt.date() for dt,_ in obs})
        expected=calendar.monthrange(y,m)[1]
        if days<max(15,int(expected*.65)):continue
        avg=round(sum(v for _,v in obs)/len(obs),2)
        monthly.append({'year':y,'month':m,'avg':avg,'days':days,'expected_days':expected,
                        'limited':days<expected-2})
        byyear[y].append(monthly[-1])
    annual=[]
    for y,items in sorted(byyear.items()):
        # Compare full-year averages only when all 12 calendar months are covered.
        # An unweighted monthly mean avoids summer/winter observation-frequency biases.
        if len(items)<12:continue
        annual.append({'year':y,'avg':round(sum(x['avg'] for x in items)/12,2),
                       'months':12,'limited':any(x['limited'] for x in items)})
    return monthly,annual

def main():
    inventory=request_json(BASE_URL+'/parameter/6.json')
    stations=inventory.get('station',[])
    if not stations:raise RuntimeError('SMHI parameter 6 inventory empty')
    candidates=[s for s in stations if station_inside(s)]
    if not candidates:raise RuntimeError('No parameter 6 stations inside Lulea geometry; check inventory schema')
    existing={}
    if OUT.exists():
        old=json.loads(OUT.read_text(encoding='utf-8'))
        existing={str(s['id']):s for s in old.get('stations',[])}
    found=[];audit=[];failures=[]
    for st in sorted(candidates,key=lambda v:str(v.get('name') or '')):
        sid=str(st.get('key') or st.get('id') or '')
        if not sid:continue
        name=str(st.get('name') or sid)
        if sid=='162860':
            audit.append({'id':sid,'name':name,'status':'existing-dashboard'})
            continue
        raw=[];errors=[]
        for period in ('corrected-archive','latest-months'):
            try:
                part,_,_=fetch_period(PARAM,{'id':sid,'name':name},period)
                raw.extend(part)
            except Exception as e:
                errors.append(period+': '+str(e)[:250])
        observations=clean_rows(raw,PID)
        monthly,annual=build_series(observations)
        item={'id':sid,'name':name,'monthly':monthly,'annual':annual,
              'latitude':number(st,'latitude','lat'),'longitude':number(st,'longitude','lon'),
              'parameter_id':PID}
        previous=existing.get(sid)
        if previous and len(previous.get('monthly',[]))>len(monthly):
            item=previous
            audit.append({'id':sid,'name':name,'status':'retained previous longer series',
                          'months':len(item['monthly']),'warnings':errors})
        elif monthly:
            audit.append({'id':sid,'name':name,'status':'observed','records':len(observations),
                          'months':len(monthly),'complete_years':len(annual),'warnings':errors})
        else:
            audit.append({'id':sid,'name':name,'status':'no usable humidity observations',
                          'records':len(observations),'warnings':errors})
        if item.get('monthly'):found.append(item)
        if errors and not observations and not previous:
            failures.append(name+': '+'; '.join(errors))
        print(name,sid,'monthly=',len(monthly),'annual=',len(annual),'warnings=',len(errors),flush=True)
    if failures:
        # Do not publish a misleading inventory while a station could not be inspected.
        raise RuntimeError('Incomplete humidity station audit: '+'; '.join(failures))
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'source':BASE_URL+'/parameter/6.json',
            'parameter_id':6,'municipality':'Luleå','geography_crs':'EPSG:4326',
            'method':'SMHI parameter 6 official station list, WGS84 polygon test, corrected archive and latest months; monthly >=65% observed days and >=15 days; yearly all 12 months',
            'stations':found,'audit':audit}
    OUT.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Verified extra humidity stations:',[(x['id'],x['name'],len(x['monthly'])) for x in found],flush=True)
if __name__=='__main__':main()
