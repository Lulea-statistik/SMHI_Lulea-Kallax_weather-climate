#!/usr/bin/env python3
"""Extract exact SMHI snow image-overlay geometry expressions."""

from pathlib import Path
import json,re,requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_overlay_geometry.json"
URL="https://www.smhi.se/snowdepth/279.cb148.js?proxy=fodl-klimat"

r=requests.get(URL,timeout=45,headers={"User-Agent":"Lulea-statistik-SMHI-snow-overlay-probe/1.0"})
r.raise_for_status()
t=r.text

needles=[
    'var T=function(e){var i=e.className,s=e.width,u=e.height',
    'd=[[0,0],[u,s]]',
    'center:[u/2,s/2]',
    'bounds:d',
    '570/249',
    'url:l[t].url'
]
contexts={}
for n in needles:
    i=t.find(n)
    contexts[n]=t[max(0,i-1400):min(len(t),i+5000)] if i>=0 else None

# Capture the complete map helper from "var T=function" to responsive width D definition.
m=re.search(r'var T=function\(e\)\{var i=e\.className,s=e\.width,u=e\.height.*?\},D=function\(\)',t)
block=m.group(0) if m else None

OUT.write_text(json.dumps({"url":URL,"contexts":contexts,"map_block":block},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"found_block":bool(block),"block":block},ensure_ascii=False,indent=2))
