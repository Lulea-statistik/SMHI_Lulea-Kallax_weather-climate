#!/usr/bin/env python3
"""Read-only historical audit of SMHI classes 2/3 intersecting Lulea NMD sea.

Historical date coverage uses saved manifests separately from WFS class hits.
No source-absence is interpreted as evidence of algae-free conditions.
"""
import json
from collections import defaultdict
from datetime import date
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
YEARS = range(2002, 2027)
CLASSES = (2, 3)
PAGE_SIZE = 500
MAX_PAGES = 100
TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
session = requests.Session()
session.headers["User-Agent"] = "Lulea-statistik-algae-historical-local-audit/1.0"

source = json.loads(SOURCE.read_text(encoding="utf-8"))
if source.get("crs") and "4326" not in json.dumps(source["crs"]):
    raise SystemExit("GeoJSON CRS differs from EPSG:4326")
features = [f for f in source["features"] if (f.get("properties") or {}).get("class") == "sea"]
if len(features) != 1:
    raise SystemExit(f"Expected one Lulea NMD sea mask; got {len(features)}")
sea = shape(features[0]["geometry"])
if sea.is_empty or not sea.is_valid:
    raise SystemExit("Invalid NMD sea mask")
bounds = sea.bounds
if not (19 < bounds[0] < 25 and 64 < bounds[1] < 67 and
        20 < bounds[2] < 27 and 65 < bounds[3] < 68):
    raise SystemExit(f"Unexpected sea bounds {bounds}; verify EPSG:4326")
sea_area = transform(TO_3006, sea).area / 1e6

report = {
    "title": "Historical Lulea NMD sea audit of SMHI WFS classes 2 and 3",
    "wfs": WFS, "sea_mask": str(SOURCE.relative_to(ROOT)),
    "source_crs": "EPSG:4326 (GeoJSON from build_lightning_geography.py)",
    "area_crs": "EPSG:3006", "sea_area_km2": round(sea_area, 3),
    "years": {}, "errors": [],
    "interpretation": (
        "WFS class 2/3 labels remain preliminary. No match means no feature "
        "of that class returned by this WFS query, not absence of algae. "
        "Dates outside published local manifests have unknown observational coverage."
    ),
    "method": "Complete paginated annual WFS class/BBOX search then clipping to NMD sea with area measured in EPSG:3006",
}

def retrieve(year, cls):
    bbox = ",".join(f"{v:.6f}" for v in bounds)
    query = (f"date>='{year}-06-01' AND date<='{year}-09-30' "
             f"AND class={cls} AND BBOX(geom,{bbox},'EPSG:4326')")
    matched = None
    all_features = []
    first_ids = set()
    for page in range(MAX_PAGES):
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": "algae:SR.SeaSurfaceArea",
            "outputFormat": "application/json", "srsName": "EPSG:4326",
            "count": PAGE_SIZE, "startIndex": page * PAGE_SIZE,
            "CQL_FILTER": query,
        }
        response = session.get(WFS, params=params, timeout=90)
        response.raise_for_status()
        payload = response.json()
        if payload.get("type") != "FeatureCollection":
            raise ValueError("Expected FeatureCollection, got service error or other response")
        batch = payload.get("features")
        if not isinstance(batch, list):
            raise ValueError("Missing features array")
        if page == 0 and isinstance(payload.get("numberMatched"), int):
            matched = payload["numberMatched"]
        if batch:
            identifier = str(batch[0].get("id") or
                             (batch[0].get("properties") or {}).get("cyano_daymap_file_id") or "")
            if identifier and identifier in first_ids:
                raise ValueError("WFS pagination repeated first feature")
            if identifier:
                first_ids.add(identifier)
        all_features.extend(batch)
        if matched is not None and len(all_features) >= matched:
            break
        if len(batch) < PAGE_SIZE:
            break
    else:
        raise ValueError(f"Pagination exceeded {MAX_PAGES} pages")
    if matched is not None and matched != len(all_features):
        raise ValueError(f"Incomplete WFS pages: expected {matched}, got {len(all_features)}")
    return matched, all_features

for year in YEARS:
    manifest_file = ROOT / "docs/algae" / str(year) / "manifest.json"
    observed = set()
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        observed = {item["date"] for item in manifest.get("dates", [])
                    if item.get("date")}
    year_report = {
        "local_manifest_observation_dates": len(observed),
        "observed_dates_source": str(manifest_file.relative_to(ROOT)) if manifest_file.exists() else None,
        "classes": {}, "dates_with_intersection": {}, "status": "complete",
    }
    report["years"][str(year)] = year_report
    for cls in CLASSES:
        try:
            matched, all_features = retrieve(year, cls)
            dated = defaultdict(list)
            fetched_dates = set()
            invalid_dates = 0
            for feature in all_features:
                props = feature.get("properties") or {}
                if str(props.get("class")) != str(cls):
                    raise ValueError("Source class differs from requested class")
                raw_date = str(props.get("date") or "")[:10]
                try:
                    parsed = date.fromisoformat(raw_date)
                except ValueError:
                    invalid_dates += 1
                    continue
                if parsed.year != year or not (6 <= parsed.month <= 9):
                    raise ValueError(f"Unexpected source date {raw_date}")
                fetched_dates.add(raw_date)
                geometry = shape(feature["geometry"])
                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError(f"Invalid WFS geometry on {raw_date}")
                overlap = geometry.intersection(sea)
                if not overlap.is_empty:
                    projected = transform(TO_3006, overlap)
                    if projected.area > 0:
                        dated[raw_date].append(projected)
            if invalid_dates:
                raise ValueError(f"{invalid_dates} records had invalid source dates")
            for day, polygons in dated.items():
                a = unary_union(polygons).area / 1e6
                day_row = year_report["dates_with_intersection"].setdefault(day, {})
                day_row[f"class_{cls}_area_km2"] = round(a, 6)
                day_row[f"class_{cls}_pct_sea"] = round(100 * a / sea_area, 6)
                day_row[f"class_{cls}_wfs_polygons"] = len(polygons)
                day_row["date_in_existing_local_manifest"] = day in observed
            year_report["classes"][str(cls)] = {
                "status": "complete",
                "wfs_numberMatched_in_sea_bbox": matched,
                "fetched_features": len(all_features),
                "wfs_dates_in_bbox": len(fetched_dates),
                "days_with_polygon_intersecting_sea": len(dated),
                "polygons_intersecting_sea": sum(len(v) for v in dated.values()),
            }
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            year_report["status"] = "incomplete"
            year_report["classes"][str(cls)] = {"status": "failed", "error": str(exc)}
            report["errors"].append(f"{year} class {cls}: {exc}")
    year_report["days_with_any_class_2_or_3"] = len(year_report["dates_with_intersection"])
    print(json.dumps({"year": year, "status": year_report["status"],
                      "observation_days": len(observed),
                      "class_2": year_report["classes"].get("2"),
                      "class_3": year_report["classes"].get("3")}, ensure_ascii=False), flush=True)

report["summary"] = {
    "years_checked": len(report["years"]),
    "complete_years": sum(1 for v in report["years"].values() if v["status"] == "complete"),
    "local_manifest_observation_day_entries": sum(
        v["local_manifest_observation_dates"] for v in report["years"].values()),
    "years_with_class_2_or_3_intersection": [
        int(year) for year, v in report["years"].items()
        if v["dates_with_intersection"]],
    "distinct_days_with_class_2_or_3_intersection": sum(
        v["days_with_any_class_2_or_3"] for v in report["years"].values()),
    "failed_class_queries": len(report["errors"]),
}
(OUT / "lulea-sea-historical-classes-audit.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("SUMMARY", json.dumps(report["summary"], ensure_ascii=False), flush=True)
if report["errors"]:
    raise SystemExit("Audit incomplete: review errors, do not interpret missing results as zeros")
