#!/usr/bin/env python3
"""Build an observed snow-depth map for Lulea municipality from SMHI MetObs parameter 8."""

from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
NMD_GEO_PATH = ROOT / "data" / "lightning" / "geography_nmd.geojson"
OUT_ROOT = ROOT / "docs" / "snowmap"
BOUNDARY_PATH = ROOT / "docs" / "snowmap_boundary.geojson"
API = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/8.json"
STATION_DATA = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/8/station/{station}/period/corrected-archive/data.csv"
TIMEOUT = 90
BUFFER_KM = 60

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Lulea-statistik-SMHI-snowmap/1.0"})
TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def load_municipality():
    data = json.loads(NMD_GEO_PATH.read_text(encoding="utf-8"))
    geoms = []
    for feat in data.get("features", []):
        try:
            g = shape(feat["geometry"]).buffer(0)
        except Exception:
            continue
        if not g.is_empty:
            geoms.append(g)
    if not geoms:
        raise RuntimeError("Lulea municipality geometry is missing")
    return unary_union(geoms).buffer(0)


def station_catalog():
    r = SESSION.get(API, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    return payload.get("station", payload.get("stations", []))


def station_key(s):
    return str(s.get("key") or s.get("id") or s.get("station") or "")


def get_float(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def parse_station_csv(text):
    # SMHI corrected archive is semicolon separated and may contain preamble lines.
    lines = text.replace("\ufeff", "").splitlines()
    header_i = None
    for i, line in enumerate(lines):
        low = line.lower()
        if "datum" in low and ("snödjup" in low or "värde" in low or "value" in low):
            header_i = i
            break
    if header_i is None:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_i:])), delimiter=";")
    rows = []
    for row in reader:
        d_raw = row.get("Datum") or row.get("datum") or row.get("Date") or ""
        d_raw = str(d_raw).strip()[:10]
        try:
            d = date.fromisoformat(d_raw)
        except Exception:
            continue

        val = None
        for key, raw in row.items():
            lk = str(key or "").lower()
            if "snödjup" in lk or lk in {"värde", "value"}:
                val = get_float(raw)
                if val is not None:
                    break
        if val is None:
            # Fallback: first numeric field after date/time that looks like snow depth.
            for key, raw in row.items():
                if str(key or "").lower() in {"datum", "tid (utc)", "tid"}:
                    continue
                v = get_float(raw)
                if v is not None and 0 <= v <= 5000:
                    val = v
                    break
        if val is None:
            continue
        # SMHI parameter 8 is published in metres. Convert physical snow
        # depth to centimetres before storing it in the report. Negative
        # values (-0.01 and -0.02) are SMHI special codes, not depths, so
        # exclude them from numeric interpolation.
        if val < 0:
            continue
        rows.append((d, val * 100.0))
    return rows


def season_name(d):
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    municipality = load_municipality()
    municipality_3006 = transform(TO_3006, municipality)
    search_area_3006 = municipality_3006.buffer(BUFFER_KM * 1000)

    boundary_feature = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "Lulea kommun", "source": "Lulea municipality/NMD working geometry"},
            "geometry": mapping(municipality),
        }],
    }
    BOUNDARY_PATH.write_text(json.dumps(boundary_feature, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    stations = []
    for s in station_catalog():
        lat = get_float(s.get("latitude"))
        lon = get_float(s.get("longitude"))
        key = station_key(s)
        if not key or lat is None or lon is None:
            continue
        p3006 = transform(TO_3006, Point(lon, lat))
        if not search_area_3006.contains(p3006):
            continue
        inside = municipality_3006.contains(p3006)
        distance_km = municipality_3006.distance(p3006) / 1000 if not inside else 0.0
        stations.append({
            "id": key,
            "name": s.get("name") or s.get("title") or key,
            "latitude": lat,
            "longitude": lon,
            "inside_municipality": inside,
            "distance_to_municipality_km": round(distance_km, 1),
            "active": bool(s.get("active", False)),
            "from": s.get("from"),
            "to": s.get("to"),
        })

    print(f"Snow stations selected: {len(stations)} within {BUFFER_KM} km of Lulea municipality")
    by_season = defaultdict(list)
    station_meta = {s["id"]: s for s in stations}

    for i, s in enumerate(stations, 1):
        url = STATION_DATA.format(station=s["id"])
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            observations = parse_station_csv(r.text)
        except Exception as exc:
            print(f"Snow station {s['id']} {s['name']}: {exc}")
            continue
        print(f"Snow station {i}/{len(stations)} {s['name']}: {len(observations)} observations")
        for d, depth in observations:
            by_season[season_name(d)].append({
                "date": d.isoformat(),
                "station_id": s["id"],
                "depth_cm": round(depth, 1),
            })

    index = {
        "source": "SMHI Meteorologiska observationer - Snodjup dygnsvarde, parameter 8 (meter converted to cm)",
        "source_url": "https://www.smhi.se/data/sok-oppna-data-i-utforskaren/se-acmf-meteorologiska-observationer-snodjup-dygnsvarde",
        "map_reference_url": "https://www.smhi.se/vader/observationer/snodjup",
        "buffer_km": BUFFER_KM,
        "stations": stations,
        "seasons": [],
    }

    for season in sorted(by_season):
        rows = sorted(by_season[season], key=lambda r: (r["date"], r["station_id"]))
        if not rows:
            continue
        dates = sorted({r["date"] for r in rows})
        # Daily summary uses only stations inside municipality when available, otherwise all nearby stations.
        daily = []
        grouped = defaultdict(list)
        for r in rows:
            grouped[r["date"]].append(r)
        for d in dates:
            rr = grouped[d]
            inside = [x for x in rr if station_meta.get(x["station_id"], {}).get("inside_municipality")]
            use = inside or rr
            vals = [x["depth_cm"] for x in use]
            daily.append({
                "date": d,
                "stations": len(use),
                "mean_cm": round(sum(vals) / len(vals), 1) if vals else None,
                "max_cm": round(max(vals), 1) if vals else None,
                "snow_cover_share_pct": round(100 * sum(v >= 1 for v in vals) / len(vals), 1) if vals else None,
            })

        payload = {
            "season": season,
            "stations": station_meta,
            "observations": rows,
            "daily": daily,
        }
        filename = f"{season}.json"
        (OUT_ROOT / filename).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        index["seasons"].append({
            "season": season,
            "file": filename,
            "first_date": dates[0],
            "last_date": dates[-1],
            "dates": len(dates),
            "observations": len(rows),
        })

    index["seasons"].sort(key=lambda x: x["season"])
    (OUT_ROOT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snow map: {len(index['seasons'])} seasons written")


if __name__ == "__main__":
    main()
