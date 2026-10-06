#!/usr/bin/env python3
"""Probe one MESAN-A day and report GRIB subdatasets/bands for snow fields."""

from __future__ import annotations
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests
import rasterio

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"mesan_probe.json"
BASE="https://opendata-download-grid-archive.smhi.se/feed/6"
TARGET=("2018","01","15")
S=requests.Session()
S.headers.update({"User-Agent":"Lulea-statistik-MESAN-probe/1.0"})


def get(url):
    r=S.get(url,timeout=90)
    r.raise_for_status()
    return r


def atom_links(url):
    r=get(url)
    root=ET.fromstring(r.content)
    links=[]
    for e in root.iter():
        if not e.tag.endswith("link"):
            continue
        href=e.attrib.get("href")
        if not href:
            continue
        rel=e.attrib.get("rel","")
        typ=e.attrib.get("type","")
        title=e.attrib.get("title","")
        links.append({"href":urljoin(url,href),"rel":rel,"type":typ,"title":title})
    return links


def descend():
    url=BASE
    trace=[]
    for part in TARGET:
        links=atom_links(url)
        trace.append({"url":url,"links":links[:12]})
        candidates=[x for x in links if re.search(rf"/{re.escape(part)}(?:/|$)",x["href"])]
        if not candidates:
            candidates=[x for x in links if part in x["title"] or part in x["href"].rstrip("/").split("/")[-1]]
        if not candidates:
            raise RuntimeError(f"Could not find {part} under {url}")
        url=candidates[0]["href"]
    links=atom_links(url)
    trace.append({"url":url,"links":links[:30]})
    files=[x for x in links if ("grib" in x["type"].lower() or re.search(r"\.(grib|grb|grib2)(\?|$)",x["href"],re.I))]
    if not files:
        files=[x for x in links if "/data/" in x["href"] or "download" in x["href"]]
    if not files:
        raise RuntimeError("No GRIB file link found for target day")
    return files,trace


def inspect_grib(url):
    r=get(url)
    body=r.content
    magic=body[:16]
    report={
        "url":url,
        "status":r.status_code,
        "content_type":r.headers.get("Content-Type"),
        "content_length":r.headers.get("Content-Length"),
        "bytes":len(body),
        "magic_hex":magic.hex(),
        "magic_ascii":"".join(chr(b) if 32 <= b < 127 else "." for b in magic),
        "final_url":r.url,
        "datasets":[],
    }

    # GRIB messages always begin with ASCII "GRIB". Do not hand HTML/XML
    # responses or redirect landing pages to GDAL.
    if not body.startswith(b"GRIB"):
        report["not_grib_preview"]=body[:500].decode("utf-8","replace")
        return report

    with tempfile.NamedTemporaryFile(suffix=".grib",delete=False) as tmp:
        tmp.write(body)
        path=tmp.name
    try:
        try:
            with rasterio.open(path) as ds:
                report["driver"]=ds.driver
                report["crs"]=str(ds.crs)
                report["shape"]=[ds.height,ds.width]
                report["count"]=ds.count
                report["tags"]=ds.tags()
                report["subdatasets"]=list(ds.subdatasets)
                if ds.count:
                    report["bands"]=[
                        {"band":i,"description":ds.descriptions[i-1],"tags":ds.tags(i)}
                        for i in range(1,ds.count+1)
                    ]
            for sub in report.get("subdatasets",[])[:40]:
                try:
                    with rasterio.open(sub) as sd:
                        report["datasets"].append({
                            "name":sub,
                            "count":sd.count,
                            "shape":[sd.height,sd.width],
                            "crs":str(sd.crs),
                            "descriptions":list(sd.descriptions),
                            "tags":sd.tags(),
                            "band_tags":[sd.tags(i) for i in range(1,min(sd.count,5)+1)]
                        })
                except Exception as exc:
                    report["datasets"].append({"name":sub,"error":str(exc)})
        except Exception as exc:
            report["rasterio_error"]=str(exc)
    finally:
        Path(path).unlink(missing_ok=True)
    return report


def main():
    files,trace=descend()
    inspected=[]
    for f in files[:5]:
        inspected.append(inspect_grib(f["href"]))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"target":"-".join(TARGET),"trace":trace,"files":files[:20],"inspected":inspected},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "files":[x["href"] for x in files[:10]],
        "summary":[{
            "final_url":x.get("final_url"),
            "content_type":x.get("content_type"),
            "bytes":x.get("bytes"),
            "magic_ascii":x.get("magic_ascii"),
            "driver":x.get("driver"),
            "count":x.get("count"),
            "rasterio_error":x.get("rasterio_error")
        } for x in inspected]
    },indent=2))


if __name__=="__main__":
    main()
