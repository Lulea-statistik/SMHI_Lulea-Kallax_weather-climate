#!/usr/bin/env python3
"""Inspect SMHI analysed snow-depth PNG for dimensions, palette and legend classes."""

from __future__ import annotations
import io,json
from collections import Counter
from pathlib import Path
import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_png_probe.json"
URL="https://www.smhi.se/pd/klimat/snow_depth/2526/sno260517.png"
TIMEOUT=45

def main():
    r=requests.get(URL,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-snow-png-probe/1.0"})
    r.raise_for_status()
    im=Image.open(io.BytesIO(r.content))
    rgba=im.convert("RGBA")
    count=Counter(rgba.getdata())
    common=[{"rgba":list(k),"count":v} for k,v in count.most_common(80)]
    report={
        "url":URL,
        "mode":im.mode,
        "size":list(im.size),
        "format":im.format,
        "info":im.info,
        "unique_rgba":len(count),
        "common_rgba":common,
        "palette":list(im.getpalette() or [])[:768],
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "mode":report["mode"],
        "size":report["size"],
        "format":report["format"],
        "unique_rgba":report["unique_rgba"],
        "common_rgba":common[:30]
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
