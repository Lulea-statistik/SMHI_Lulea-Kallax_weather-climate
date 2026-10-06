#!/usr/bin/env python3
"""Probe SMHI snow-depth station WMS capabilities and supported CRS."""

from __future__ import annotations
import json
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_wms_capabilities.json"
URL="https://opendata-view.smhi.se/met-obs/ACMF.snodjup_momentan_view/wms?service=WMS&request=GetCapabilities"

def lname(tag):
    return tag.rsplit("}",1)[-1]

def txt(el):
    return (el.text or "").strip() if el is not None else None

def main():
    r=requests.get(URL,timeout=60,headers={"User-Agent":"Lulea-statistik-SMHI-WMS-probe/1.0"})
    r.raise_for_status()
    root=ET.fromstring(r.content)
    version=root.attrib.get("version")
    crs=set()
    layers=[]
    for el in root.iter():
        n=lname(el.tag)
        if n in {"CRS","SRS"} and txt(el):
            crs.add(txt(el))
    for layer in [e for e in root.iter() if lname(e.tag)=="Layer"]:
        name=title=None
        layer_crs=[]
        bboxes=[]
        for ch in list(layer):
            n=lname(ch.tag)
            if n=="Name": name=txt(ch)
            elif n=="Title": title=txt(ch)
            elif n in {"CRS","SRS"} and txt(ch): layer_crs.append(txt(ch))
            elif n=="BoundingBox":
                bboxes.append({k:v for k,v in ch.attrib.items()})
            elif n=="EX_GeographicBoundingBox":
                vals={}
                for x in list(ch):
                    vals[lname(x.tag)]=txt(x)
                bboxes.append({"EX_GeographicBoundingBox":vals})
        if name or title:
            layers.append({"name":name,"title":title,"crs":layer_crs,"bounding_boxes":bboxes})

    report={
        "url":URL,
        "http_status":r.status_code,
        "content_type":r.headers.get("content-type"),
        "wms_version":version,
        "root_element":lname(root.tag),
        "supported_crs":sorted(crs),
        "layers":layers,
        "raw_xml_prefix":r.text[:2000]
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
