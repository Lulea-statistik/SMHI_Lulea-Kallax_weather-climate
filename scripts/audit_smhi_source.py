"""Independent read-only audit of SMHI archive versus local observations and dashboard.
Does not import the project's SMHI parser or change any observation files.
"""
import csv, io, json, math, calendar, statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
BASE='https://opendata-download-metobs.smhi.se/api/version/latest'
TZ=ZoneInfo('Europe/Stockholm')
STATION='162860'
SPECS={1:('temperature','monthly','avg',statistics.mean),5:('precipitation','monthly_total','sum',math.fsum),21:('wind','gust_max_monthly','max',max)}
GAPS={5:list(range(2003,2012)),21:[2014,2015]}
SAMPLES=[(2020,1),(2023,7),(2024,2),(2025,10)]
OUT=ROOT/'audit-output'
OUT.mkdir(exist_ok=True)
dashboard=json.loads((ROOT/'docs/dashboard_data.json').read_text())
report={'station':STATION,'checked_at':datetime.now(timezone.utc).isoformat(),'parameters':{},'limitations':['Calendar grouping uses local interval start, matching dashboard convention; not an independent validation of meteorological day definition.','All numeric observations included, matching published aggregation; quality codes separately counted.','A missing observation in the archive is not proof that no measurement was made.']}
errors=[]
def date(s):
    return datetime.fromisoformat(s.strip().replace('Z','+00:00')).replace(tzinfo=timezone.utc) if '+' not in s and not s.endswith('Z') else datetime.fromisoformat(s.replace('Z','+00:00'))
def download(pid):
    urls=[f'{BASE}/parameter/{pid}/station/{STATION}/period/corrected-archive/data.csv',f'https://opendata-download.smhi.se/stream?type=metobs&parameterIds={pid}&stationId={STATION}&period=corrected-archive']
    failures=[]
    for url in urls:
        try:
            with urlopen(Request(url,headers={'User-Agent':'Lulea-climate-audit/1.0'}),timeout=180) as r: raw=r.read()
            try: text=raw.decode('utf-8-sig')
            except UnicodeDecodeError: text=raw.decode('cp1252')
            rows=list(csv.reader(io.StringIO(text),delimiter=';'))
            for i,row in enumerate(rows):
                if row and row[0].strip().lower()=='stationsnamn':
                    if rows[i+1][1].strip()!=STATION:raise ValueError('station mismatch')
                    break
            else: raise ValueError('station metadata absent')
            for i,row in enumerate(rows):
                q=next((j for j,x in enumerate(row) if 'kvalitet' in x.lower().strip()),None)
                if q is not None and q>=1 and ('datum' in row[0].strip().lower() or 'från' in row[0].strip().lower() or 'fran' in row[0].strip().lower()):
                    interval='från' in row[0].lower() or 'fran' in row[0].lower() or (q>=3 and ('till' in row[1].lower() or 'slut' in row[1].lower()))
                    date_only=q==1 or (q==2 and not interval and 'tid' not in row[1].lower())
                    print(f'Parameter {pid}: parsed header {row!r}',flush=True)
                    result={}
                    for cells in rows[i+1:]:
                        if len(cells)<=q:continue
                        try:
                            dt=date(cells[0] if interval or date_only else cells[0]+' '+cells[1])
                            end=date(cells[1]).isoformat() if interval else ''
                            v=float(cells[q-1].replace(',','.'))
                            if math.isfinite(v):result[(dt.isoformat(),end)]=(dt.astimezone(TZ),v,cells[q])
                        except (ValueError,IndexError):continue
                    if not result:raise ValueError('no parsed observations')
                    return url,result
            raise ValueError('data header not found; candidate headers: '+repr([r for r in rows[:40] if any('kvalitet' in x.lower() for x in r)]))
        except Exception as e: failures.append(str(e))
    raise RuntimeError('; '.join(failures))
def local(pid):
    result={}
    for p in sorted((ROOT/'data'/f'parameter_{pid}').glob('*.csv')):
        with p.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                try:
                    dt=datetime.fromisoformat(r['datetime_utc'].replace('Z','+00:00'))
                    end=datetime.fromtimestamp(int(r['to_ms'])/1000,timezone.utc).isoformat() if r.get('to_ms') else ''
                    v=float(r['value_numeric'])
                    if math.isfinite(v):result[(dt.isoformat(),end)]=(dt.astimezone(TZ),v,r.get('quality',''))
                except (ValueError,KeyError):continue
    return result
def months(rows):
    groups=defaultdict(list)
    for d,v,q in rows.values():groups[(d.year,d.month)].append((d,v,q))
    return groups
for pid,(section,field,metric,aggregate) in SPECS.items():
    entry={}
    report['parameters'][str(pid)]=entry
    try:
        url,source=download(pid)
        stored=local(pid)
        sm, lm=months(source),months(stored)
        entry.update(source=url,archive_records=len(source),local_records=len(stored))
        entry['gap_years']=[]
        for y in GAPS.get(pid,[]):
            a={k:v for k,v in source.items() if v[0].year==y}
            b={k:v for k,v in stored.items() if v[0].year==y}
            entry['gap_years'].append({'year':y,'archive':len(a),'local':len(b),'missing_local':len(a.keys()-b.keys()),'classification':'archive_has_records' if a else 'no_numeric_records_in_current_archive'})
        entry['samples']=[]
        published={(r['year'],r['month']):r.get(metric) for r in dashboard[section][field]}
        for y,m in SAMPLES:
            a,b=sm.get((y,m),[]),lm.get((y,m),[])
            av=round(aggregate([v for _,v,_ in a]),2) if a else None
            bv=round(aggregate([v for _,v,_ in b]),2) if b else None
            pv=published.get((y,m))
            days=len({d.date() for d,_,_ in a})
            item={'year':y,'month':m,'archive':av,'local':bv,'dashboard':pv,'archive_n':len(a),'local_n':len(b),'archive_days':days,'calendar_days':calendar.monthrange(y,m)[1],'quality':dict(Counter(q for _,_,q in a))}
            item['dashboard_matches_local']=bv is not None and pv is not None and abs(bv-pv)<=0.011
            item['archive_matches_local']=av is not None and bv is not None and abs(av-bv)<=0.011 and len(a)==len(b)
            entry['samples'].append(item)
            if b and not item['dashboard_matches_local']:errors.append(f'Parameter {pid} {y}-{m}: dashboard differs from local observations')
        entry['year_coverage']=[{'year':y,'months':len({m for yy,m in lm if yy==y}),'days':len({d.date() for d,_,_ in stored.values() if d.year==y})} for y in sorted({y for y,m in lm})]
    except Exception as e:
        entry['error']=str(e)
        errors.append(f'Parameter {pid}: audit unavailable: {e}')
report['errors']=errors
(OUT/'smhi-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
