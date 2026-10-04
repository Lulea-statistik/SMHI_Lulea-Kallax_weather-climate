#!/usr/bin/env python3
"""Fetch SMHI historical lightning data and classify strikes within Lulea municipality.

Geography:
- Municipality boundary and DeSO land polygons are discovered from SCB WFS.
- Land polygons >= 100 km2 are treated as mainland; smaller disconnected polygons as islands.
- The largest municipality-minus-land water polygon is treated as sea; other water is inland water.
- Points within 500 m of a land/water boundary are classified as coast_uncertain.

The 500 m uncertainty zone follows SMHI's statement that median positioning error
under normal operation should be below 500 m, while individual errors can be larger.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape, mapping
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "lightning"
SUMMARY_PATH = OUT_DIR / "summary.json"
GEO_PATH = OUT_DIR / "geography.geojson"

ATOM_URL = "https://opendata-download-lightning.smhi.se/api/version/latest.atom"
SCB_WFS = "https://geodata.scb.se/geoserver/stat/wfs"
MUNICIPALITY_ARCGIS = "https://services-eu1.arcgis.com/Ek4rv9ndj9nQOpV3/arcgis/rest/services/Region_kommun/FeatureServer/1/query"
MUNICIPALITY_CODE = "2580"
COAST_UNCERTAINTY_M = 500.0
MAINLAND_MIN_AREA_KM2 = 100.0
TIMEOUT = 90

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Lulea-statistik-SMHI-lightning/1.0"})

TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def get(url: str) -> requests.Response:
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def discover_deso_feature_type() -> str:
    r = get(f"{SCB_WFS}?service=WFS&version=1.1.0&request=GetCapabilities")
    root = ET.fromstring(r.content)
    names = [e.text or "" for e in root.iter() if e.tag.endswith("Name")]
    deso = next((n for n in names if "deso" in n.lower() and "2025" in n.lower()), None)
    if not deso:
        deso = next((n for n in names if "deso" in n.lower()), None)
    if not deso:
        raise RuntimeError("Could not discover SCB DeSO feature type")
    return deso


def fetch_municipality_geometry():
    # Administrative municipality polygon including municipal water.
    # Source: Region Norrbotten / ArcGIS FeatureServer, layer Kommungränser.
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    r = SESSION.get(MUNICIPALITY_ARCGIS, params=params, timeout=TIMEOUT)
    if r.ok:
        try:
            data = r.json()
            matches = []
            for feat in data.get("features", []):
                props = feat.get("properties") or {}
                values = [str(v).lower() for v in props.values() if v is not None]
                if any(v == "2580" or "luleå" in v or "lulea" in v for v in values):
                    matches.append(shape(feat["geometry"]))
            if matches:
                return unary_union(matches)
        except Exception:
            pass

    # Fallback to ArcGIS JSON if GeoJSON output is unavailable.
    params["f"] = "json"
    params["outSR"] = "3006"
    r = SESSION.get(MUNICIPALITY_ARCGIS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    geoms = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes") or {}
        values = [str(v).lower() for v in attrs.values() if v is not None]
        if not any(v == "2580" or "luleå" in v or "lulea" in v for v in values):
            continue
        rings = (feat.get("geometry") or {}).get("rings") or []
        ring_polys = []
        for ring in rings:
            if len(ring) >= 4:
                try:
                    p = Polygon(ring)
                    if p.is_valid and not p.is_empty:
                        ring_polys.append(p)
                except Exception:
                    pass
        if ring_polys:
            geoms.append(unary_union(ring_polys))
    if not geoms:
        raise RuntimeError("Could not find Luleå municipality in ArcGIS municipality layer")
    # Already EPSG:3006 in fallback branch.
    return transform(TO_4326, unary_union(geoms))


def wfs_geojson(type_name: str, filter_field_candidates: list[str]) -> dict:
    last_error = None
    for field in filter_field_candidates:
        params = {
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typeName": type_name,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "CQL_FILTER": f"{field}='{MUNICIPALITY_CODE}'",
        }
        try:
            r = SESSION.get(SCB_WFS, params=params, timeout=TIMEOUT)
            if r.ok:
                data = r.json()
                if data.get("features"):
                    return data
            last_error = f"{r.status_code}: {r.text[:200]}"
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(f"SCB WFS query failed for {type_name}: {last_error}")


def build_geography():
    deso_type = discover_deso_feature_type()
    deso = wfs_geojson(deso_type, ["kommunkod", "KOMMUNKOD", "kommun_kod", "KnKod"])

    land_wgs = unary_union([shape(f["geometry"]) for f in deso["features"]])
    municipality_wgs = fetch_municipality_geometry()

    land = transform(TO_3006, land_wgs)
    municipality = transform(TO_3006, municipality_wgs)

    land_parts = list(land.geoms) if land.geom_type == "MultiPolygon" else [land]
    mainland_parts = [g for g in land_parts if g.area / 1_000_000 >= MAINLAND_MIN_AREA_KM2]
    island_parts = [g for g in land_parts if g.area / 1_000_000 < MAINLAND_MIN_AREA_KM2]
    mainland = unary_union(mainland_parts)
    islands = unary_union(island_parts)

    water = municipality.difference(land)
    water_parts = list(water.geoms) if water.geom_type == "MultiPolygon" else [water]
    water_parts = [g for g in water_parts if not g.is_empty and g.area > 0]
    water_parts.sort(key=lambda g: g.area, reverse=True)
    sea = water_parts[0] if water_parts else municipality.buffer(0).difference(municipality.buffer(0))
    inland_water = unary_union(water_parts[1:]) if len(water_parts) > 1 else sea.difference(sea)

    coast_boundary = land.boundary
    bounds = municipality_wgs.bounds

    # simplified copy for documentation / later map rendering
    features = []
    for name, geom in [
        ("municipality", municipality),
        ("mainland", mainland),
        ("islands", islands),
        ("sea", sea),
        ("inland_water", inland_water),
    ]:
        if geom.is_empty:
            continue
        simple = geom.simplify(20, preserve_topology=True)
        features.append({"type": "Feature", "properties": {"class": name}, "geometry": mapping(transform(TO_4326, simple))})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GEO_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    return {
        "municipality": municipality,
        "land": land,
        "mainland": mainland,
        "islands": islands,
        "sea": sea,
        "inland_water": inland_water,
        "coast_boundary": coast_boundary,
        "bounds": bounds,
        "deso_type": deso_type,
        "kommun_type": "Region_kommun/FeatureServer/1",
    }


def crawl_atom(url: str, seen: set[str], out: list[str], depth: int = 0):
    if depth > 5 or url in seen:
        return
    seen.add(url)
    r = get(url)
    root = ET.fromstring(r.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for link in root.findall(".//a:link", ns):
        href = link.attrib.get("href")
        if not href:
            continue
        href = urljoin(url, href)
        low = href.lower()
        if low.endswith(".atom"):
            crawl_atom(href, seen, out, depth + 1)
        elif any(x in low for x in [".json", ".txt", ".csv", ".ualf", ".gz", ".zip"]):
            out.append(href)


def date_from_url(url: str):
    m = re.search(r"(20\d{2})[-_/]?([01]\d)[-_/]?([0-3]\d)", url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc).date()
        except ValueError:
            return None
    return None


def iter_payload_text(url: str):
    raw = get(url).content
    low = url.lower()
    if low.endswith(".gz"):
        raw = gzip.decompress(raw)
    elif low.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if name.endswith("/"):
                    continue
                yield z.read(name).decode("utf-8", errors="replace")
        return
    yield raw.decode("utf-8", errors="replace")


def parse_ualf_fields(fields):
    if len(fields) < 10:
        return None
    offset = 0
    if not re.fullmatch(r"20\d{2}", str(fields[0])):
        offset = 1
    if len(fields) < offset + 10:
        return None
    try:
        year, month, day = map(int, fields[offset:offset+3])
        hour, minute, second = map(int, fields[offset+3:offset+6])
        nanosecond = int(float(fields[offset+6]))
        lat = float(fields[offset+7])
        lon = float(fields[offset+8])
        current = float(fields[offset+9])
        multiplicity = int(float(fields[offset+10])) if len(fields) > offset+10 else 0
        chi = float(fields[offset+17]) if len(fields) > offset+17 else None
        cloud = int(float(fields[offset+21])) if len(fields) > offset+21 else None
        dt = datetime(year, month, day, hour, minute, second, min(999999, nanosecond // 1000), tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return {"datetime": dt, "lat": lat, "lon": lon, "current_ka": current, "multiplicity": multiplicity, "chi_square": chi, "cloud_indicator": cloud}


def parse_json_record(v):
    if isinstance(v, str):
        return parse_ualf_fields(v.replace(",", " ").split())
    if isinstance(v, list):
        return parse_ualf_fields(v)
    if not isinstance(v, dict):
        return None
    try:
        lat = float(v.get("lat", v.get("latitude")))
        lon = float(v.get("lon", v.get("longitude")))
    except (TypeError, ValueError):
        return None
    stamp = v.get("timestamp") or v.get("time") or v.get("datetime")
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except Exception:
        return None
    return {
        "datetime": dt,
        "lat": lat,
        "lon": lon,
        "current_ka": v.get("current", v.get("peakCurrent", v.get("peak_current"))),
        "multiplicity": v.get("multiplicity"),
        "chi_square": v.get("chiSquare", v.get("chi_square")),
        "cloud_indicator": v.get("cloudIndicator", v.get("cloud_indicator")),
    }


def parse_payload(text: str):
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
            values = data.get("values", data.get("value", [])) if isinstance(data, dict) else data
            for v in values:
                rec = parse_json_record(v)
                if rec:
                    yield rec
            return
        except json.JSONDecodeError:
            pass
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rec = parse_ualf_fields(re.split(r"[;\s]+", line))
        if rec:
            yield rec


def classify(rec, geo):
    p = transform(TO_3006, Point(rec["lon"], rec["lat"]))
    if not geo["municipality"].covers(p):
        return None
    dist = p.distance(geo["coast_boundary"])
    if dist <= COAST_UNCERTAINTY_M:
        return "coast_uncertain"
    if geo["mainland"].covers(p):
        return "mainland"
    if geo["islands"].covers(p):
        return "islands"
    if geo["sea"].covers(p):
        return "sea"
    if geo["inland_water"].covers(p):
        return "inland_water"
    return "other"


def load_existing_rows():
    rows = {}
    if not OUT_DIR.exists():
        return rows
    for path in OUT_DIR.glob("20??.csv"):
        with path.open("r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                key = (r["datetime_utc"], r["lat"], r["lon"])
                rows[key] = r
    return rows


def save_rows(rows):
    by_year = defaultdict(list)
    for r in rows.values():
        by_year[int(r["datetime_utc"][:4])].append(r)
    fields = ["datetime_utc", "year", "month", "day", "lat", "lon", "current_ka", "multiplicity", "chi_square", "cloud_indicator", "surface_class"]
    for year, yr in by_year.items():
        yr.sort(key=lambda r: r["datetime_utc"])
        with (OUT_DIR / f"{year}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(yr)


def build_summary(rows, geo):
    annual = defaultdict(lambda: defaultdict(int))
    monthly = defaultdict(lambda: defaultdict(int))
    monthly_by_year = defaultdict(lambda: defaultdict(int))
    days = defaultdict(set)
    days_by_month = defaultdict(set)
    current = defaultdict(list)
    for r in rows.values():
        cls = r["surface_class"]
        y, m = int(r["year"]), int(r["month"])
        annual[y][cls] += 1
        monthly[m][cls] += 1
        monthly_by_year[(y, m)][cls] += 1
        days[y].add(r["datetime_utc"][:10])
        days_by_month[(y, m)].add(r["datetime_utc"][:10])
        try:
            current[y].append(abs(float(r["current_ka"])))
        except (TypeError, ValueError):
            pass
    classes = ["mainland", "islands", "sea", "coast_uncertain", "inland_water"]
    annual_rows = []
    for y in sorted(annual):
        item = {"year": y, **{c: annual[y].get(c, 0) for c in classes}, "lightning_days": len(days[y])}
        item["classified_total"] = item["mainland"] + item["islands"] + item["sea"]
        item["uncertain_pct"] = round(100 * item["coast_uncertain"] / max(1, item["classified_total"] + item["coast_uncertain"]), 2)
        item["max_abs_current_ka"] = round(max(current[y]), 1) if current[y] else None
        annual_rows.append(item)
    monthly_rows = []
    for m in range(1, 13):
        monthly_rows.append({"month": m, **{c: monthly[m].get(c, 0) for c in classes}})
    monthly_year_rows = []
    for (y, m), vals in sorted(monthly_by_year.items()):
        monthly_year_rows.append({"year": y, "month": m, "lightning_days": len(days_by_month[(y, m)]), **{c: vals.get(c, 0) for c in classes}})
    summary = {
        "source": "SMHI Blixtdata - historiska arkivdata",
        "source_url": "https://www.smhi.se/data/sok-oppna-data-i-utforskaren/blixtdata-historiska-arkivdata",
        "start_date": "2012-01-02",
        "method_break": "2014",
        "coast_uncertainty_m": COAST_UNCERTAINTY_M,
        "mainland_component_min_km2": MAINLAND_MIN_AREA_KM2,
        "geography_source": "SCB DeSO 2025 landmask + Region Norrbotten ArcGIS kommungräns",
        "geography_note": "SCB-geometrin används som analysunderlag i denna första version; byt till Lantmäteriets exakta geometri när sådan finns tillgänglig.",
        "annual": annual_rows,
        "monthly": monthly_rows,
        "monthly_by_year": monthly_year_rows,
        "records": len(rows),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        geo = build_geography()
    except Exception as exc:
        print(f"Lightning geography unavailable: {exc}", file=sys.stderr)
        return 2

    existing = load_existing_rows()
    try:
        urls = []
        crawl_atom(ATOM_URL, set(), urls)
        urls = sorted(set(urls))
    except Exception as exc:
        print(f"Lightning Atom feed unavailable: {exc}", file=sys.stderr)
        if existing:
            build_summary(existing, geo)
        return 0

    mode = os.environ.get("RUN_MODE", "auto")
    if mode in {"auto", "update"} and existing:
        cutoff = datetime.now(timezone.utc).date().replace(day=1)
        recent = [u for u in urls if date_from_url(u) is None or date_from_url(u) >= cutoff]
        if recent:
            urls = recent

    minx, miny, maxx, maxy = geo["bounds"]
    n_new = 0
    for i, url in enumerate(urls, 1):
        try:
            for text in iter_payload_text(url):
                for rec in parse_payload(text):
                    if not (minx <= rec["lon"] <= maxx and miny <= rec["lat"] <= maxy):
                        continue
                    cls = classify(rec, geo)
                    if not cls:
                        continue
                    dt = rec["datetime"].astimezone(timezone.utc)
                    row = {
                        "datetime_utc": dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "year": dt.year,
                        "month": dt.month,
                        "day": dt.day,
                        "lat": f"{rec['lat']:.6f}",
                        "lon": f"{rec['lon']:.6f}",
                        "current_ka": "" if rec.get("current_ka") is None else rec.get("current_ka"),
                        "multiplicity": "" if rec.get("multiplicity") is None else rec.get("multiplicity"),
                        "chi_square": "" if rec.get("chi_square") is None else rec.get("chi_square"),
                        "cloud_indicator": "" if rec.get("cloud_indicator") is None else rec.get("cloud_indicator"),
                        "surface_class": cls,
                    }
                    key = (row["datetime_utc"], row["lat"], row["lon"])
                    if key not in existing:
                        n_new += 1
                    existing[key] = row
        except Exception as exc:
            print(f"Warning: lightning file failed {url}: {exc}", file=sys.stderr)
        if i % 100 == 0:
            print(f"Processed {i}/{len(urls)} archive files; local records {len(existing):,}")

    save_rows(existing)
    build_summary(existing, geo)
    print(f"Lightning: {len(existing):,} Lulea records, {n_new:,} new; summary written to {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
