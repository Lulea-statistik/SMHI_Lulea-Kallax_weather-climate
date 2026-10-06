#!/usr/bin/env python3
"""Probe dynamic chunks behind SMHI snow-depth web app for data endpoints."""

from __future__ import annotations
import json,re
from urllib.parse import urljoin
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_chunks_probe.json"
BASE="https://www.smhi.se/snowdepth/"
RUNTIME=BASE+"41a20.js?proxy=fodl-klimat"
TIMEOUT=45
S=requests.Session()
S.headers.update({"User-Agent":"Lulea-statistik-SMHI-snow-chunks-probe/1.0"})

TOKENS=["fetch(","axios","xmlhttprequest","/api/","api.","json","png","tif","tiff","wms","wcs","wmts","snow","snodjup","snödjup","fodl-klimat","http"]

def contexts(text,source):
    low=text.lower()
    out=[]
    for tok in TOKENS:
        start=0
        while True:
            i=low.find(tok.lower(),start)
            if i<0: break
            out.append({"token":tok,"source":source,"context":text[max(0,i-260):min(len(text),i+520)].replace("\n"," ")})
            start=i+len(tok)
            if len(out)>=250: return out
    return out

def main():
    r=S.get(RUNTIME,timeout=TIMEOUT); r.raise_for_status()
    rt=r.text
    # Runtime typically contains chunk-id -> hash mappings and filename builder.
    js_names=set(re.findall(r'["\']([A-Za-z0-9._-]+\.js)["\']',rt))
    hashes=re.findall(r'([0-9]{1,5}):["\']([a-f0-9]{4,})["\']',rt)
    ids=set(re.findall(r'\b(\d{1,5})\b',rt))
    candidates=set(js_names)
    for cid,h in hashes:
        candidates.add(f"{cid}.{h}.js")
        candidates.add(f"{cid}{h}.js")
    # Also parse webpack u() templates like return ""+e+"."+({...}[e]||e)+".js"
    for m in re.finditer(r'\.js',rt):
        ctx=rt[max(0,m.start()-500):m.start()+100]
        for cid,h in re.findall(r'(\d{1,5}):["\']([a-f0-9]{4,})["\']',ctx):
            candidates.add(f"{cid}.{h}.js")
    report={"runtime":RUNTIME,"runtime_size":len(rt),"hashes":hashes,"candidates":[]}
    # Probe a bounded candidate set plus common chunk-number forms.
    probe=list(sorted(candidates))[:100]
    for cid in sorted(ids)[:80]:
        probe.extend([f"{cid}.js"])
    seen=set()
    for name in probe:
        if name in seen: continue
        seen.add(name)
        u=urljoin(BASE,name)
        try:
            q=S.get(u,params={"proxy":"fodl-klimat"},timeout=TIMEOUT)
            if q.status_code!=200 or len(q.content)<100: continue
            ct=q.headers.get("content-type","")
            if "javascript" not in ct and not name.endswith(".js"): continue
            item={"name":name,"url":q.url,"status":q.status_code,"size":len(q.content),"hits":contexts(q.text,q.url)}
            if item["hits"]: report["candidates"].append(item)
        except Exception as exc:
            pass
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "runtime_size":len(rt),
        "hash_mappings":hashes[:40],
        "matching_chunks":[{"name":x["name"],"size":x["size"],"hits":x["hits"][:10]} for x in report["candidates"][:20]]
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
