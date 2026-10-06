#!/usr/bin/env python3
"""Probe whether SMHI snow observation PNG can provide point control for georeferencing."""

from __future__ import annotations
import io,json
from collections import Counter
from pathlib import Path
import requests
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_obs_png_probe.json"
URL="https://www.smhi.se/pd/klimat/snow_depth/2526/snoobs260215.png"
FALLBACK="https://www.smhi.se/pd/klimat/snow_depth/2526/snoobs260517.png"

def fetch(url):
    r=requests.get(url,timeout=45,headers={"User-Agent":"Lulea-statistik-SMHI-snow-obs-probe/1.0"})
    if r.status_code!=200: return None,r.status_code
    return r.content,r.status_code

def analyze(content,url):
    im=Image.open(io.BytesIO(content)).convert("RGBA")
    a=np.asarray(im)
    alpha=a[:,:,3]
    rgb=a[:,:,:3]
    opaque=int(np.sum(alpha>20))
    ys,xs=np.where(alpha>20)
    bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None
    cnt=Counter(map(tuple,rgb[alpha>20].reshape(-1,3)))
    return {
        "url":url,"size":list(im.size),"opaque_pixels":opaque,
        "alpha_bbox":bbox,"unique_rgb_opaque":len(cnt),
        "common_rgb":[{"rgb":[int(x) for x in k],"count":int(v)} for k,v in cnt.most_common(40)]
    }

def main():
    content,status=fetch(URL)
    used=URL
    if content is None:
        content,status=fetch(FALLBACK); used=FALLBACK
    if content is None: raise RuntimeError("No observation PNG available")
    report=analyze(content,used)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
