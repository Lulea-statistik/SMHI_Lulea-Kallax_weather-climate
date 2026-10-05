#!/usr/bin/env python3
"""Fetch SMHI sea-ice analysis maps and aggregate them to Lulea municipality sea area.

No geopandas is used. Shapefiles are read with pyshp, geometries are handled by
Shapely, and all area calculations are performed in EPSG:3006.

The SMHI product is SE.SR Analyskarta havsis. The API exposes daily map packages.
We store only the derived daily statistics, not the downloaded shapefiles.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "seaice"
DAILY_PATH = DATA_DIR / "daily.csv"
SUMMARY_PATH = DATA_DIR / "summary.json"
MAP_GEOJSON_PATH = ROOT / "docs" / "seaice_analysis_area.geojson"
TEST_ICE_DATE = date(2023, 12, 14)
TEST_ICE_GEOJSON_PATH = ROOT / "docs" / "seaice_test_2023-12-14.geojson"
SEASON_MAP_LABEL = "2023/24"
SEASON_MAP_START = date(2023, 10, 15)
SEASON_MAP_END = date(2024, 6, 6)
SEASON_MAP_DIR = ROOT / "docs" / "seaice" / "2023-24"
SEASON_MAP_MANIFEST = SEASON_MAP_DIR / "manifest.json"
NMD_GEO_PATH = ROOT / "data" / "lightning" / "geography_nmd.geojson"

API_BASE = "https://opendata-download-icemap.smhi.se/api/version/1.0"
START_DATE = date(2003, 1, 1)
RECENT_DAYS = 21
TIMEOUT = 90
TARGET_CRS = CRS.from_epsg(3006)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Lulea-statistik-SMHI-seaice/1.0"})

ICE_TYPES = {
    0: "ice_free",
    1: "open_water",
    2: "very_open_ice",
    3: "open_ice",
    4: "close_ice",
    5: "very_close_ice",
    6: "consolidated_ice",
    7: "level_ice",
    8: "fast_ice",
    9: "new_ice",
    10: "rotten_ice",
}
ICEACT_LABELS = {
    "01": "<1/10",
    "10": "1/10",
    "20": "2/10",
    "30": "3/10",
    "40": "4/10",
    "50": "5/10",
    "60": "6/10",
    "70": "7/10",
    "80": "8/10",
    "90": "9/10",
    "91": "9+/10",
    "92": "10/10",
    "98": "isfritt",
}


def season_label(d: date) -> str:
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}/{str(start + 1)[-2:]}"


def load_lulea_sea_3006():
    if not NMD_GEO_PATH.exists():
        raise RuntimeError(f"Missing static Lulea geography: {NMD_GEO_PATH}")
    data = json.loads(NMD_GEO_PATH.read_text(encoding="utf-8"))
    sea = None
    for feat in data.get("features", []):
        if (feat.get("properties") or {}).get("class") == "sea":
            sea = shape(feat["geometry"])
            break
    if sea is None or sea.is_empty:
        raise RuntimeError("Lulea sea polygon is missing from geography_nmd.geojson")
    to_3006 = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True).transform
    return transform(to_3006, sea).buffer(0)


def get(url: str):
    r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r


def find_urls(value):
    out = []
    if isinstance(value, dict):
        for v in value.values():
            out.extend(find_urls(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(find_urls(v))
    elif isinstance(value, str) and value.startswith("http"):
        out.append(value)
    return out


def extract_links(response):
    ctype = (response.headers.get("Content-Type") or "").lower()
    body = response.content
    if "zip" in ctype or body[:2] == b"PK":
        return [response.url]
    text = body.decode("utf-8", errors="replace")
    urls = []
    try:
        parsed = json.loads(text)
        urls.extend(find_urls(parsed))
    except Exception:
        pass
    try:
        root = ET.fromstring(text)
        for elem in root.iter():
            href = elem.attrib.get("href")
            if href:
                urls.append(href)
            if elem.text and elem.text.strip().startswith("http"):
                urls.append(elem.text.strip())
    except Exception:
        pass
    urls.extend(re.findall(r'https?://[^"\'<>\s]+', text))
    return list(dict.fromkeys(urls))


def daily_package_url(d: date):
    base = f"{API_BASE}/year/{d.year}/month/{d.month}/day/{d.day}"
    for suffix in ("", ".xml", ".json"):
        try:
            r = get(base + suffix)
        except Exception as exc:
            print(f"Sea-ice metadata warning {base + suffix}: {exc}", file=sys.stderr)
            continue
        if r is None:
            continue
        links = extract_links(r)
        candidates = [u for u in links if ".zip" in u.lower()]
        if candidates:
            return candidates[-1]
        # Some API responses redirect directly to the package.
        if (r.headers.get("Content-Type") or "").lower().find("zip") >= 0 or r.content[:2] == b"PK":
            return r.url
    return None


def read_shapefile_zip(raw: bytes):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    shp_names = [n for n in names if n.lower().endswith(".shp")]
    if not shp_names:
        raise RuntimeError("Downloaded sea-ice package contains no .shp file")
    shp_name = shp_names[0]
    stem = shp_name[:-4]
    dbf_name = next((n for n in names if n.lower() == (stem + ".dbf").lower()), None)
    shx_name = next((n for n in names if n.lower() == (stem + ".shx").lower()), None)
    prj_name = next((n for n in names if n.lower() == (stem + ".prj").lower()), None)
    if not dbf_name:
        raise RuntimeError("Sea-ice shapefile is missing .dbf")
    if not prj_name:
        raise RuntimeError("Sea-ice shapefile is missing .prj; source CRS cannot be verified")

    src_crs = CRS.from_wkt(z.read(prj_name).decode("utf-8", errors="replace"))
    transformer = None if src_crs == TARGET_CRS else Transformer.from_crs(src_crs, TARGET_CRS, always_xy=True).transform

    reader = shapefile.Reader(
        shp=io.BytesIO(z.read(shp_name)),
        shx=io.BytesIO(z.read(shx_name)) if shx_name else None,
        dbf=io.BytesIO(z.read(dbf_name)),
    )
    fields = [f[0].lower() for f in reader.fields[1:]]
    for sr in reader.iterShapeRecords():
        props = {fields[i]: sr.record[i] for i in range(min(len(fields), len(sr.record)))}
        geom = shape(sr.shape.__geo_interface__)
        if transformer is not None:
            geom = transform(transformer, geom)
        yield geom, props, src_crs.to_string()


def as_number(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def as_int(v):
    x = as_number(v)
    return int(x) if x is not None else None


def normalize_iceact(v):
    if v is None:
        return ""
    s = str(v).strip()
    try:
        return f"{int(float(s)):02d}"
    except Exception:
        return s


def aggregate_day(d: date, raw: bytes, sea_geom):
    sea_area = sea_geom.area
    coverage_geoms = []
    ice_geoms = []
    fast_geoms = []
    concentration_geoms = defaultdict(list)
    type_geoms = defaultdict(list)
    weighted_t = 0.0
    weighted_area = 0.0
    max_t = None
    min_t = None
    source_crs = None
    chartdates = []

    for geom, props, crs_text in read_shapefile_zip(raw):
        source_crs = source_crs or crs_text
        if geom.is_empty:
            continue
        clipped = geom.intersection(sea_geom)
        if clipped.is_empty:
            continue
        area = clipped.area
        if area <= 0:
            continue

        coverage_geoms.append(clipped)
        ice_type = as_int(props.get("type"))
        iceact = normalize_iceact(props.get("iceact"))
        mean_t = as_number(props.get("icetck"))
        feature_max = as_number(props.get("icemax"))
        feature_min = as_number(props.get("icemin"))
        chartdate = props.get("chartdate")
        if chartdate:
            chartdates.append(str(chartdate)[:10])

        is_ice = ice_type is not None and ice_type >= 2
        if is_ice:
            ice_geoms.append(clipped)
            if ice_type == 8:
                fast_geoms.append(clipped)
            type_geoms[ICE_TYPES.get(ice_type, f"type_{ice_type}")].append(clipped)
            if iceact:
                concentration_geoms[ICEACT_LABELS.get(iceact, iceact)].append(clipped)
            if mean_t is not None:
                weighted_t += mean_t * area
                weighted_area += area
            if feature_max is not None:
                max_t = feature_max if max_t is None else max(max_t, feature_max)
            if feature_min is not None:
                min_t = feature_min if min_t is None else min(min_t, feature_min)

    coverage_geom = unary_union(coverage_geoms).buffer(0) if coverage_geoms else None
    coverage_area = coverage_geom.area if coverage_geom is not None else 0.0
    ice_area = unary_union(ice_geoms).area if ice_geoms else 0.0
    fast_area = unary_union(fast_geoms).area if fast_geoms else 0.0
    concentration = {
        k: round(unary_union(v).area / 1e6, 3)
        for k, v in concentration_geoms.items() if v
    }
    types = {
        k: round(unary_union(v).area / 1e6, 3)
        for k, v in type_geoms.items() if v
    }
    effective_date = sorted(chartdates)[-1] if chartdates else d.isoformat()
    row = {
        "date": effective_date,
        "season": season_label(date.fromisoformat(effective_date)),
        "sea_area_km2": round(sea_area / 1e6, 3),
        "analysis_coverage_area_km2": round(coverage_area / 1e6, 3),
        "analysis_coverage_pct": round(100 * coverage_area / sea_area, 2) if sea_area else 0.0,
        "uncovered_area_km2": round(max(0.0, sea_area - coverage_area) / 1e6, 3),
        "ice_area_km2": round(ice_area / 1e6, 6),
        # Keep enough precision for tiny late/early-season ice remnants. With
        # two decimals, a real but very small ice area could be displayed as
        # 0.00 %, while still having a valid non-zero thickness.
        "ice_share_pct": round(100 * ice_area / coverage_area, 4) if coverage_area else 0.0,
        "ice_share_municipal_pct": round(100 * ice_area / sea_area, 4) if sea_area else 0.0,
        "fast_ice_area_km2": round(fast_area / 1e6, 6),
        "fast_ice_share_pct": round(100 * fast_area / coverage_area, 4) if coverage_area else 0.0,
        # Thickness is defined only where ice exists. A genuinely ice-free
        # analysis therefore has 0 cm thickness; if ice exists but SMHI has
        # no thickness attribute, keep the value missing rather than inventing it.
        "mean_ice_thickness_cm": 0.0 if ice_area <= 0 else (round(weighted_t / weighted_area, 1) if weighted_area else None),
        "max_ice_thickness_cm": 0.0 if ice_area <= 0 else (round(max_t, 1) if max_t is not None else None),
        "min_ice_thickness_cm": 0.0 if ice_area <= 0 else (round(min_t, 1) if min_t is not None else None),
        "concentration_area_km2": concentration,
        "ice_type_area_km2": types,
        "source_crs": source_crs,
    }
    return row, coverage_geom


def save_map_geojson(sea_geom, coverage_geom, source_date):
    if coverage_geom is None or coverage_geom.is_empty:
        return
    to_4326 = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True).transform
    sea_wgs84 = transform(to_4326, sea_geom)
    coverage_wgs84 = transform(to_4326, coverage_geom)
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "kind": "municipal_sea",
                    "name": "Luleå kommunal havsyta",
                },
                "geometry": mapping(sea_wgs84),
            },
            {
                "type": "Feature",
                "properties": {
                    "kind": "smhi_analysis",
                    "name": "SMHI analyserad havsyta",
                    "source_date": source_date,
                },
                "geometry": mapping(coverage_wgs84),
            },
        ],
    }
    MAP_GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_GEOJSON_PATH.write_text(
        json.dumps(feature_collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )



def save_test_ice_geojson(raw: bytes, sea_geom, source_date: str):
    """Export one representative winter map for a lightweight web-map test.

    Only polygons classified as ice are included. Geometry is clipped to
    Lulea's sea area and simplified by 20 metres in EPSG:3006 before export.
    """
    features = []
    to_4326 = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True).transform

    for geom, props, _ in read_shapefile_zip(raw):
        if geom.is_empty:
            continue
        clipped = geom.intersection(sea_geom)
        if clipped.is_empty or clipped.area <= 0:
            continue

        ice_type = as_int(props.get("type"))
        if ice_type is None or ice_type < 2:
            continue

        simplified = clipped.simplify(20, preserve_topology=True)
        if simplified.is_empty:
            continue

        features.append({
            "type": "Feature",
            "properties": {
                "ice_type": ice_type,
                "ice_type_name": ICE_TYPES.get(ice_type, f"type_{ice_type}"),
                "iceact": normalize_iceact(props.get("iceact")),
                "mean_thickness_cm": as_number(props.get("icetck")),
                "max_thickness_cm": as_number(props.get("icemax")),
                "min_thickness_cm": as_number(props.get("icemin")),
                "source_date": source_date,
            },
            "geometry": mapping(transform(to_4326, simplified)),
        })

    fc = {
        "type": "FeatureCollection",
        "properties": {
            "source": "SMHI SE.SR Analyskarta havsis",
            "source_date": source_date,
            "note": "Performance test: ice polygons clipped to Lulea sea area and simplified 20 m in EPSG:3006 before EPSG:4326 export.",
        },
        "features": features,
    }
    TEST_ICE_GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_ICE_GEOJSON_PATH.write_text(
        json.dumps(fc, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Sea ice test polygons: {len(features)} features written for {source_date}.")



def build_season_map_files(rows, sea_geom):
    """Build a lazy-loadable GeoJSON archive for the 2023/24 test season.

    One file is written per available SMHI map date. The browser therefore
    downloads only the selected day rather than the whole winter at once.
    Existing day files are reused, making later workflow runs cheap.
    """
    season_dates = [
        date.fromisoformat(k)
        for k, r in sorted(rows.items())
        if r.get("season") == SEASON_MAP_LABEL
        and SEASON_MAP_START <= date.fromisoformat(k) <= SEASON_MAP_END
    ]
    if not season_dates:
        print(f"Sea ice season map: no dates available for {SEASON_MAP_LABEL}.")
        return

    SEASON_MAP_DIR.mkdir(parents=True, exist_ok=True)
    manifest_dates = []

    for i, d in enumerate(season_dates, 1):
        out_path = SEASON_MAP_DIR / f"{d.isoformat()}.geojson"
        if not out_path.exists():
            package = daily_package_url(d)
            if not package:
                continue
            r = get(package)
            if r is None:
                continue

            features = []
            to_4326 = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True).transform
            for geom, props, _ in read_shapefile_zip(r.content):
                if geom.is_empty:
                    continue
                clipped = geom.intersection(sea_geom)
                if clipped.is_empty or clipped.area <= 0:
                    continue
                ice_type = as_int(props.get("type"))
                if ice_type is None or ice_type < 2:
                    continue
                simplified = clipped.simplify(20, preserve_topology=True)
                if simplified.is_empty:
                    continue
                features.append({
                    "type": "Feature",
                    "properties": {
                        "ice_type": ice_type,
                        "ice_type_name": ICE_TYPES.get(ice_type, f"type_{ice_type}"),
                        "iceact": normalize_iceact(props.get("iceact")),
                        "mean_thickness_cm": as_number(props.get("icetck")),
                        "max_thickness_cm": as_number(props.get("icemax")),
                        "min_thickness_cm": as_number(props.get("icemin")),
                        "source_date": d.isoformat(),
                    },
                    "geometry": mapping(transform(to_4326, simplified)),
                })

            fc = {
                "type": "FeatureCollection",
                "properties": {
                    "source": "SMHI SE.SR Analyskarta havsis",
                    "source_date": d.isoformat(),
                    "season": SEASON_MAP_LABEL,
                    "simplification_m": 20,
                },
                "features": features,
            }
            out_path.write_text(
                json.dumps(fc, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

        if out_path.exists():
            manifest_dates.append({
                "date": d.isoformat(),
                "file": out_path.name,
                "ice_share_pct": rows[d.isoformat()].get("ice_share_pct"),
                "mean_ice_thickness_cm": rows[d.isoformat()].get("mean_ice_thickness_cm"),
                "max_ice_thickness_cm": rows[d.isoformat()].get("max_ice_thickness_cm"),
            })

        if i % 25 == 0:
            print(f"Sea ice season map progress {i}/{len(season_dates)}.")

    manifest = {
        "season": SEASON_MAP_LABEL,
        "start_date": SEASON_MAP_START.isoformat(),
        "end_date": SEASON_MAP_END.isoformat(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "simplification_m": 20,
        "dates": manifest_dates,
    }
    SEASON_MAP_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Sea ice season map: {len(manifest_dates)} lazy-loadable dates written for {SEASON_MAP_LABEL}.")


def load_daily():
    rows = {}
    if not DAILY_PATH.exists():
        return rows
    with DAILY_PATH.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows[r["date"]] = {
                    "date": r["date"],
                    "season": r["season"],
                    "sea_area_km2": float(r["sea_area_km2"]),
                    "analysis_coverage_area_km2": float(r["analysis_coverage_area_km2"]) if r.get("analysis_coverage_area_km2") else None,
                    "analysis_coverage_pct": float(r["analysis_coverage_pct"]) if r.get("analysis_coverage_pct") else None,
                    "uncovered_area_km2": float(r["uncovered_area_km2"]) if r.get("uncovered_area_km2") else None,
                    "ice_area_km2": float(r["ice_area_km2"]),
                    "ice_share_pct": float(r["ice_share_pct"]),
                    "ice_share_municipal_pct": float(r["ice_share_municipal_pct"]) if r.get("ice_share_municipal_pct") else float(r["ice_share_pct"]),
                    "fast_ice_area_km2": float(r["fast_ice_area_km2"]),
                    "fast_ice_share_pct": float(r["fast_ice_share_pct"]),
                    "mean_ice_thickness_cm": float(r["mean_ice_thickness_cm"]) if r["mean_ice_thickness_cm"] else None,
                    "max_ice_thickness_cm": float(r["max_ice_thickness_cm"]) if r["max_ice_thickness_cm"] else None,
                    "min_ice_thickness_cm": float(r["min_ice_thickness_cm"]) if r["min_ice_thickness_cm"] else None,
                    "concentration_area_km2": json.loads(r["concentration_area_km2"] or "{}"),
                    "ice_type_area_km2": json.loads(r["ice_type_area_km2"] or "{}"),
                    "source_crs": r.get("source_crs") or None,
                }
            except Exception:
                continue
    return rows


def save_daily(rows):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "date", "season", "sea_area_km2", "analysis_coverage_area_km2", "analysis_coverage_pct",
        "uncovered_area_km2", "ice_area_km2", "ice_share_pct", "ice_share_municipal_pct",
        "fast_ice_area_km2", "fast_ice_share_pct", "mean_ice_thickness_cm",
        "max_ice_thickness_cm", "min_ice_thickness_cm",
        "concentration_area_km2", "ice_type_area_km2", "source_crs",
    ]
    with DAILY_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for key in sorted(rows):
            r = dict(rows[key])
            r["concentration_area_km2"] = json.dumps(r.get("concentration_area_km2") or {}, ensure_ascii=False, separators=(",", ":"))
            r["ice_type_area_km2"] = json.dumps(r.get("ice_type_area_km2") or {}, ensure_ascii=False, separators=(",", ":"))
            w.writerow(r)


def build_summary(rows):
    daily = [rows[k] for k in sorted(rows)]
    by_season = defaultdict(list)
    for r in daily:
        by_season[r["season"]].append(r)

    seasonal = []
    for season, rr in sorted(by_season.items()):
        ice_days = [r for r in rr if r["ice_share_pct"] > 0]
        max_ice = max(rr, key=lambda r: r["ice_share_pct"])
        max_fast = max(rr, key=lambda r: r["fast_ice_share_pct"])
        thickness = [r["mean_ice_thickness_cm"] for r in rr if r["mean_ice_thickness_cm"] is not None]
        first = ice_days[0]["date"] if ice_days else None
        last = ice_days[-1]["date"] if ice_days else None
        length_days = (date.fromisoformat(last) - date.fromisoformat(first)).days + 1 if first and last else 0
        seasonal.append({
            "season": season,
            "start_year": int(season[:4]),
            "max_ice_area_km2": max_ice["ice_area_km2"],
            "max_ice_share_pct": max_ice["ice_share_pct"],
            "max_ice_date": max_ice["date"],
            "max_fast_ice_area_km2": max_fast["fast_ice_area_km2"],
            "max_fast_ice_share_pct": max_fast["fast_ice_share_pct"],
            "max_fast_ice_date": max_fast["date"],
            "mean_ice_thickness_cm": round(sum(thickness) / len(thickness), 1) if thickness else None,
            "first_ice_date": first,
            "last_ice_date": last,
            "season_length_days": length_days,
            "observed_ice_days": len(ice_days),
            "map_days": len(rr),
        })

    source_crs = sorted({r.get("source_crs") for r in daily if r.get("source_crs")})
    out = {
        "source": "SMHI SE.SR Analyskarta havsis",
        "source_url": "https://www.smhi.se/data/hav-och-havsmiljo/havsis",
        "api": API_BASE,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "analysis_crs": "EPSG:3006",
        "source_crs_seen": source_crs,
        "geography": "Lulea municipality sea area from the repository's static NMD geography",
        "method_note": "Daily SMHI sea-ice polygons are reprojected to EPSG:3006 and intersected with Lulea municipality sea geometry before area statistics are calculated. Ice-share percentages use the portion of the municipal sea area actually covered by that day's SMHI analysis polygons as denominator; total municipal sea area and coverage percentage are retained separately for quality control.",
        "daily": daily,
        "seasonal": seasonal,
    }
    SUMMARY_PATH.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def is_ice_season_date(d: date):
    """Daily sea-ice update window: 15 October through 6 June."""
    if d.month > 10 or d.month < 6:
        return True
    if d.month == 10:
        return d.day >= 15
    if d.month == 6:
        return d.day <= 6
    return False


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_daily()
    sea_geom = load_lulea_sea_3006()
    mode = os.environ.get("RUN_MODE", "auto")

    # Schema v2 adds explicit map-coverage quality metrics. Existing historical
    # rows from v1 must be rebuilt once because those values cannot be reconstructed
    # from the aggregated CSV alone.
    needs_coverage_rebuild = bool(rows) and any(r.get("analysis_coverage_area_km2") is None for r in rows.values())
    if needs_coverage_rebuild and mode not in {"bootstrap", "refresh-all"}:
        print("Sea-ice quality schema changed: historical rows need one refresh-all run to calculate map coverage.")
        build_summary(rows)
        return 0

    today = datetime.now(timezone.utc).date()
    if mode in {"bootstrap", "refresh-all"} or not rows:
        start_year = int(os.environ.get("SEAICE_START_YEAR", START_DATE.year))
        start = date(start_year, 1, 1)
        candidates = [d for d in daterange(start, today) if is_ice_season_date(d)]
        if mode != "refresh-all":
            candidates = [d for d in candidates if d.isoformat() not in rows]
        print(f"Sea-ice history scan: {len(candidates):,} candidate dates from {start}.")
    else:
        start = today - timedelta(days=RECENT_DAYS - 1)
        candidates = [d for d in daterange(start, today) if is_ice_season_date(d)]
        if not candidates:
            print("Sea-ice incremental scan skipped: today is outside the 15 October-6 June update window.")
            if not MAP_GEOJSON_PATH.exists() and rows:
                latest_date = date.fromisoformat(sorted(rows)[-1])
                package = daily_package_url(latest_date)
                if package:
                    r = get(package)
                    if r is not None:
                        _, coverage_geom = aggregate_day(latest_date, r.content, sea_geom)
                        if coverage_geom is not None and not coverage_geom.is_empty:
                            save_map_geojson(sea_geom, coverage_geom, latest_date.isoformat())
                            print(f"Sea ice map geometry backfilled from {latest_date.isoformat()}.")
            if not TEST_ICE_GEOJSON_PATH.exists():
                package = daily_package_url(TEST_ICE_DATE)
                if package:
                    r = get(package)
                    if r is not None:
                        save_test_ice_geojson(r.content, sea_geom, TEST_ICE_DATE.isoformat())
            if not SEASON_MAP_MANIFEST.exists():
                build_season_map_files(rows, sea_geom)
            build_summary(rows)
            return 0
        print(f"Sea-ice incremental scan: {len(candidates)} recent dates within the 15 October-6 June update window.")

    updated = 0
    found = 0
    latest_coverage_geom = None
    latest_coverage_date = None
    for i, d in enumerate(candidates, 1):
        package = daily_package_url(d)
        if not package:
            continue
        found += 1
        try:
            r = get(package)
            if r is None:
                continue
            row, coverage_geom = aggregate_day(d, r.content, sea_geom)
            rows[row["date"]] = row
            if coverage_geom is not None and not coverage_geom.is_empty:
                latest_coverage_geom = coverage_geom
                latest_coverage_date = row["date"]
            updated += 1
            if updated % 25 == 0:
                save_daily(rows)
                print(f"Sea ice: saved checkpoint after {updated} maps.")
        except Exception as exc:
            print(f"Sea-ice map failed {d} ({package}): {exc}", file=sys.stderr)
        if i % 250 == 0:
            print(f"Sea-ice scan progress {i}/{len(candidates)}; packages found {found}; maps aggregated {updated}.")

    if latest_coverage_geom is not None:
        save_map_geojson(sea_geom, latest_coverage_geom, latest_coverage_date)
        print(f"Sea ice map geometry updated from {latest_coverage_date}.")

    if not TEST_ICE_GEOJSON_PATH.exists():
        package = daily_package_url(TEST_ICE_DATE)
        if package:
            r = get(package)
            if r is not None:
                save_test_ice_geojson(r.content, sea_geom, TEST_ICE_DATE.isoformat())
    if not SEASON_MAP_MANIFEST.exists():
        build_season_map_files(rows, sea_geom)
    save_daily(rows)
    build_summary(rows)
    print(f"Sea ice: {len(rows):,} daily Lulea summaries stored; {updated} maps processed this run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
