#!/usr/bin/env python3
"""Probe the public SMHI snow-depth page for machine-readable data endpoints."""

from __future__ import annotations
import json,re
from urllib.parse import urljoin
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_page_probe.json"
PAGE="https://www.smhi.se/vader/observationer/snodjup/"
TIMEOUT=45
S=requests.Session()
S.headers.update({"User-Agent":"Lulea-statistik-SMHI-snow-page-probe/1.0"})

PATTERNS=[
    "snodjup","snödjup","snowdepth","snow_depth","snow-depth",
    "opendata","wms","wcs","wmts","arcgis","geoserver","image","png","tif","tiff","json","api/"
]

def scan_text(text,source):
    low=text.lower()
    hits=[]
    for p in PATTERNS:
        start=0
        while True:
            i=low.find(p,start)
            if i<0: break
            hits.append({
                "pattern":p,
                "source":source,
                "context":text[max(0,i-220):min(len(text),i+420)].replace("\n"," ")[:700]
            })
            start=i+len(p)
            if len(hits)>=250: break
        if len(hits)>=250: break
    urls=sorted(set(re.findall(r'https?://[^"\'<>\\\s]+',text)))
    return hits,urls

def main():
    report={"page":PAGE,"status":None,"scripts":[],"page_hits":[],"page_urls":[],"script_hits":[]}
    r=S.get(PAGE,timeout=TIMEOUT)
    report["status"]=r.status_code
    r.raise_for_status()
    hits,urls=scan_text(r.text,PAGE)
    report["page_hits"]=hits
    report["page_urls"]=urls[:300]

    scripts=[]
    for m in re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text,re.I):
        u=urljoin(PAGE,m)
        if u not in scripts: scripts.append(u)
    report["scripts"]=scripts[:80]

    for u in scripts[:40]:
        try:
            sr=S.get(u,timeout=TIMEOUT)
            item={"url":u,"status":sr.status_code,"size":len(sr.content),"hits":[],"urls":[]}
            if sr.ok and len(sr.content)<=8_000_000:
                text=sr.text
                sh,su=scan_text(text,u)
                item["hits"]=sh[:100]
                item["urls"]=su[:100]
            report["script_hits"].append(item)
        except Exception as exc:
            report["script_hits"].append({"url":u,"error":str(exc)})

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

    summary=[]
    for h in report["page_hits"]:
        summary.append((h["pattern"],"page",h["context"][:220]))
    for s in report["script_hits"]:
        for h in s.get("hits",[]):
            summary.append((h["pattern"],s["url"],h["context"][:220]))
    print(json.dumps({
        "page_status":report["status"],
        "scripts":len(report["scripts"]),
        "interesting_hits":summary[:80]
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
