#!/usr/bin/env python3
"""Probe SMHI snowdepth API week endpoint and referenced assets."""

from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urljoin
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_week_probe.json"
API="https://www.smhi.se/pd/fodl-klimat/api/snowdepth/week"
TIMEOUT=45
S=requests.Session()
S.headers.update({"User-Agent":"Lulea-statistik-SMHI-snow-week-probe/1.0"})

def main():
    r=S.get(API,timeout=TIMEOUT)
    report={
        "api":API,
        "status":r.status_code,
        "content_type":r.headers.get("content-type"),
        "length":len(r.content),
        "json":None,
        "assets":[]
    }
    r.raise_for_status()
    data=r.json()
    report["json"]=data

    urls=[]
    def walk(x):
        if isinstance(x,dict):
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
        elif isinstance(x,str):
            if x.startswith("http://") or x.startswith("https://") or x.startswith("/"):
                urls.append(urljoin(API,x))
    walk(data)

    seen=set()
    for u in urls:
        if u in seen: continue
        seen.add(u)
        try:
            q=S.head(u,allow_redirects=True,timeout=TIMEOUT)
            report["assets"].append({
                "url":u,
                "status":q.status_code,
                "content_type":q.headers.get("content-type"),
                "content_length":q.headers.get("content-length"),
                "final_url":q.url
            })
        except Exception as exc:
            report["assets"].append({"url":u,"error":str(exc)})

    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "status":report["status"],
        "keys":list(data.keys()) if isinstance(data,dict) else None,
        "depth_count":len(data.get("depths",{})) if isinstance(data,dict) else None,
        "obs_count":len(data.get("obs",{})) if isinstance(data,dict) else None,
        "assets":report["assets"][:20]
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
