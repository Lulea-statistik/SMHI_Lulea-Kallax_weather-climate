#!/usr/bin/env python3
"""Archive SMHI weather warnings and intersect current warning polygons with Luleå.

SMHI API geometry and the existing municipality geometry are GeoJSON EPSG:4326.
This is an observational archive of snapshots, not a complete historical feed.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
API="https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json"
BOUNDARY=ROOT/"docs"/"snowmap_boundary.geojson"
OUT=ROOT/"docs"/"warnings"
ARCHIVE=ROOT/"data"/"warning_snapshots"
PROJECT=Transformer.from_crs("EPSG:4326","EPSG:3006",always_xy=True).transform

def fetch():
    req=Request(API,headers={"User-Agent":"Lulea-statistik warning archive/1.0","Accept":"application/json"})
    with urlopen(req,timeout=55) as response:
        return json.load(response)

def main():
    bounds=json.loads(BOUNDARY.read_text(encoding="utf-8"))
    features=bounds.get("features",[])
    if not features:raise ValueError("Missing municipal polygon")
    municipal=shape(features[0]["geometry"])
    if municipal.is_empty or not municipal.is_valid:raise ValueError("Invalid Lulea boundary")
    # Warning polygons are documented in GeoJSON EPSG:4326; verify their CRS before spatial comparison.
    municipal_metric=transform(PROJECT,municipal)
    now=datetime.now(timezone.utc)
    data=fetch()
    if not isinstance(data,list):raise ValueError("Unexpected SMHI API structure")
    result=[]
    for warning in data:
        for item in warning.get("warningAreas",[]):
            feature=item.get("area") or {}
            geom_data=feature.get("geometry") if isinstance(feature,dict) else None
            if not geom_data:continue
            crs=(feature.get("crs") or {}).get("properties",{}).get("name","EPSG:4326")
            if crs.upper() not in ("EPSG:4326","URN:OGC:DEF:CRS:EPSG::4326"):
                raise ValueError("Unsupported warning CRS: "+crs)
            geometry=shape(geom_data)
            if geometry.is_empty or not geometry.is_valid:continue
            if not municipal.intersects(geometry):continue
            intersection=municipal_metric.intersection(transform(PROJECT,geometry))
            kind="linje" if geometry.geom_type in ("LineString","MultiLineString") else "yta" if geometry.geom_type in ("Polygon","MultiPolygon") else "annan"
            result.append({
                "id":str(warning.get("id","")),"area_id":str(item.get("id","")),
                "event":(warning.get("event") or {}).get("sv",""),
                "event_code":(warning.get("event") or {}).get("code",""),
                "title":(item.get("eventDescription") or {}).get("sv",""),
                "level":(item.get("warningLevel") or {}).get("sv",""),
                "level_code":(item.get("warningLevel") or {}).get("code",""),
                "area_name":(item.get("areaName") or {}).get("sv",""),
                "start":item.get("approximateStart"),"end":item.get("approximateEnd"),
                "published":item.get("published"),
                "geometry_type":geometry.geom_type,"geography_kind":kind,
                "overlap_length_km":round(intersection.length/1000,3) if kind=="linje" else None,
                "overlap_km2":round(intersection.area/1e6,2) if kind=="yta" else None,
                "overlap_percent":round(100*intersection.area/municipal_metric.area,2) if kind=="yta" else None,
                "geometry":geom_data
            })
    OUT.mkdir(parents=True,exist_ok=True)
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    stamp=now.strftime("%Y%m%dT%H%M%SZ")
    (ARCHIVE/(stamp+".json")).write_text(json.dumps({"fetched_utc":now.isoformat(),"source":API,"warnings":data},ensure_ascii=False),encoding="utf-8")
    summary={"fetched_utc":now.isoformat(),"source":API,
        "boundary_source":"docs/snowmap_boundary.geojson (working geometry, not verified official administrative boundary)",
        "boundary_crs":"EPSG:4326","intersection_crs":"EPSG:3006",
        "national_warning_count":len(data),"municipality_warning_areas":len(result),
        "warnings":result,"history_note":"Snapshots begin when scheduled fetching starts; no retrospective warning archive is implied."}
    (OUT/"current.json").write_text(json.dumps(summary,ensure_ascii=False),encoding="utf-8")
    history_path=OUT/"history.json"
    try:
        history=json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
        if not isinstance(history,list):history=[]
    except (ValueError,OSError):
        history=[]
    history.append({"fetched_utc":now.isoformat(),"national_count":len(data),
                    "lulea_area_count":len(result),
                    "events":sorted({r["event"] for r in result}),
                    "snapshot":stamp+".json"})
    # Retain one historical summary per actual fetch timestamp, without inferring periods between polls.
    history=list({x["fetched_utc"]:x for x in history}.values())
    history.sort(key=lambda x:x["fetched_utc"])
    history_path.write_text(json.dumps(history,ensure_ascii=False,separators=(',',':')),encoding="utf-8")

    print("SMHI warnings:",len(data),"national,",len(result),"overlapping Lulea. Snapshot:",stamp)

if __name__=="__main__":main()
