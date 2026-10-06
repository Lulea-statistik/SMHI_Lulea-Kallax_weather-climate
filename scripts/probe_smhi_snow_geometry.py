#!/usr/bin/env python3
"""Extract map geometry and snow-depth legend definitions from SMHI snow app chunk."""

from __future__ import annotations
import json,re
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_geometry_probe.json"
URL="https://www.smhi.se/snowdepth/279.cb148.js?proxy=fodl-klimat"
TIMEOUT=45

def ctx(text,needle,span=900):
    out=[]
    start=0
    low=text.lower(); n=needle.lower()
    while True:
        i=low.find(n,start)
        if i<0: break
        out.append(text[max(0,i-span):min(len(text),i+span)])
        start=i+len(n)
        if len(out)>=30: break
    return out

def main():
    r=requests.get(URL,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-snow-geometry-probe/1.0"})
    r.raise_for_status()
    text=r.text

    needles=[
        "ImageOverlay","imageOverlay","CRS.Simple","maxBounds",
        "legendTitle","barmark","snowDepth","snow_depth",
        "obsort2425.png","h2o2425.png","lan2425.png","orter2425.png",
        "nt=","bounds","color","#"
    ]
    report={"url":URL,"size":len(text),"contexts":{}}
    for n in needles:
        report["contexts"][n]=ctx(text,n)

    # Extract hex colors and nearby snippets to help identify legend classes.
    colors=sorted(set(re.findall(r'#[0-9a-fA-F]{6}',text)))
    report["hex_colors"]=colors

    # Broad numeric array snippets often used for dimensions / bounds.
    arrays=re.findall(r'\[[0-9.\-]+\s*,\s*[0-9.\-]+\]',text)
    report["numeric_pairs"]=sorted(set(arrays))[:500]

    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "hex_colors":colors[:100],
        "numeric_pairs":report["numeric_pairs"][:100],
        "crs_simple":report["contexts"].get("CRS.Simple",[])[:3],
        "legend":report["contexts"].get("legendTitle",[])[:3],
        "image_overlay":report["contexts"].get("ImageOverlay",[])[:3],
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
