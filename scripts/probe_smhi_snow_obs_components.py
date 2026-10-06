#!/usr/bin/env python3
"""Detect connected objects in SMHI snow observation overlay for control-point matching."""

from __future__ import annotations
import io,json
from pathlib import Path
import requests,numpy as np
from PIL import Image
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_obs_components.json"
URL="https://www.smhi.se/pd/klimat/snow_depth/2526/snoobs260215.png"

def main():
    r=requests.get(URL,timeout=45,headers={"User-Agent":"Lulea-statistik-SMHI-obs-components/1.0"})
    r.raise_for_status()
    im=Image.open(io.BytesIO(r.content)).convert("RGBA")
    a=np.asarray(im)
    alpha=a[:,:,3]

    # Include all visible antialiased pixels, then bridge tiny glyph gaps to group
    # the digits/symbols belonging to the same station annotation.
    visible=alpha>20
    bridged=ndimage.binary_dilation(visible,structure=np.ones((3,5),bool),iterations=1)
    bridged=ndimage.binary_closing(bridged,structure=np.ones((3,3),bool),iterations=1)
    labels,n=ndimage.label(bridged)

    comps=[]
    for lab in range(1,n+1):
        ys,xs=np.where(labels==lab)
        if len(xs)<4: continue
        # Recover original visible pixels within component bbox.
        x0,x1=int(xs.min()),int(xs.max())
        y0,y1=int(ys.min()),int(ys.max())
        sub=visible[y0:y1+1,x0:x1+1]
        yy,xx=np.where(sub)
        if len(xx)==0: continue
        xxg=xx+x0; yyg=yy+y0
        comps.append({
            "id":lab,
            "bbox":[x0,y0,x1,y1],
            "width":x1-x0+1,
            "height":y1-y0+1,
            "visible_pixels":int(len(xxg)),
            "centroid_col":round(float(xxg.mean()),3),
            "centroid_row":round(float(yyg.mean()),3)
        })

    # Keep plausible station annotations; very large components may be touching labels.
    comps.sort(key=lambda c:(c["centroid_row"],c["centroid_col"]))
    plausible=[c for c in comps if 4<=c["width"]<=35 and 4<=c["height"]<=18 and c["visible_pixels"]>=5]

    report={
        "url":URL,
        "size":list(im.size),
        "connected_components_total":len(comps),
        "plausible_station_annotation_components":len(plausible),
        "components":comps,
        "plausible":plausible
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "size":list(im.size),
        "components_total":len(comps),
        "plausible":len(plausible),
        "first_plausible":plausible[:30]
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
