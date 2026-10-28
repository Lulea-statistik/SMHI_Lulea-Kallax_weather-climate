#!/usr/bin/env python3
"""Probe other known Lulea stations against official SMHI MetObs inventories.

Only verified observations are admitted to station menus. The complete Kallax
series remains in the existing dashboard_data.json and is never overwritten.
"""
from __future__ import annotations
import calendar
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from fetch_smhi import BASE_URL,fetch_period,request_json
from build_precip_stations import STATIONS

OUT=ROOT/'docs'/'weather_stations.json'
PARAMETERS={1:'Lufttemperatur',3:'Vindriktning',4:'Vindhastighet',21:'Byvind',8:'Snödjup'}

def mean(v):return sum(v)/len(v) if v else None
def r2(x):return None if x is None else round(x,2)
def snow_seasons(rows_cm):
    # Project definition for a stable snow-cover season at Kallax:
    # season year = August-July; start/end require 7 consecutive available
    # observations with snow depth >= 1 cm and no observation gap > 3 days.
    # Mean and maximum snow depth are then calculated from all available
    # observations inside the resulting continuous season, including temporary
    # thaws below 1 cm.
    by_season=defaultdict(dict)
    for d,v in rows_cm:
        season_start=d.year if d.month>=8 else d.year-1
        day=d.date()
        by_season[season_start][day]=max(v,by_season[season_start].get(day,float('-inf')))

    def stable_start(obs,window=7,threshold_cm=1.0,max_gap_days=3):
        for i in range(0,len(obs)-window+1):
            seq=obs[i:i+window]
            if all(val>=threshold_cm for _,val in seq) and all((seq[j][0]-seq[j-1][0]).days<=max_gap_days for j in range(1,len(seq))):
                return seq[0][0]
        return None

    def stable_end(obs,window=7,threshold_cm=1.0,max_gap_days=3):
        for i in range(len(obs)-window,-1,-1):
            seq=obs[i:i+window]
            if all(val>=threshold_cm for _,val in seq) and all((seq[j][0]-seq[j-1][0]).days<=max_gap_days for j in range(1,len(seq))):
                return seq[-1][0]
        return None

    out=[]
    for start_year,daymap in sorted(by_season.items()):
        obs=sorted(daymap.items())
        first=stable_start(obs)
        last=stable_end(obs)
        if not first or not last or last<first:
            continue
        in_season=[(day,val) for day,val in obs if first<=day<=last]
        if not in_season:
            continue
        vals=[val for _,val in in_season]
        month_vals=defaultdict(list)
        for day,val in in_season:
            month_vals[day.month].append(val)
        monthly_mean={str(m):r2(mean(vs)) for m,vs in sorted(month_vals.items())}
        monthly_max={str(m):r2(max(vs)) for m,vs in sorted(month_vals.items())}
        out.append({
            'start_year':start_year,
            'end_year':start_year+1,
            'label':f'{start_year}/{str(start_year+1)[-2:]}',
            'first_snow':first.isoformat(),
            'last_snow':last.isoformat(),
            'length_days':(last-first).days+1,
            'observed_days':len(vals),
            'snow_days_observed':sum(1 for val in vals if val>=1.0),
            'mean_depth_cm':r2(mean(vals)),
            'max_depth_cm':r2(max(vals)),
            'monthly_mean_cm':monthly_mean,
            'monthly_max_cm':monthly_max,
            'definition':'7 consecutive available observations >= 1 cm, max 3-day gap; mean/max within continuous season'
        })
    return out


def clean_rows(raw,parameter):
    seen={}
    for row in raw:
        try:
            dt=datetime.fromisoformat(str(row['datetime_local']).replace('Z','+00:00'))
            val=row.get('value_numeric') if row.get('value_numeric') not in (None,'') else row.get('value')
            v=float(str(val).replace(',','.'))
            if not math.isfinite(v):continue
            if parameter==1 and not -65<=v<=45:continue
            if parameter in (4,21) and not 0<=v<=80:continue
            if parameter==3 and not 0<=v<=360:continue
            if parameter==8 and not 0<=v<=4:continue
            seen[dt.isoformat()]=(dt,v)
        except (ValueError,TypeError,KeyError):
            continue
    return sorted(seen.values())

def coverage_months(rows,min_fraction=.65):
    bymonth=defaultdict(list)
    for dt,v in rows:
        bymonth[(dt.year,dt.month)].append((dt,v))
    good={}
    for (year,month),vals in bymonth.items():
        observed=len({dt.date() for dt,_ in vals})
        expected=calendar.monthrange(year,month)[1]
        if observed>=max(15,math.ceil(expected*min_fraction)):
            good[(year,month)]=vals
    return good

def temp_data(rows):
    months=coverage_months(rows)
    monthly=[]
    byyear=defaultdict(list)
    for (year,month),observations in sorted(months.items()):
        vals=[v for _,v in observations]
        byday=defaultdict(list)
        for dt,v in observations:byday[dt.date()].append(v)
        r={'year':year,'month':month,'avg':r2(mean(vals)),
           'min':r2(min(vals)),'max':r2(max(vals)),
           'avg_daily_min':r2(mean([min(v) for v in byday.values()])),
           'avg_daily_max':r2(mean([max(v) for v in byday.values()])),
           'days':len(byday)}
        monthly.append(r);byyear[year].append(r)
    annual=[]
    for year,monthrows in sorted(byyear.items()):
        if len(monthrows)<9:continue
        annual.append({'year':year,
          'avg':r2(mean([m['avg'] for m in monthrows])),
          'min':min(m['min'] for m in monthrows),'max':max(m['max'] for m in monthrows),
          'avg_daily_min':r2(mean([m['avg_daily_min'] for m in monthrows])),
          'avg_daily_max':r2(mean([m['avg_daily_max'] for m in monthrows])),
          'months':len(monthrows)})
    return {'annual':annual,'monthly':monthly}

def wind_data(raw):
    speed,direction,gust=raw[4],raw[3],raw[21]
    sm,dm,gm=coverage_months(speed),coverage_months(direction),coverage_months(gust)
    good=set(sm)&set(dm)
    if not good:return None
    sectors=['N','NO','O','SO','S','SV','V','NV']
    sr=defaultdict(list);dr=defaultdict(list);gr=defaultdict(list)
    sector_counts=defaultdict(int)
    for (year,month) in good:
        s=sm[(year,month)];d=dm[(year,month)]
        sr[(year,month)]=s;dr[(year,month)]=d
        if (year,month) in gm:gr[(year,month)]=gm[(year,month)]
        for _,degree in d:
            if degree==0:continue
            sector=sectors[int(((degree%360+22.5)%360)//45)]
            sector_counts[(year,month,sector)]+=1
    def direction_mean(rows):
        angles=[v for _,v in rows if v!=0]
        if not angles:return None
        sin=sum(math.sin(math.radians(x)) for x in angles)
        cos=sum(math.cos(math.radians(x)) for x in angles)
        if abs(sin)<1e-10 and abs(cos)<1e-10:return None
        return {'avg':r2(math.degrees(math.atan2(sin,cos))%360),
                'sin_sum':sin,'cos_sum':cos,'count':len(angles)}
    def group(which):
        monthly=[];yearly=defaultdict(list)
        for (y,m),vals in sorted(which.items()):
            values=[v for _,v in vals]
            if not values:continue
            monthly.append({'year':y,'month':m,'avg':r2(mean(values)),'max':r2(max(values))})
            yearly[y].extend(vals)
        annual=[]
        for year,vals in sorted(yearly.items()):
            if sum(1 for x in which if x[0]==year)<9:continue
            values=[v for _,v in vals]
            annual.append({'year':year,'avg':r2(mean(values)),'max':r2(max(values))})
        return annual,monthly
    speed_a,speed_m=group(sr);gust_a,gust_m=group(gr)
    direction_a=[];direction_m=[]
    for (y,m),vals in sorted(dr.items()):
        d=direction_mean(vals)
        if d:direction_m.append({'year':y,'month':m,**d})
    byyear=defaultdict(list)
    for (y,m),vals in dr.items():byyear[y].extend(vals)
    for y,vals in sorted(byyear.items()):
        if sum(1 for x in dr if x[0]==y)<9:continue
        d=direction_mean(vals)
        if d:direction_a.append({'year':y,**d})
    sectors_data=[{'year':y,'month':m,'direction':label,'count':n}
                  for (y,m,label),n in sorted(sector_counts.items())]
    if not speed_a or not direction_a:return None
    # Reconstruct page-specific annual and monthly maximum wind statistics.
    max_a=[{'year':v['year'],'max':v['max']} for v in speed_a]
    max_m=[{'year':v['year'],'month':v['month'],'max':v['max']} for v in speed_m]
    return {'speed_annual':speed_a,'speed_monthly':speed_m,
            'max_annual':max_a,'max_monthly':max_m,
            'gust_max_annual':[{'year':v['year'],'max':v['max']} for v in gust_a],
            'gust_max_monthly':[{'year':v['year'],'month':v['month'],'max':v['max']} for v in gust_m],
            'direction_annual':direction_a,'direction_monthly':direction_m,
            'direction_sectors':sectors_data}

def snow_data(rows):
    seasons=[r for r in snow_seasons([(dt,v*100) for dt,v in rows]) if r['observed_days']>=50]
    if not seasons:return None
    annual=[{'year':s['start_year'],'label':s['label'],'avg':s['mean_depth_cm']} for s in seasons]
    maximum=[{'year':s['start_year'],'label':s['label'],'max':s['max_depth_cm']} for s in seasons]
    monthly=[{'year':s['start_year'],'month':int(m),'avg':v}
             for s in seasons for m,v in s['monthly_mean_cm'].items()]
    return {'annual_mean':annual,'annual_max':maximum,'monthly':monthly,'seasons':seasons}

def main():
    inventory={}
    for pid in PARAMETERS:
        raw=request_json(BASE_URL+f'/parameter/{pid}.json')
        items=raw.get('station',[]) if isinstance(raw,dict) else []
        if not items:raise RuntimeError(f'No SMHI station inventory for parameter {pid}')
        inventory[pid]={str(i.get('key') or i.get('id') or '') for i in items}
        print('Parameter',pid,'listed stations',len(inventory[pid]),flush=True)
    station_output={'temperature':[],'wind':[],'snow':[]}
    audit=[]
    for st in STATIONS:
        sid,name=st['id'],st['name']
        avail={str(pid):sid in inventory[pid] for pid in PARAMETERS}
        status={'id':sid,'name':name,'parameters_listed':avail,'records':{},'errors':{}}
        if sid=='162860':
            station_output['temperature'].append({'id':sid,'name':name,'source':'existing-dashboard'})
            station_output['wind'].append({'id':sid,'name':name,'source':'existing-dashboard'})
            station_output['snow'].append({'id':sid,'name':name,'source':'existing-dashboard'})
            status['verified']=['temperature','wind','snow']
            audit.append(status)
            continue
        records={}
        for pid in PARAMETERS:
            if sid not in inventory[pid]:
                records[pid]=[];continue
            raw=[]
            for period in ['corrected-archive','latest-months']:
                try:
                    part,_,_=fetch_period({'id':str(pid),'name':PARAMETERS[pid]},st,period)
                    raw.extend(part)
                except Exception as exc:
                    status['errors'][str(pid)+'/'+period]=str(exc)[:180]
            records[pid]=clean_rows(raw,pid)
            status['records'][str(pid)]=len(records[pid])
        td=temp_data(records[1]) if records[1] else None
        wd=wind_data(records) if records[3] and records[4] else None
        sd=snow_data(records[8]) if records[8] else None
        status['verified']=[]
        for kind,aggregates in [('temperature',td),('wind',wd),('snow',sd)]:
            if aggregates is None:continue
            station_output[kind].append({'id':sid,'name':name,**aggregates})
            status['verified'].append(kind)
        audit.append(status)
        print(name, 'records:',status['records'],'verified:',status['verified'],flush=True)
    if any(not any(x['id']=='162860' for x in station_output[k]) for k in station_output):
        raise RuntimeError('Kallax default is missing')
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),
             'default_station':'162860',
             'source':'SMHI MetObs official parameter station inventories, corrected archives and latest months',
             'method':'Only proven observations; temperature/wind require at least 65% observed days per month and nine valid months per year; snow uses the Kallax seven-observation season rule. Missing stations are never interpolated.',
             'stations':station_output,'audit':audit}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Saved',OUT,'stations:',{k:[s['name'] for s in v] for k,v in station_output.items()},flush=True)

if __name__=='__main__':main()
