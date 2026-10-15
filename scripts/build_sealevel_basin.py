#!/usr/bin/env python3
"""Compare northern Gulf of Bothnia stations in common RH 2000 datum; G only."""
import csv, datetime as dt, json, pathlib, urllib.request
from collections import defaultdict
BASE=pathlib.Path(__file__).resolve().parents[1]
OUT=BASE/"docs"/"sealevel"/"basin.json"
API="https://opendata-download-ocobs.smhi.se/api/version/1.0"
STATIONS=[("Forsmark",2179,60.4086,18.2108),("Gävle Hamn",35236,60.6967,17.2314),("Spikarna",2061,62.3633,17.5311),("Skagsudde 2",35138,63.1905,19.0123),("Furuögrund",2055,64.9156,21.2307),("Strömören",35183,65.5484,22.2380),("Ratan",2056,63.9861,20.8950)]
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Lulea-statistik-basin/1.0"}),timeout=120) as r:return r.read()
def stats(a):
    return {"count":len(a),"mean_cm":round(sum(a)/len(a),2),"min_cm":min(a),"max_cm":max(a)} if a else None
def load(station):
    u=f"{API}/parameter/6/station/{station}/period/corrected-archive/data.csv"
    s=get(u).decode("utf-8-sig")
    lines=s.splitlines()
    start=next(i for i,l in enumerate(lines) if l.startswith("Datum Tid (UTC);"))
    values={}
    for row in csv.reader(lines[start+1:],delimiter=";"):
        if len(row)<3 or row[2].strip().upper()!="G":continue
        try:
            t=dt.datetime.strptime(row[0].strip(),"%Y-%m-%d %H:%M:%S")
            v=float(row[1].replace(",","."))
        except (ValueError,IndexError):continue
        values[t]=v
    return values
def discover_stations():
    """Use SMHI parameter 6 catalog; keep original known stations as fallback."""
    known={item[1]:item for item in STATIONS}
    try:
        catalog=json.loads(get(f"{API}/parameter/6.json").decode("utf-8-sig"))
        entries=catalog.get("station",[])
        if not entries:
            raise ValueError("SMHI parameter catalog returned no stations")
        for item in entries:
            try:
                sid=int(item.get("key",item.get("id")))
                lat=float(item.get("latitude",item.get("lat")))
                lon=float(item.get("longitude",item.get("lon")))
                name=str(item.get("name",item.get("title",""))).strip()
            except (TypeError,ValueError):
                continue
            # Sweden's Bothnian coastline, north of Forsmark; exclude other seas.
            if 60.4086 <= lat <= 66.8 and 16.0 <= lon <= 24.5 and name:
                known[sid]=(name,sid,lat,lon)
        print("Catalog station candidates:",len(known))
    except Exception as exc:
        print("WARNING station discovery failed:",exc)
    return sorted(known.values(),key=lambda x:(x[2],x[1]))

def main():
    stations=[]
    for name,sid,lat,lon in discover_stations():
        try:
            rows=load(sid)
            if not rows:raise ValueError("No approved observations")
            daily=defaultdict(list);annual=defaultdict(list);monthly=defaultdict(list);coverage=defaultdict(int)
            for t,v in sorted(rows.items()):
                daily[t.strftime("%Y-%m-%d")].append(v)
                annual[str(t.year)].append(v)
                monthly[t.strftime("%Y-%m")].append(v)
                coverage[str(t.year)]+=1
            current=max(rows)
            recent=(current-dt.timedelta(days=120))
            stations.append({"id":sid,"name":name,"lat":lat,"lon":lon,"first":min(rows).isoformat()+"Z","last":current.isoformat()+"Z",
              "daily":[{"time":k,**stats(v)} for k,v in sorted(daily.items())],
              "monthly":[{"time":k,**stats(v)} for k,v in sorted(monthly.items())],
              "annual":[{"year":int(k),**stats(v),"coverage_pct":round(len(v)/(8784 if int(k)%4==0 and (int(k)%100!=0 or int(k)%400==0) else 8760)*100,1)} for k,v in sorted(annual.items())],
              "recent_hourly":[{"time":t.strftime("%Y-%m-%dT%H:%M:%SZ"),"cm":v} for t,v in sorted(rows.items()) if t>=recent]})
            print(f"{name} {sid}: {len(rows)} G records")
        except Exception as e:
            print(f"WARNING {name} {sid}: {e}")
            stations.append({"id":sid,"name":name,"lat":lat,"lon":lon,"error":str(e)})
    if not any(s.get("id")==2056 and s.get("annual") for s in stations):
        raise SystemExit("Ratan reference station 2056 has no valid observations")
    if sum("annual" in s for s in stations)<3:raise SystemExit("Fewer than three stations loaded")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"reference":"RH 2000","unit":"cm","time_basis":"UTC","quality":"G","stations":stations},ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print("Wrote",OUT,OUT.stat().st_size)
if __name__=="__main__":main()
