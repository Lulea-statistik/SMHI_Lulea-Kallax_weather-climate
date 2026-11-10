#!/usr/bin/env python3
"""Read-only cross-check of local WFS polygons against SMHI WMS pixels.

Samples representative points in published (clipped) WFS polygons, using the
WMS 1.1.1 EPSG:4326 request box in lon/lat order. Pixel colors are evidence,
not geodetic areas or a verified mapping from numerical WFS class values.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("algae-service-audit")
OUT.mkdir(exist_ok=True)
DAYS = ("2026-06-19", "2026-06-25", "2019-08-15", "2025-06-03")
BBOX = (21.0, 65.1, 23.6, 66.1)
WIDTH, HEIGHT = 1040, 600
URL = "https://opendata-view.smhi.se/algae/wms"
session = requests.Session()
session.headers["User-Agent"] = "Lulea-statistik-SMHI-algae-spatial-audit/1.0"
report = {"method": "WFS polygon representative points sampled on WMS TIME image",
          "wfs_geometry_crs": "EPSG:4326 (local GeoJSON output)",
          "wms_request_crs": "EPSG:4326 (WMS 1.1.1, lon/lat axis order)",
          "bbox_lonlat": BBOX,
          "pixel_interpretation": "Pixel RGBA only, not area; no semantic code mapping assumed",
          "days": {}, "warnings": []}
for day in DAYS:
    year = day[:4]
    path = ROOT / "docs" / "algae" / year / (day + ".geojson")
    if not path.exists():
        report["warnings"].append(f"{day}: local GeoJSON missing")
        continue
    features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "LAYERS": "SR.SeaSurfaceArea", "STYLES": "SR.SeaSurfaceArea.Algae",
        "FORMAT": "image/png", "TRANSPARENT": "TRUE", "SRS": "EPSG:4326",
        "BBOX": ",".join(str(z) for z in BBOX), "WIDTH": WIDTH,
        "HEIGHT": HEIGHT, "TIME": day,
    }
    try:
        response = session.get(URL, params=params, timeout=45)
        response.raise_for_status()
        if response.content[:100].find(b"Exception") != -1:
            raise ValueError("OGC ServiceException in image response")
        with Image.open(BytesIO(response.content)) as raw:
            im = raw.convert("RGBA")
            if im.size != (WIDTH, HEIGHT):
                raise ValueError(f"Unexpected image dimensions: {im.size}")
    except (requests.RequestException, OSError, ValueError) as exc:
        report["warnings"].append(f"{day}: WMS request failed: {exc}")
        continue

    counts = defaultdict(Counter)
    examples = []
    checked, ignored = 0, Counter()
    # Use largest 60 polygons per class; each polygon contributes a sample,
    # without considering the polygon's geodetic area.
    candidates = defaultdict(list)
    for feature in features:
        try:
            geom = shape(feature["geometry"])
            if geom.is_empty or not geom.is_valid:
                ignored["invalid_or_empty_geometry"] += 1
                continue
            cls = str((feature.get("properties") or {}).get("class"))
            candidates[cls].append((geom.area, geom))
        except (ValueError, TypeError, KeyError) as exc:
            ignored["bad_geometry"] += 1
    for cls, geometries in sorted(candidates.items()):
        for _, geom in sorted(geometries, key=lambda pair: pair[0], reverse=True)[:60]:
            point = geom.representative_point()
            lon, lat = point.x, point.y
            if not (BBOX[0] < lon < BBOX[2] and BBOX[1] < lat < BBOX[3]):
                ignored["outside_wms_bbox"] += 1
                continue
            col = min(WIDTH-1, max(0, int((lon-BBOX[0])/(BBOX[2]-BBOX[0])*WIDTH)))
            row = min(HEIGHT-1, max(0, int((BBOX[3]-lat)/(BBOX[3]-BBOX[1])*HEIGHT)))
            rgba = im.getpixel((col, row))
            # WMS pixels are not guaranteed to match vector boundaries exactly;
            # sample observations are not treated as a definitive class mapping.
            if rgba[3] == 0:
                ignored["transparent_wms_pixel"] += 1
                continue
            counts[cls][rgba] += 1
            checked += 1
            if len(examples) < 15:
                examples.append({"class": cls, "lon": round(lon, 6),
                                 "lat": round(lat, 6), "pixel_xy": [col, row],
                                 "rgba": list(rgba)})
    report["days"][day] = {
        "total_local_features": len(features),
        "samples_with_visible_pixels": checked,
        "ignored": dict(ignored),
        "sample_counts_by_class_and_rgba": {
            cls: [{"rgba": list(rgba), "samples": n}
                  for rgba, n in counter.most_common(15)]
            for cls, counter in counts.items()
        },
        "sample_examples": examples,
    }
(OUT / "spatial-class-audit.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
