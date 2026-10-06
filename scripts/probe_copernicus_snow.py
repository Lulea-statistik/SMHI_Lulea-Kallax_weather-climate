#!/usr/bin/env python3
"""Discover Copernicus Snow Phenology collections/items covering Lulea."""

from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"copernicus_snow_probe.json"
STAC="https://stac.dataspace.copernicus.eu/v1"
BBOX=[20.5,65.2,23.2,66.3]  # broad Lulea municipality envelope, metadata probe only
TIMEOUT=90

S=requests.Session()
S.headers.update({"User-Agent":"Lulea-statistik-Copernicus-snow-probe/1.0"})


def get_json(url, **params):
    r=S.get(url, params=params or None, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def main():
    cols=get_json(f"{STAC}/collections").get("collections",[])
    snow_cols=[]
    for c in cols:
        blob=" ".join([
            str(c.get("id","")),
            str(c.get("title","")),
            str(c.get("description","")),
            " ".join(map(str,c.get("keywords") or [])),
        ]).lower()
        if "snow phenology" in blob or ("phenology" in blob and "snow" in blob):
            snow_cols.append({
                "id":c.get("id"),
                "title":c.get("title"),
                "extent":c.get("extent"),
                "summaries":c.get("summaries"),
                "bands":c.get("bands"),
                "item_assets":c.get("item_assets"),
            })

    report={"bbox":BBOX,"collections":snow_cols,"items":{}}
    for c in snow_cols:
        cid=c["id"]
        try:
            data=get_json(
                f"{STAC}/collections/{cid}/items",
                bbox=",".join(map(str,BBOX)),
                limit=100,
            )
            feats=[]
            for f in data.get("features",[]):
                feats.append({
                    "id":f.get("id"),
                    "bbox":f.get("bbox"),
                    "datetime":(f.get("properties") or {}).get("datetime"),
                    "start_datetime":(f.get("properties") or {}).get("start_datetime"),
                    "end_datetime":(f.get("properties") or {}).get("end_datetime"),
                    "assets":f.get("assets"),
                    "properties":f.get("properties"),
                })
            report["items"][cid]=feats
        except Exception as exc:
            report["items"][cid]={"error":str(exc)}

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "collections":[{"id":c["id"],"title":c["title"]} for c in snow_cols],
        "item_counts":{k:(len(v) if isinstance(v,list) else v) for k,v in report["items"].items()}
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
