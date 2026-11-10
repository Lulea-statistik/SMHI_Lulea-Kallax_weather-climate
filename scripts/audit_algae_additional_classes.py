#!/usr/bin/env python3
"""Read-only search for additional numeric SMHI WFS classes in a larger sea area.

This is a bounded diagnostic, not an exhaustive inventory of all dates/areas.
For each requested class/day, query up to 25 WFS features (with numberMatched
when available) and compare an interior WFS point with a same-day WMS pixel.
"""
import json
from collections import Counter
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from shapely.geometry import shape

OUT = Path("algae-service-audit")
OUT.mkdir(exist_ok=True)
WFS = "https://opendata-view.smhi.se/algae/wfs"
WMS = "https://opendata-view.smhi.se/algae/wms"
# South and north Baltic plus Gulf of Bothnia; EPSG:4326 lon,lat.
REGIONS = {
    "southern_baltic": (13.0, 54.0, 21.0, 59.0),
    "northern_baltic": (17.0, 58.0, 26.0, 63.0),
    "gulf_of_bothnia": (17.0, 61.0, 26.0, 66.0),
}
DAYS = ("2026-06-25", "2026-07-15", "2025-07-15", "2019-08-15")
CLASSES = (2, 3, 5)
session = requests.Session()
session.headers["User-Agent"] = "Lulea-statistik-algae-class-discovery/1.0"
report = {
    "method": "bounded WFS class discovery and interior point WMS GetMap color check",
    "wfs_crs": "EPSG:4326, requested", "wms_crs": "EPSG:4326, WMS 1.1.1",
    "regions": REGIONS, "days": list(DAYS), "classes_tested": list(CLASSES),
    "important": "An empty result is only absence within this date/region/query, not proof the class never exists.",
    "hits": [], "errors": [], "request_count": 0,
}

def wms_pixel(day, lon, lat):
    # Request a small image around the sample point to reduce edge/pixel ambiguity.
    dx, dy = 0.12, 0.06
    box = (lon-dx, lat-dy, lon+dx, lat+dy)
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "LAYERS": "SR.SeaSurfaceArea", "STYLES": "SR.SeaSurfaceArea.Algae",
        "FORMAT": "image/png", "TRANSPARENT": "TRUE", "SRS": "EPSG:4326",
        "BBOX": ",".join(map(str, box)), "WIDTH": 480, "HEIGHT": 240,
        "TIME": day,
    }
    response = session.get(WMS, params=params, timeout=45)
    response.raise_for_status()
    if b"ServiceException" in response.content[:1000]:
        raise ValueError("SMHI returned WMS ServiceException")
    with Image.open(BytesIO(response.content)) as image:
        im = image.convert("RGBA")
        return list(im.getpixel((240, 120)))

for day in DAYS:
    for region_name, (xmin, ymin, xmax, ymax) in REGIONS.items():
        for cls in CLASSES:
            params = {
                "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": "algae:SR.SeaSurfaceArea",
                "outputFormat": "application/json", "srsName": "EPSG:4326",
                "count": 25, "startIndex": 0,
                "CQL_FILTER": (
                    f"date='{day}' AND class={cls} AND "
                    f"BBOX(geom,{xmin},{ymin},{xmax},{ymax},'EPSG:4326')"
                ),
            }
            row = {"date": day, "region": region_name, "class": cls,
                   "wfs_limit": 25}
            report["request_count"] += 1
            try:
                response = session.get(WFS, params=params, timeout=45)
                response.raise_for_status()
                payload = response.json()
                if payload.get("type") != "FeatureCollection":
                    raise ValueError("Unexpected WFS response, possibly service exception")
                features = payload.get("features", [])
                row["numberMatched"] = payload.get("numberMatched")
                row["numberReturned"] = payload.get("numberReturned")
                row["features_received"] = len(features)
                row["observed_classes"] = dict(Counter(
                    str((feature.get("properties") or {}).get("class"))
                    for feature in features))
                sample = None
                for feature in features:
                    try:
                        polygon = shape(feature["geometry"])
                        if not polygon.is_valid or polygon.is_empty:
                            continue
                        point = polygon.representative_point()
                        if xmin < point.x < xmax and ymin < point.y < ymax:
                            sample = point
                            break
                    except (TypeError, ValueError, KeyError):
                        continue
                if sample is not None:
                    row["sample_lonlat"] = [round(sample.x, 7), round(sample.y, 7)]
                    try:
                        row["wms_rgba_at_sample"] = wms_pixel(day, sample.x, sample.y)
                    except (requests.RequestException, ValueError, OSError) as exc:
                        row["wms_error"] = str(exc)
            except (requests.RequestException, ValueError) as exc:
                row["error"] = str(exc)
                report["errors"].append(f"{day} {region_name} class {cls}: {exc}")
            report["hits"].append(row)
            print(json.dumps(row, ensure_ascii=False))
(OUT / "additional-classes-audit.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("Search complete:", report["request_count"], "requests;",
      len(report["errors"]), "errors")
