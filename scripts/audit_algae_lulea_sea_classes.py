#!/usr/bin/env python3
"""Read-only geographic audit of SMHI WFS algae classes within Lulea's NMD sea.

Uses the same NMD-derived, municipality-clipped sea geometry as fetch_algae.py.
All vector clipping is performed in verified EPSG:4326; area is measured only
after reprojection to EPSG:3006. No production data are written.
"""
import json
from collections import Counter
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("algae-service-audit")
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "data/lightning/geography_nmd.geojson"
WFS = "https://opendata-view.smhi.se/algae/wfs"
DAYS = ("2019-08-15", "2025-07-15", "2026-06-25", "2026-07-15")
CLASSES = (2, 3)
PAGE_SIZE = 500
MAX_PAGES = 100
TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
session = requests.Session()
session.headers["User-Agent"] = "Lulea-statistik-algae-local-sea-audit/1.0"

source = json.loads(SOURCE.read_text(encoding="utf-8"))
# GeoJSON coordinates are WGS84 lon/lat. The generating script
# build_lightning_geography.py explicitly transforms EPSG:3006 -> EPSG:4326.
if source.get("crs") and "4326" not in json.dumps(source["crs"]):
    raise SystemExit("Unexpected CRS in NMD-derived GeoJSON: audit stopped")
sea_features = [
    f for f in source.get("features", [])
    if (f.get("properties") or {}).get("class") == "sea"
]
if len(sea_features) != 1:
    raise SystemExit(f"Expected exactly one sea feature; got {len(sea_features)}")
sea = shape(sea_features[0]["geometry"])
if sea.is_empty or not sea.is_valid:
    raise SystemExit("Invalid sea geometry; audit stopped")
bounds = sea.bounds
if not (19 < bounds[0] < 25 and 64 < bounds[1] < 67 and
        20 < bounds[2] < 27 and 65 < bounds[3] < 68):
    raise SystemExit(f"Unexpected WGS84 Lulea sea bounds: {bounds}")
sea_3006 = transform(TO_3006, sea)
report = {
    "source": WFS,
    "sea_mask": str(SOURCE.relative_to(ROOT)),
    "sea_mask_description": "NMD class 62 clipped to Lulea municipality; inherited approx. 20 m mask resolution",
    "source_vector_crs": "EPSG:4326 (GeoJSON lon/lat, from generating script)",
    "area_crs": "EPSG:3006",
    "sea_bounds_wgs84": list(bounds),
    "sea_area_km2": round(sea_3006.area / 1e6, 3),
    "method": "WFS class filter and bounding-box retrieval; polygon intersection with true Lulea NMD sea mask; union after EPSG:3006 projection",
    "dates": {}, "errors": [],
    "limitations": [
        "Only selected days; absence is not absence for all historic dates",
        "NMD marine mask is a land-cover-derived approximation, not a surveyed municipal boundary",
        "WFS class semantics are preliminary; this audit does not establish confirmed algae area",
        "Overlapping source polygons within a class are unioned; different classes are reported separately",
        "WFS BBOX is only a prefilter; actual polygon clipping is to the sea geometry",
    ]
}
for day in DAYS:
    daily = {}
    report["dates"][day] = daily
    for cls in CLASSES:
        all_features = []
        matched = None
        failed = False
        for page in range(MAX_PAGES):
            params = {
                "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": "algae:SR.SeaSurfaceArea",
                "outputFormat": "application/json", "srsName": "EPSG:4326",
                "count": PAGE_SIZE, "startIndex": page * PAGE_SIZE,
                "CQL_FILTER": (
                    f"date='{day}' AND class={cls} AND "
                    f"BBOX(geom,{bounds[0]:.6f},{bounds[1]:.6f},"
                    f"{bounds[2]:.6f},{bounds[3]:.6f},'EPSG:4326')"
                ),
            }
            try:
                response = session.get(WFS, params=params, timeout=90)
                response.raise_for_status()
                payload = response.json()
                if payload.get("type") != "FeatureCollection":
                    raise ValueError("Unexpected WFS response instead of GeoJSON FeatureCollection")
                items = payload.get("features")
                if not isinstance(items, list):
                    raise ValueError("WFS did not return features list")
                if page == 0 and isinstance(payload.get("numberMatched"), int):
                    matched = payload["numberMatched"]
                all_features.extend(items)
                if matched is not None and len(all_features) >= matched:
                    break
                if len(items) < PAGE_SIZE:
                    break
            except (requests.RequestException, ValueError) as exc:
                report["errors"].append(f"{day} class {cls} page {page}: {exc}")
                failed = True
                break
        else:
            report["errors"].append(f"{day} class {cls}: pagination exceeded {MAX_PAGES} pages")
            failed = True
        if matched is not None and len(all_features) != matched:
            report["errors"].append(
                f"{day} class {cls}: incomplete WFS response, {len(all_features)} of {matched}")
            failed = True
        if failed:
            daily[str(cls)] = {"status": "incomplete", "wfs_numberMatched": matched}
            continue
        clipped = []
        source_classes = Counter()
        for feature in all_features:
            source_cls = str((feature.get("properties") or {}).get("class"))
            source_classes[source_cls] += 1
            geom = shape(feature["geometry"])
            if not geom.is_valid:
                report["errors"].append(f"{day} class {cls}: invalid source geometry")
                failed = True
                break
            intersection = geom.intersection(sea)
            if not intersection.is_empty:
                projected = transform(TO_3006, intersection)
                if projected.area > 0:
                    clipped.append(projected)
        if failed:
            daily[str(cls)] = {"status": "incomplete", "wfs_numberMatched": matched}
            continue
        if any(k != str(cls) for k in source_classes):
            report["errors"].append(f"{day} class {cls}: returned mismatched source classes")
            daily[str(cls)] = {"status": "incomplete", "source_classes": dict(source_classes)}
            continue
        area = unary_union(clipped).area if clipped else 0.0
        daily[str(cls)] = {
            "status": "complete",
            "wfs_numberMatched_bbox": matched,
            "wfs_features_bbox": len(all_features),
            "polygons_intersecting_lulea_sea": len(clipped),
            "intersected_area_km2": round(area / 1e6, 6),
            "intersected_pct_of_nmd_sea": round(100 * area / sea_3006.area, 6),
            "raw_source_class": cls,
        }
        print(f"{day} class {cls}: {json.dumps(daily[str(cls)])}")
(OUT / "lulea-sea-class-audit.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("Errors:", len(report["errors"]))
if report["errors"]:
    raise SystemExit("Incomplete local audit; see lulea-sea-class-audit.json")
