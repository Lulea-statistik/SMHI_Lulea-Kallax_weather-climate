#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parents[1]
SNOWMAP=ROOT/"docs"/"snowmap"
SNOWGRID=ROOT/"docs"/"snowgrid"
OUT=SNOWGRID/"recent_snow_diagnostic.json"

SEASONS=["2018-19","2019-20","2020-21","2021-22","2022-23","2023-24","2024-25","2025-26"]

def stats(vals):
    vals=[float(v) for v in vals if v is not None]
    if not vals:return {"n":0}
    return {
        "n":len(vals),
        "min":round(min(vals),1),
        "mean":round(mean(vals),1),
        "max":round(max(vals),1),
        "positive":sum(v>=1 for v in vals),
        "positive_pct":round(100*sum(v>=1 for v in vals)/len(vals),1),
        "sample":vals[:20],
    }

def main():
    out={"seasons":[]}
    for season in SEASONS:
        smp=SNOWMAP/f"{season}.json"
        sgp=SNOWGRID/f"{season}.json"
        if not smp.exists() or not sgp.exists():
            continue
        sm=json.loads(smp.read_text(encoding="utf-8"))
        sg=json.loads(sgp.read_text(encoding="utf-8"))
        obs_by_date={}
        for r in sm.get("observations",[]):
            obs_by_date.setdefault(r["date"],[]).append(r)
        grid_by_date={r["date"]:r for r in sg.get("days",[])}
        y=int(season[:4])
        dates=[f"{y}-12-15",f"{y+1}-01-15",f"{y+1}-02-15",f"{y+1}-03-15",f"{y+1}-04-15"]
        rows=[]
        for d in dates:
            obs=obs_by_date.get(d,[])
            grid=grid_by_date.get(d,{})
            obsvals=[r.get("depth_cm") for r in obs]
            rows.append({
                "date":d,
                "stations":[{"id":r.get("station_id"),"depth_cm":r.get("depth_cm")} for r in obs[:25]],
                "station_stats":stats(obsvals),
                "grid_stats":stats(grid.get("values_cm",[])),
                "grid_station_count":grid.get("station_count"),
            })
        out["seasons"].append({
            "season":season,
            "source_type":sg.get("source_type"),
            "method":sg.get("method"),
            "rows":rows,
        })
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
