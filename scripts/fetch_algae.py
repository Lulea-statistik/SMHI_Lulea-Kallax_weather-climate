#!/usr/bin/env python3
"""Build a lightweight Lulea algae-map test from SMHI SE.SR Ytansamling av alger.

The script queries SMHI's WFS only for a small bounding box around Lulea, clips
features to the municipality's marine area from the existing NMD geometry, and
writes one lazy-loadable GeoJSON file per available day plus a manifest.

This is intentionally a test-season implementation modelled on the sea-ice map.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
NMD_GEO_PATH = ROOT / "data" / "lightning" / "geography_nmd.geojson"
OUT_ROOT = ROOT / "docs" / "algae"
DATA_DIR = ROOT / "data" / "algae"
SUMMARY_PATH = DATA_DIR / "summary.json"

WFS_URL = "https://opendata-view.smhi.se/algae/wfs"
TYPE_NAME = "algae:SR.SeaSurfaceArea"
TIMEOUT = 90
RUN_MODE = os.getenv("RUN_MODE", "auto").strip().lower()
TEST_YEAR = int(os.getenv("ALGAE_TEST_YEAR", "0") or 0)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Lulea-statistik-SMHI-algae/1.0"})

TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def load_lulea_sea_wgs84():
    if not NMD_GEO_PATH.exists():
        raise RuntimeError(f"Missing Lulea marine geometry: {NMD_GEO_PATH}")
    data = json.loads(NMD_GEO_PATH.read_text(encoding="utf-8"))
    for feat in data.get("features", []):
        if (feat.get("properties") or {}).get("class") == "sea":
            geom = shape(feat["geometry"]).buffer(0)
            if not geom.is_empty:
                return geom
    raise RuntimeError("Lulea sea polygon is missing from geography_nmd.geojson")


def test_year(today: date) -> int:
    if TEST_YEAR:
        return TEST_YEAR
    return today.year if today.month >= 6 else today.year - 1


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def candidate_dates(year: int, today: date):
    season_start = date(year, 6, 1)
    season_end = date(year, 9, 30)
    if year == today.year:
        season_end = min(season_end, today)

    if RUN_MODE in {"bootstrap", "refresh-all"} or not (OUT_ROOT / str(year) / "manifest.json").exists():
        return list(date_range(season_start, season_end))

    start = max(season_start, today - timedelta(days=21))
    end = min(season_end, today)
    return list(date_range(start, end)) if start <= end else []


def fetch_day(d: date, bbox):
    minx, miny, maxx, maxy = bbox
    cql = (
        f"date='{d.isoformat()}' AND "
        f"BBOX(geom,{minx:.6f},{miny:.6f},{maxx:.6f},{maxy:.6f},'EPSG:4326')"
    )
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": TYPE_NAME,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "CQL_FILTER": cql,
    }
    r = SESSION.get(WFS_URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    return payload.get("features", [])


def flag(props, key):
    v = props.get(key)
    if v in (None, "", False):
        return False
    try:
        return int(float(v)) != 0
    except Exception:
        return str(v).strip().lower() in {"true", "yes", "ja"}


def category(props):
    if flag(props, "surface"):
        return "surface"
    if flag(props, "sub_surfac"):
        return "risk"
    if flag(props, "cloud"):
        return "cloud"
    if flag(props, "no_data"):
        return "no_data"
    cls = props.get("class")
    return f"class_{cls}" if cls not in (None, "") else "other"


def process_day(d: date, raw_features, sea_wgs84):
    sea_3006 = transform(TO_3006, sea_wgs84)
    by_cat = defaultdict(list)
    out_features = []

    for feat in raw_features:
        geom_data = feat.get("geometry")
        if not geom_data:
            continue
        try:
            geom = shape(geom_data).buffer(0)
        except Exception:
            continue
        if geom.is_empty:
            continue
        clipped = geom.intersection(sea_wgs84)
        if clipped.is_empty:
            continue

        cat = category(feat.get("properties") or {})
        clipped_3006 = transform(TO_3006, clipped)
        if clipped_3006.is_empty or clipped_3006.area <= 0:
            continue
        by_cat[cat].append(clipped_3006)

        simplified = clipped_3006.simplify(20, preserve_topology=True)
        if simplified.is_empty:
            continue
        props = dict(feat.get("properties") or {})
        props["algae_class"] = cat
        props["source_date"] = d.isoformat()
        out_features.append({
            "type": "Feature",
            "properties": props,
            "geometry": mapping(transform(TO_4326, simplified)),
        })

    area_km2 = {}
    for cat, geoms in by_cat.items():
        area_km2[cat] = round(unary_union(geoms).area / 1e6, 3)

    sea_area = sea_3006.area / 1e6
    known = {"surface", "risk", "cloud", "no_data"}
    classified_area = sum(area_km2.values())
    other_area = sum(v for k, v in area_km2.items() if k not in known)
    classes_pct = {
        k: round(100 * v / sea_area, 3) if sea_area else 0.0
        for k, v in sorted(area_km2.items())
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            "source": "SMHI SE.SR Ytansamling av alger",
            "date": d.isoformat(),
            "note": "Test: SMHI WFS clipped to Lulea municipal sea area and simplified 20 m.",
        },
        "features": out_features,
    }, {
        "date": d.isoformat(),
        "file": f"{d.isoformat()}.geojson",
        "features": len(out_features),
        "sea_area_km2": round(sea_area, 3),
        "surface_area_km2": area_km2.get("surface", 0.0),
        "risk_area_km2": area_km2.get("risk", 0.0),
        "cloud_area_km2": area_km2.get("cloud", 0.0),
        "no_data_area_km2": area_km2.get("no_data", 0.0),
        "surface_pct_sea": round(100 * area_km2.get("surface", 0.0) / sea_area, 3) if sea_area else 0.0,
        "risk_pct_sea": round(100 * area_km2.get("risk", 0.0) / sea_area, 3) if sea_area else 0.0,
        "cloud_pct_sea": round(100 * area_km2.get("cloud", 0.0) / sea_area, 3) if sea_area else 0.0,
        "no_data_pct_sea": round(100 * area_km2.get("no_data", 0.0) / sea_area, 3) if sea_area else 0.0,
        "other_area_km2": round(other_area, 3),
        "other_pct_sea": round(100 * other_area / sea_area, 3) if sea_area else 0.0,
        "classes_area_km2": {k: round(v, 3) for k, v in sorted(area_km2.items())},
        "classes_pct_sea": classes_pct,
        "classified_area_km2": round(classified_area, 3),
    }


def main():
    today = date.today()
    year = test_year(today)
    out_dir = OUT_ROOT / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sea = load_lulea_sea_wgs84()
    bbox = sea.bounds
    dates = candidate_dates(year, today)
    print(f"Algae test year: {year}; dates to check: {len(dates)}")

    existing = {}
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing = {x["date"]: x for x in old.get("dates", [])}
        except Exception:
            existing = {}

    for i, d in enumerate(dates, 1):
        old_meta = existing.get(d.isoformat())
        old_path = out_dir / old_meta["file"] if old_meta and old_meta.get("file") else None
        if RUN_MODE not in {"refresh-all"} and old_meta and old_path and old_path.exists():
            if "classes_pct_sea" in old_meta:
                continue
            try:
                saved = json.loads(old_path.read_text(encoding="utf-8"))
                geo, meta = process_day(d, saved.get("features", []), sea)
                if geo["features"]:
                    old_path.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                    existing[d.isoformat()] = meta
                    print(f"Algae {d}: backfilled class areas from saved GeoJSON")
                    continue
            except Exception as exc:
                print(f"Algae {d}: local backfill warning: {exc}")
        try:
            features = fetch_day(d, bbox)
        except Exception as exc:
            print(f"Algae {d}: WFS warning: {exc}")
            continue
        if not features:
            print(f"Algae {d}: no WFS features in Lulea bbox")
            continue

        geo, meta = process_day(d, features, sea)
        if not geo["features"]:
            print(f"Algae {d}: no polygons overlap Lulea sea")
            continue

        path = out_dir / meta["file"]
        path.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        existing[d.isoformat()] = meta
        print(
            f"Algae {d}: {meta['features']} polygons; "
            f"surface {meta['surface_pct_sea']} %, risk {meta['risk_pct_sea']} %"
        )

    rows = [existing[k] for k in sorted(existing)]
    manifest = {
        "source": "SMHI SE.SR Ytansamling av alger",
        "source_url": "https://www.smhi.se/data/sok-oppna-data-i-utforskaren/se-sr-ytansamling-av-alger",
        "wfs": WFS_URL,
        "year": year,
        "dates": rows,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Algae manifest: {len(rows)} available Lulea map dates for {year}")


if __name__ == "__main__":
    main()
