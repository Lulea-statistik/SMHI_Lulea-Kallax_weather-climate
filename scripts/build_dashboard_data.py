from __future__ import annotations
import csv,json,math,re,html
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';DOCS=ROOT/'docs'
WEATHER_CODES_URL='https://www.smhi.se/data/hitta-data-for-en-plats/ladda-ner-vaderobservationer/presentWeather'
PARAMS={1:'Lufttemperatur',3:'Vindriktning',4:'Vindhastighet',5:'Nederbörd 1 dygn',6:'Relativ luftfuktighet',7:'Nederbörd 1 timme',8:'Snödjup',10:'Solskenstid',11:'Global irradians',12:'Sikt',13:'Rådande väder',17:'Nederbördstyp 12 timmar',18:'Nederbördstyp 24 timmar',21:'Byvind'}

def read_param(pid:int):
    rows=[];folder=DATA/f'parameter_{pid}'
    if not folder.exists():return rows
    for path in sorted(folder.glob('*.csv')):
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                dt=r.get('datetime_local') or r.get('datetime_utc') or ''
                try:d=datetime.fromisoformat(dt.replace('Z','+00:00'))
                except Exception:continue
                val=r.get('value_numeric')
                if val in (None,''):val=r.get('value')
                try:num=float(str(val).replace(',','.'))
                except Exception:continue
                rows.append((d,num))
    return rows

def read_param_raw(pid:int):
    rows=[];folder=DATA/f'parameter_{pid}'
    if not folder.exists():return rows
    for path in sorted(folder.glob('*.csv')):
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                dt=r.get('datetime_local') or r.get('datetime_utc') or ''
                try:d=datetime.fromisoformat(dt.replace('Z','+00:00'))
                except Exception:continue
                value=(r.get('value') or '').strip()
                reference=(r.get('reference') or '').strip()
                rows.append((d,value,reference))
    return rows

def mean(v):return sum(v)/len(v) if v else None
def r2(x):return None if x is None else round(x,2)
def aggregate_temp(rows):
    y=defaultdict(list);ym=defaultdict(list);daily=defaultdict(list)
    for d,v in rows:
        y[d.year].append(v);ym[(d.year,d.month)].append(v);daily[d.date()].append(v)

    daily_min={day:min(vals) for day,vals in daily.items() if vals}
    daily_max={day:max(vals) for day,vals in daily.items() if vals}
    y_daily_min=defaultdict(list);y_daily_max=defaultdict(list)
    ym_daily_min=defaultdict(list);ym_daily_max=defaultdict(list)
    for day,val in daily_min.items():
        y_daily_min[day.year].append(val);ym_daily_min[(day.year,day.month)].append(val)
    for day,val in daily_max.items():
        y_daily_max[day.year].append(val);ym_daily_max[(day.year,day.month)].append(val)

    annual=[]
    for year,vals in sorted(y.items()):
        annual.append({
            'year':year,
            'avg':r2(mean(vals)),
            'min':r2(min(vals)),
            'max':r2(max(vals)),
            'avg_daily_min':r2(mean(y_daily_min[year])),
            'avg_daily_max':r2(mean(y_daily_max[year]))
        })

    monthly=[]
    for k,vals in sorted(ym.items()):
        monthly.append({
            'year':k[0],'month':k[1],
            'avg':r2(mean(vals)),
            'min':r2(min(vals)),
            'max':r2(max(vals)),
            'avg_daily_min':r2(mean(ym_daily_min[k])),
            'avg_daily_max':r2(mean(ym_daily_max[k]))
        })
    return annual,monthly
def aggregate_mean(rows):
    y=defaultdict(list);ym=defaultdict(list)
    for d,v in rows:y[d.year].append(v);ym[(d.year,d.month)].append(v)
    return ([{'year':k,'avg':r2(mean(v))} for k,v in sorted(y.items())],[{'year':k[0],'month':k[1],'avg':r2(mean(v))} for k,v in sorted(ym.items())])
def direction_parts(vals):
    vals=[v for v in vals if v!=0]
    if not vals:return None
    s=sum(math.sin(math.radians(v)) for v in vals);c=sum(math.cos(math.radians(v)) for v in vals)
    if abs(s)<1e-12 and abs(c)<1e-12:return None
    d=math.degrees(math.atan2(s,c))%360
    if abs(d)<1e-9:d=360.0
    return {'avg':r2(d),'sin_sum':s,'cos_sum':c,'count':len(vals)}
def aggregate_direction(rows):
    y=defaultdict(list);ym=defaultdict(list)
    for d,v in rows:y[d.year].append(v);ym[(d.year,d.month)].append(v)
    annual=[];monthly=[]
    for yr,vals in sorted(y.items()):
        p=direction_parts(vals)
        if p:annual.append({'year':yr,**p})
    for k,vals in sorted(ym.items()):
        p=direction_parts(vals)
        if p:monthly.append({'year':k[0],'month':k[1],**p})
    return annual,monthly
def aggregate_direction_sectors(rows):
    names=['N','NO','O','SO','S','SV','V','NV']
    counts=defaultdict(int)
    for d,v in rows:
        if v==0:continue
        deg=v%360
        idx=int(((deg+22.5)%360)//45)
        counts[(d.year,d.month,names[idx])]+=1
    return [{'year':y,'month':m,'direction':name,'count':n} for (y,m,name),n in sorted(counts.items())]

def aggregate_daily_max_annual(rows):
    daily=defaultdict(list)
    for d,v in rows:daily[d.date()].append(v)
    yearly=defaultdict(list)
    for day,vals in daily.items():yearly[day.year].append(max(vals))
    return [{'year':yr,'max':r2(max(vals))} for yr,vals in sorted(yearly.items()) if vals]
def aggregate_precip(rows):
    y=defaultdict(float);ym=defaultdict(float)
    for d,v in rows:y[d.year]+=v;ym[(d.year,d.month)]+=v
    return ([{'year':k,'sum':r2(v)} for k,v in sorted(y.items())],[{'year':k[0],'month':k[1],'sum':r2(v)} for k,v in sorted(ym.items())])
def aggregate_max(rows):
    y=defaultdict(list);ym=defaultdict(list)
    for d,v in rows:y[d.year].append(v);ym[(d.year,d.month)].append(v)
    return ([{'year':k,'max':r2(max(v))} for k,v in sorted(y.items()) if v],[{'year':k[0],'month':k[1],'max':r2(max(v))} for k,v in sorted(ym.items()) if v])
def aggregate_sum_hours(rows):
    y=defaultdict(float);ym=defaultdict(float)
    for d,v in rows:y[d.year]+=v;ym[(d.year,d.month)]+=v
    return ([{'year':k,'hours':r2(v/3600.0)} for k,v in sorted(y.items())],[{'year':k[0],'month':k[1],'hours':r2(v/3600.0)} for k,v in sorted(ym.items())])
def aggregate_irradiance_energy(rows):
    # SMHI parameter 11 is hourly mean global irradiance in W/m2.
    # One hourly mean value integrated over one hour equals Wh/m2.
    y=defaultdict(lambda:{'sum_wh':0.0,'n':0})
    ym=defaultdict(lambda:{'sum_wh':0.0,'n':0})
    for d,v in rows:
        y[d.year]['sum_wh']+=v;y[d.year]['n']+=1
        ym[(d.year,d.month)]['sum_wh']+=v;ym[(d.year,d.month)]['n']+=1

    annual=[]
    for year,g in sorted(y.items()):
        expected=8784 if year%4==0 and (year%100!=0 or year%400==0) else 8760
        coverage=100*g['n']/expected
        annual.append({
            'year':year,
            'kwh_m2':r2(g['sum_wh']/1000.0) if coverage>=90 else None,
            'mean_w_m2':r2(g['sum_wh']/g['n']) if g['n'] else None,
            'observations':g['n'],
            'coverage_pct':r2(coverage)
        })

    monthly=[]
    import calendar
    for (year,month),g in sorted(ym.items()):
        expected=calendar.monthrange(year,month)[1]*24
        coverage=100*g['n']/expected
        monthly.append({
            'year':year,'month':month,
            'kwh_m2':r2(g['sum_wh']/1000.0) if coverage>=90 else None,
            'mean_w_m2':r2(g['sum_wh']/g['n']) if g['n'] else None,
            'observations':g['n'],
            'coverage_pct':r2(coverage)
        })
    return annual,monthly

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

def aggregate_weather(rows):
    c=defaultdict(int)
    for d,v in rows:
        code=str(int(v)) if float(v).is_integer() else str(v);c[(d.year,d.month,code)]+=1
    return [{'year':k[0],'month':k[1],'code':k[2],'count':v} for k,v in sorted(c.items())]
def precipitation_types_direct(rows):
    # SMHI direct precipitation-type observations (parameter 17/18).
    # Values may be supplied as translated text; classify conservatively.
    counts=defaultdict(int)
    for d,value,reference in rows:
        text=(' '.join([value,reference])).strip().lower()
        if not text:
            continue
        cat=None
        # Mixed must be tested before rain/snow because descriptions may contain both words.
        if ('regn' in text and 'snö' in text) or 'snöbland' in text or 'bland' in text:
            cat='mixed'
        elif 'snö' in text or 'kornsnö' in text or 'snöfall' in text or 'snöby' in text:
            cat='snow'
        elif 'regn' in text or 'duggregn' in text or 'underkyld' in text:
            cat='rain'
        elif 'hagel' in text:
            # Keep hail outside the three-way rain/snow comparison.
            cat=None
        if cat:
            counts[(d.year,d.month,cat)]+=1
    return [{'year':y,'month':m,'type':cat,'count':n} for (y,m,cat),n in sorted(counts.items())]

def precipitation_types(weather_rows,temp_rows):
    # Classify precipitation observations from SMHI present-weather codes.
    # Explicit rain/snow/mixed codes win. Only ambiguous precipitation codes
    # use the nearest temperature observation as a fallback.
    rain_codes=set([20,21,24,25,*range(50,68),*range(80,83),91,92,123,125,143,144,147,148,*range(150,167),*range(180,185),*range(250,268),280,281])
    mixed_codes=set([23,26,68,69,83,84,93,94,167,168,192,259,279,282])
    snow_codes=set([22,*range(70,80),85,86,124,145,146,*range(170,179),*range(185,188),*range(270,279),283])
    ambiguous_codes={122,140,141,142}

    temp_sorted=sorted(temp_rows,key=lambda x:x[0])
    temp_times=[d for d,_ in temp_sorted]
    from bisect import bisect_left

    def nearest_temp(dt):
        if not temp_times:return None
        i=bisect_left(temp_times,dt)
        candidates=[]
        if i<len(temp_sorted):candidates.append(temp_sorted[i])
        if i>0:candidates.append(temp_sorted[i-1])
        if not candidates:return None
        d,v=min(candidates,key=lambda x:abs((x[0]-dt).total_seconds()))
        if abs((d-dt).total_seconds())>5400:return None
        return v

    counts=defaultdict(int)
    for d,v in weather_rows:
        code=int(v) if float(v).is_integer() else None
        cat=None
        if code in mixed_codes:cat='mixed'
        elif code in rain_codes:cat='rain'
        elif code in snow_codes:cat='snow'
        elif code in ambiguous_codes:
            t=nearest_temp(d)
            if t is not None:
                cat='mixed' if -2<=t<=2 else ('snow' if t<-2 else 'rain')
        if cat:counts[(d.year,d.month,cat)]+=1
    return [{'year':y,'month':m,'type':cat,'count':n} for (y,m,cat),n in sorted(counts.items())]

def vegetation_period(rows):
    # SMHI uses +5 C as threshold for the vegetation-period climate indicator.
    # Start/end are based on a 10-year mean daily-temperature profile because
    # individual years can oscillate around the threshold.
    daily=defaultdict(list)
    for d,v in rows:
        daily[d.date()].append(v)
    daily_mean={day:mean(vals) for day,vals in daily.items() if vals}
    daily_min={day:min(vals) for day,vals in daily.items() if vals}

    # Raw annual context: number of observed days with daily mean > 5 C.
    annual=[]
    by_year=defaultdict(dict)
    for day,val in daily_mean.items():
        by_year[day.year][day]=val
    for year,daymap in sorted(by_year.items()):
        total=len(daymap)
        above=sum(1 for val in daymap.values() if val>5)
        annual.append({
            'year':year,
            'observed_days':total,
            'days_above_5':above if total>=329 else None,
            'coverage_pct':r2(100*total/(366 if year%4==0 and (year%100!=0 or year%400==0) else 365))
        })

    years=sorted(by_year)
    climate=[]
    month_days=[(m,d) for m in range(1,13) for d in range(1,32)
                if not (m==2 and d==29)
                and (m,d) not in {(2,30),(2,31),(4,31),(6,31),(9,31),(11,31)}]

    for end_year in years:
        start_year=end_year-9
        window=[y for y in years if start_year<=y<=end_year]
        if len(window)<10:
            continue

        profile=[]
        for md in month_days:
            vals=[]
            for y in window:
                try:
                    day=datetime(y,md[0],md[1]).date()
                except ValueError:
                    continue
                if day in daily_mean:
                    vals.append(daily_mean[day])
            profile.append(mean(vals) if len(vals)>=7 else None)

        # Longest contiguous run above +5 C defines the period.
        best_start=best_end=None
        best_len=0
        run_start=None
        for i,val in enumerate(profile+[None]):
            if val is not None and val>5:
                if run_start is None:
                    run_start=i
            elif run_start is not None:
                run_len=i-run_start
                if run_len>best_len:
                    best_len=run_len
                    best_start=run_start
                    best_end=i-1
                run_start=None

        if best_start is None:
            continue

        sm,sd=month_days[best_start]
        em,ed=month_days[best_end]
        # Count frost days in the calendar year represented by this climate window.
        # User-facing definition: a frost night/day is a day whose observed minimum
        # temperature falls below 0 C, restricted to the derived vegetation period.
        period_start=datetime(end_year,sm,sd).date()
        period_end=datetime(end_year,em,ed).date()
        period_days=[day for day in daily_min if period_start<=day<=period_end]
        frost_days=sum(1 for day in period_days if daily_min[day]<0)
        expected_days=(period_end-period_start).days+1
        frost_coverage=100*len(period_days)/expected_days if expected_days else 0

        climate.append({
            'window_start':start_year,
            'window_end':end_year,
            'label':f'{start_year}-{end_year}',
            'start_month':sm,'start_day':sd,
            'end_month':em,'end_day':ed,
            'start_doy':best_start+1,
            'end_doy':best_end+1,
            'length_days':best_len,
            'frost_days':frost_days if frost_coverage>=90 else None,
            'frost_coverage_pct':r2(frost_coverage),
            'threshold_c':5,
            'definition':'10-year mean daily temperature, longest continuous period > 5 C'
        })

    return {'annual_observed':annual,'climate_10y':climate}

def zero_crossings(rows):
    byday=defaultdict(list)
    for d,v in rows:byday[d.date()].append((d,v))
    out=[]
    for day,obs in sorted(byday.items()):
        obs.sort(key=lambda x:x[0]);last_sign=None;cross=0;dirs=[]
        vals=[v for _,v in obs]
        for _,v in obs:
            sign=1 if v>0 else -1 if v<0 else 0
            if sign==0:continue
            if last_sign is not None and sign!=last_sign:
                cross+=1;dirs.append('-→+' if last_sign<0 else '+→-')
            last_sign=sign
        if cross:
            out.append({'date':day.isoformat(),'year':day.year,'month':day.month,'min':r2(min(vals)),'max':r2(max(vals)),'crossings':cross,'directions':dirs,'observations':len(obs)})
    return out
def fetch_weather_labels():
    labels={}
    try:
        req=Request(WEATHER_CODES_URL,headers={'User-Agent':'SMHI-Kallax-vaderdata GitHub Action'});raw=urlopen(req,timeout=30).read().decode('utf-8','ignore')
        patterns=[r'<td[^>]*>\s*(\d{1,3})\s*</td>\s*<td[^>]*>(.*?)</td>',r'["\']?(\d{1,3})["\']?\s*[:=,]\s*["\']([^"\']{3,180})["\']',r'Kod\s*(\d{1,3})\s*</[^>]+>\s*<[^>]+>([^<]{3,180})']
        for pat in patterns:
            for code,label in re.findall(pat,raw,re.I|re.S):
                clean=html.unescape(re.sub(r'<[^>]+>',' ',label));clean=re.sub(r'\s+',' ',clean).strip()
                if clean and not clean.lower().startswith('kod '):labels.setdefault(code,clean)
    except Exception as e:print(f'Warning: could not fetch SMHI weather code labels: {e}')
    return labels
def write_daily_detail(temp,prec,prec_hourly,snow,weather):
    outdir=DOCS/'daily';outdir.mkdir(parents=True,exist_ok=True)
    byyear=defaultdict(lambda:defaultdict(lambda:{'temperature':[],'weather':[],'precipitation_hourly':[],'precipitation_mm':None,'snow_cm':None}))
    for d,v in temp:
        byyear[d.year][d.date().isoformat()]['temperature'].append({'time':d.strftime('%H:%M'),'value':r2(v)})
    precip_daily=defaultdict(float)
    for d,v in prec:precip_daily[d.date()]+=v
    for day,v in precip_daily.items():byyear[day.year][day.isoformat()]['precipitation_mm']=r2(v)
    for d,v in prec_hourly:
        byyear[d.year][d.date().isoformat()]['precipitation_hourly'].append({'time':d.strftime('%H:%M'),'value':r2(v)})
    snow_daily={}
    for d,v in snow:snow_daily[d.date()]=(d,v)
    for day,(d,v) in snow_daily.items():byyear[day.year][day.isoformat()]['snow_cm']=r2(v*100.0)
    for d,v in weather:
        code=str(int(v)) if float(v).is_integer() else str(v)
        byyear[d.year][d.date().isoformat()]['weather'].append({'time':d.strftime('%H:%M'),'code':code})
    for year,days in byyear.items():
        for day in days.values():
            day['temperature'].sort(key=lambda x:x['time'])
            day['weather'].sort(key=lambda x:x['time'])
            day['precipitation_hourly'].sort(key=lambda x:x['time'])
        (outdir/f'{year}.json').write_text(json.dumps({'year':year,'days':dict(sorted(days.items()))},ensure_ascii=False,separators=(',',':')),encoding='utf-8')

def coverage(rows,name):
    if not rows:return {'name':name,'min_date':'-','max_date':'-','rows':0}
    dates=[d for d,_ in rows];return {'name':name,'min_date':min(dates).date().isoformat(),'max_date':max(dates).date().isoformat(),'rows':len(rows)}

temp=read_param(1);wind_dir=read_param(3);wind_speed=read_param(4);prec=read_param(5);humidity=read_param(6);prec_hourly=read_param(7);snow=read_param(8);sunshine=read_param(10);irradiance=read_param(11);visibility=read_param(12);weather=read_param(13);precip_type_12=read_param_raw(17);precip_type_24=read_param_raw(18);gust=read_param(21)
temp_a,temp_m=aggregate_temp(temp);wind_s_a,wind_s_m=aggregate_mean(wind_speed);wind_d_a,wind_d_m=aggregate_direction(wind_dir);prec_a,prec_m=aggregate_precip(prec);hum_a,hum_m=aggregate_mean(humidity);vis_a,vis_m=aggregate_mean(visibility);snow_cm=[(d,v*100.0) for d,v in snow];snow_season_rows=snow_seasons(snow_cm);snow_a=[{'year':s['start_year'],'label':s['label'],'avg':s['mean_depth_cm']} for s in snow_season_rows];snow_max_a=[{'year':s['start_year'],'label':s['label'],'max':s['max_depth_cm']} for s in snow_season_rows];snow_m=[{'year':s['start_year'],'month':int(m),'avg':v} for s in snow_season_rows for m,v in s['monthly_mean_cm'].items()];snow_max_m=[{'year':s['start_year'],'month':int(m),'max':v} for s in snow_season_rows for m,v in s['monthly_max_cm'].items()];gust_max_a,gust_max_m=aggregate_max(gust);wind_max_a,wind_max_m=aggregate_max(wind_speed);sun_a,sun_m=aggregate_sum_hours(sunshine);irr_a,irr_m=aggregate_irradiance_energy(irradiance)
weather_rows=aggregate_weather(weather);used=sorted({r['code'] for r in weather_rows},key=lambda x:float(x));all_labels=fetch_weather_labels();labels={c:all_labels.get(c,f'Kod {c}') for c in used};write_daily_detail(temp,prec,prec_hourly,snow,weather)
all_years=sorted({d.year for rows in [temp,wind_dir,wind_speed,prec,humidity,snow,sunshine,irradiance,visibility,weather,gust] for d,_ in rows})
payload={'generated_at':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'station':{'id':'162860','name':'Luleå-Kallax Flygplats'},'years':all_years,
 'temperature':{'annual':temp_a,'monthly':temp_m},'precipitation':{'annual':prec_a,'monthly_total':prec_m,'types':(precipitation_types_direct(precip_type_24) or precipitation_types_direct(precip_type_12) or precipitation_types(weather,temp)),'type_source':('SMHI nederbördstyp 24 timmar' if precipitation_types_direct(precip_type_24) else ('SMHI nederbördstyp 12 timmar' if precipitation_types_direct(precip_type_12) else 'Härledd från rådande väder och temperatur'))},
 'weather':{'codes':weather_rows,'labels':labels,'source_url':WEATHER_CODES_URL},
 'wind':{'speed_annual':wind_s_a,'speed_monthly':wind_s_m,'daily_max_annual':aggregate_daily_max_annual(wind_speed),'max_annual':wind_max_a,'max_monthly':wind_max_m,'gust_max_annual':gust_max_a,'gust_max_monthly':gust_max_m,'direction_annual':wind_d_a,'direction_monthly':wind_d_m,'direction_sectors':aggregate_direction_sectors(wind_dir)},
 'visibility':{'annual':vis_a,'monthly':vis_m},'humidity':{'annual':hum_a,'monthly':hum_m},
 'snow':{'annual_mean':snow_a,'annual_max':snow_max_a,'monthly':snow_m,'monthly_max':snow_max_m,'seasons':snow_season_rows},
 'sunshine':{'station':{'id':'162015','name':'Luleå Sol'},'annual':sun_a,'monthly_total':sun_m,'irradiance_annual':irr_a,'irradiance_monthly':irr_m},
 'zero_crossings':zero_crossings(temp),
 'vegetation':vegetation_period(temp),
 'coverage':[coverage(temp,PARAMS[1]),coverage(prec,PARAMS[5]),coverage(prec_hourly,PARAMS[7]),coverage(weather,PARAMS[13]),coverage(wind_speed,PARAMS[4]),coverage(wind_dir,PARAMS[3]),coverage(gust,PARAMS[21]),coverage(visibility,PARAMS[12]),coverage(humidity,PARAMS[6]),coverage(snow,PARAMS[8]),coverage(sunshine,PARAMS[10]),coverage(irradiance,PARAMS[11]),coverage([(d,0) for d,_,_ in precip_type_12],PARAMS[17]),coverage([(d,0) for d,_,_ in precip_type_24],PARAMS[18])]}
DOCS.mkdir(exist_ok=True);(DOCS/'dashboard_data.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(f"Wrote {DOCS/'dashboard_data.json'} with {len(labels)} weather labels and {len(payload['zero_crossings'])} zero-crossing days")
