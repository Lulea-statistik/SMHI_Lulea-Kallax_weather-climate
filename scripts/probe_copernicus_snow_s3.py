#!/usr/bin/env python3
"""Probe official Copernicus HR-WSI S3 for Snow Phenology tiles covering Lulea."""

from __future__ import annotations
import json
from pathlib import Path

import boto3
import mgrs

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"copernicus_snow_s3_probe.json"

ENDPOINT="https://s3.WAW3-2.cloudferro.com"
ACCESS_KEY="c4ae60af7b144053803c618a8860f7c9"
SECRET_KEY="dcb3ba1f6eab45aaaec5802feef5e2e4"
BUCKET="HRWSI"

# Sample municipality envelope and centre points. MGRS tiles are 100 km squares,
# so a few points are sufficient to identify the tile set intersecting Lulea.
POINTS=[
    (65.58,22.15),(66.00,22.00),(65.35,21.10),(65.95,23.00),
    (66.25,21.20),(66.20,22.90),(65.30,22.80)
]

YEARS=list(range(2016,2026))
PRODUCTS=["SP_S2","SP_S1S2"]

def tile_for(lat,lon):
    m=mgrs.MGRS()
    code=m.toMGRS(lat,lon,MGRSPrecision=0)
    if isinstance(code,bytes): code=code.decode("ascii")
    return code[:5]

def main():
    tiles=sorted({tile_for(lat,lon) for lat,lon in POINTS})
    s3=boto3.resource(
        "s3",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT,
    )
    bucket=s3.Bucket(BUCKET)
    report={"tiles":tiles,"products":{}}
    for product in PRODUCTS:
        prod={}
        for tile in tiles:
            years={}
            for year in YEARS:
                prefix=f"{product}/{tile}/{year}"
                objs=[]
                for obj in bucket.objects.filter(Prefix=prefix):
                    objs.append({"key":obj.key,"size":obj.size})
                    if len(objs)>=30: break
                if objs: years[str(year)]=objs
            prod[tile]=years
        report["products"][product]=prod

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "tiles":tiles,
        "counts":{
            p:{t:{y:len(v) for y,v in ys.items()} for t,ys in td.items()}
            for p,td in report["products"].items()
        }
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
