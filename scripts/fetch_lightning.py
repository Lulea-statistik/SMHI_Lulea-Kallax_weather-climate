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
from datetime import datetime, timezone, timedelta
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
NMD_GEO_PATH = OUT_DIR / "geography_nmd.geojson"
GEOGRAPHY_VERSION = "nmd-water-v3"
UNCERTAINTY_VERSION = "surface-flags-v1"

ATOM_URL = "https://opendata-download-lightning.smhi.se/api/version/latest.atom"
SCB_WFS = "https://geodata.scb.se/geoserver/stat/wfs"
MUNICIPALITY_ARCGIS = "https://services-eu1.arcgis.com/Ek4rv9ndj9nQOpV3/arcgis/rest/services/Region_kommun/FeatureServer/1/query"
MUNICIPALITY_CODE = "2580"
COAST_UNCERTAINTY_M = 500.0
UNCERTAINTY_DISTANCES_M = (250, 500, 1000)
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


def load_analysis_geography():
    if not NMD_GEO_PATH.exists():
        raise RuntimeError(f"Static NMD geography is missing: {NMD_GEO_PATH}")
    data = json.loads(NMD_GEO_PATH.read_text(encoding="utf-8"))
    by_class = {}
    for feat in data.get("features", []):
        cls = (feat.get("properties") or {}).get("class")
        if cls and feat.get("geometry"):
            by_class[cls] = shape(feat["geometry"])
    required = ["municipality", "mainland", "islands", "sea", "inland_water", "shoreline", "neighbor_boundary"]
    missing = [x for x in required if x not in by_class]
    if missing:
        raise RuntimeError(f"NMD geography missing classes: {missing}")

    municipality_wgs = by_class["municipality"]
    return {
        "municipality": transform(TO_3006, municipality_wgs),
        "mainland": transform(TO_3006, by_class["mainland"]),
        "islands": transform(TO_3006, by_class["islands"]),
        "sea": transform(TO_3006, by_class["sea"]),
        "inland_water": transform(TO_3006, by_class["inland_water"]),
        "coast_boundary": transform(TO_3006, by_class["shoreline"]),
        "neighbor_boundary": transform(TO_3006, by_class["neighbor_boundary"]),
        "bounds": municipality_wgs.bounds,
        "source": "NMD, Naturvardsverket public WMS",
    }


def summary_geography_version():
    if not SUMMARY_PATH.exists():
        return None
    try:
        return json.loads(SUMMARY_PATH.read_text(encoding="utf-8")).get("geography_version")
    except Exception:
        return None


def reclassify_existing_rows(rows, geo):
    changed = 0
    removed = 0
    uncertainty_updated = 0
    for key in list(rows):
        r = rows[key]
        try:
            rec = {"lat": float(r["lat"]), "lon": float(r["lon"])}
        except Exception:
            continue
        # Historical rows classified as coast_uncertain need their underlying
        # surface restored. Other rows keep their good existing surface class unless
        # they are missing/obsolete.
        old_cls = r.get("surface_class")
        if old_cls in {"coast_uncertain", "", None, "other"}:
            cls = classify_surface(rec, geo)
        else:
            cls = old_cls
        if cls is None:
            rows.pop(key, None)
            removed += 1
            continue
        if old_cls != cls:
            r["surface_class"] = cls
            changed += 1

        flags = uncertainty_flags(rec, geo, cls)
        for name, value in flags.items():
            r[name] = value
        uncertainty_updated += 1
    print(
        f"Lightning smart uncertainty update: {uncertainty_updated:,} stored observations; "
        f"{changed:,} surface classes restored/changed, {removed:,} outside geometry. "
        "No historical lightning archive download was needed."
    )
    return rows


def crawl_atom(url: str, seen: set[str], out: list[str], depth: int = 0):
    if depth > 8 or url in seen:
        return
    seen.add(url)
    try:
        r = get(url)
    except Exception as exc:
        if depth == 0:
            raise
        print(f"Warning: skipping Atom subfeed {url}: {exc}", file=sys.stderr)
        return
    root = ET.fromstring(r.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for link in root.findall(".//a:link", ns):
        href = link.attrib.get("href")
        if not href:
            continue
        href = urljoin(url, href)
        low = href.lower()
        rel = (link.attrib.get("rel") or "").lower()
        typ = (link.attrib.get("type") or "").lower()

        # Atom links are navigation/catalogue feeds and must be followed first.
        # In the previous version rel="enclosure" caused year-level Atom metadata
        # to be mistaken for downloadable lightning data.
        if low.endswith(".atom") or "atom" in typ:
            crawl_atom(href, seen, out, depth + 1)
            continue

        # JSON/XML at year/month/day catalogue levels are metadata. Actual lightning
        # resources appear at the leaf level and are normally exposed as data/text,
        # CSV/UALF, compressed files, or links whose rel explicitly says data.
        is_catalogue = bool(re.search(r"/year/\d{4}(?:/month/\d{1,2})?(?:/day/\d{1,2})?\.(?:json|xml)$", low))
        # One representation is enough. Prefer CSV so a full refresh does not
        # download the same day again as JSON and XML.
        is_csv_data = low.endswith("/data.csv") or low.endswith(".csv")
        if is_csv_data:
            out.append(href)


def recent_daily_urls(days: int = 14) -> list[str]:
    """Direct daily CSV resources for incremental updates.

    Historical lightning files are already stored in the repository after bootstrap.
    Normal auto/update runs therefore only revisit a short recent window to catch
    late or corrected observations and never traverse the full 2012-present archive.
    """
    today = datetime.now(timezone.utc).date()
    urls = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        urls.append(
            "https://opendata-download-lightning.smhi.se/api/version/latest/"
            f"year/{day.year}/month/{day.month}/day/{day.day}/data.csv"
        )
    return urls


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


def classify_surface(rec, geo):
    p = transform(TO_3006, Point(rec["lon"], rec["lat"]))
    if not geo["municipality"].covers(p):
        return None
    if geo["mainland"].covers(p):
        cls = "mainland"
    elif geo["islands"].covers(p):
        cls = "islands"
    elif geo["sea"].covers(p):
        cls = "sea"
    elif geo["inland_water"].covers(p):
        cls = "inland_water"
    else:
        cls = "other"
    return cls


def uncertainty_flags(rec, geo, surface_class=None):
    p = transform(TO_3006, Point(rec["lon"], rec["lat"]))
    if surface_class is None:
        surface_class = classify_surface(rec, geo)
    coast_dist = p.distance(geo["coast_boundary"]) if surface_class in {"mainland", "islands", "sea"} else float("inf")
    municipality_dist = p.distance(geo["neighbor_boundary"])
    out = {}
    for d in UNCERTAINTY_DISTANCES_M:
        out[f"coast_uncertain_{d}"] = int(coast_dist <= d)
        out[f"municipality_boundary_uncertain_{d}"] = int(municipality_dist <= d)
    return out


def classify(rec, geo):
    return classify_surface(rec, geo)


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
    fields = ["datetime_utc", "year", "month", "day", "lat", "lon", "current_ka", "multiplicity", "chi_square", "cloud_indicator", "surface_class",
              "coast_uncertain_250", "coast_uncertain_500", "coast_uncertain_1000",
              "municipality_boundary_uncertain_250", "municipality_boundary_uncertain_500", "municipality_boundary_uncertain_1000"]
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

    flag_names = []
    for d in UNCERTAINTY_DISTANCES_M:
        flag_names.extend([f"coast_uncertain_{d}", f"municipality_boundary_uncertain_{d}"])

    for r in rows.values():
        cls = r["surface_class"]
        y, m = int(r["year"]), int(r["month"])
        annual[y][cls] += 1
        monthly[m][cls] += 1
        monthly_by_year[(y, m)][cls] += 1
        for flag in flag_names:
            try:
                hit = int(r.get(flag, 0) or 0)
            except (TypeError, ValueError):
                hit = 0
            if hit:
                annual[y][flag] += 1
                monthly[m][flag] += 1
                monthly_by_year[(y, m)][flag] += 1
        days[y].add(r["datetime_utc"][:10])
        days_by_month[(y, m)].add(r["datetime_utc"][:10])
        try:
            current[y].append(abs(float(r["current_ka"])))
        except (TypeError, ValueError):
            pass

    classes = ["mainland", "islands", "sea", "inland_water", "other"]

    def add_uncertainty_fields(item, vals, total):
        for d in UNCERTAINTY_DISTANCES_M:
            coast = vals.get(f"coast_uncertain_{d}", 0)
            muni = vals.get(f"municipality_boundary_uncertain_{d}", 0)
            item[f"coast_uncertain_{d}"] = coast
            item[f"coast_uncertain_pct_{d}"] = round(100 * coast / max(1, total), 2)
            item[f"municipality_boundary_uncertain_{d}"] = muni
            item[f"municipality_boundary_uncertain_pct_{d}"] = round(100 * muni / max(1, total), 2)
        # Backward-compatible 500 m names for the existing dashboard.
        item["coast_uncertain"] = item["coast_uncertain_500"]
        item["uncertain_pct"] = item["coast_uncertain_pct_500"]
        item["municipality_boundary_uncertain"] = item["municipality_boundary_uncertain_500"]
        item["municipality_boundary_uncertain_pct"] = item["municipality_boundary_uncertain_pct_500"]

    annual_rows = []
    for y in sorted(annual):
        item = {"year": y, **{cl: annual[y].get(cl, 0) for cl in classes}, "lightning_days": len(days[y])}
        total = sum(item[cl] for cl in classes)
        item["classified_total"] = item["mainland"] + item["islands"] + item["sea"] + item["inland_water"]
        item["records_total"] = total
        add_uncertainty_fields(item, annual[y], total)
        item["max_abs_current_ka"] = round(max(current[y]), 1) if current[y] else None
        annual_rows.append(item)

    monthly_rows = []
    for m in range(1, 13):
        item = {"month": m, **{cl: monthly[m].get(cl, 0) for cl in classes}}
        total = sum(item[cl] for cl in classes)
        add_uncertainty_fields(item, monthly[m], total)
        monthly_rows.append(item)

    monthly_year_rows = []
    for (y, m), vals in sorted(monthly_by_year.items()):
        item = {
            "year": y,
            "month": m,
            "lightning_days": len(days_by_month[(y, m)]),
            **{cl: vals.get(cl, 0) for cl in classes},
        }
        total = sum(item[cl] for cl in classes)
        add_uncertainty_fields(item, vals, total)
        monthly_year_rows.append(item)

    summary = {
        "source": "SMHI Blixtdata - historiska arkivdata",
        "source_url": "https://www.smhi.se/data/sok-oppna-data-i-utforskaren/blixtdata-historiska-arkivdata",
        "start_date": "2012-01-02",
        "method_break": "2014",
        "coast_uncertainty_m": COAST_UNCERTAINTY_M,
        "uncertainty_distances_m": list(UNCERTAINTY_DISTANCES_M),
        "mainland_component_min_km2": MAINLAND_MIN_AREA_KM2,
        "geography_source": "Nationella Marktackedata (NMD), Naturvardsverket public WMS + Region Norrbotten kommungrans",
        "geography_note": "NMD klass 61 används för inlandsvatten och klass 62 för hav. Mindre marina landkomponenter redovisas som oar. Geografin lagras statiskt och ateranvands vid dagliga korningar.",
        "geography_version": GEOGRAPHY_VERSION,
        "uncertainty_version": UNCERTAINTY_VERSION,
        "uncertainty_note": "Kustosakerhet avser endast marin strandlinje (fastland/hav eller o/hav). Kommungransosakerhet avser endast grans mot andra kommuner, inte kommunens havsgrans. 250/500/1000 m redovisas separat. Grundklassen behalls aven nar en observation ar osaker.",
        "annual": annual_rows,
        "monthly": monthly_rows,
        "monthly_by_year": monthly_year_rows,
        "records": len(rows),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        geo = load_analysis_geography()
    except Exception as exc:
        print(f"Lightning geography unavailable: {exc}", file=sys.stderr)
        return 2

    existing = load_existing_rows()
    current_summary = {}
    if SUMMARY_PATH.exists():
        try:
            current_summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        except Exception:
            current_summary = {}
    if existing and (
        current_summary.get("geography_version") != GEOGRAPHY_VERSION
        or current_summary.get("uncertainty_version") != UNCERTAINTY_VERSION
    ):
        existing = reclassify_existing_rows(existing, geo)
        save_rows(existing)
    mode = os.environ.get("RUN_MODE", "auto")

    # Once the historical baseline exists, ordinary runs must not traverse or
    # redownload the historical archive. Revisit only the last 14 days directly.
    full_history = mode in {"bootstrap", "refresh-all"} or not existing
    if not full_history:
        urls = recent_daily_urls(14)
        print(f"Lightning incremental mode: {len(urls)} recent daily CSV resources; historical archive is not queried.")
    else:
        try:
            urls = []
            crawl_atom(ATOM_URL, set(), urls)
            urls = sorted(set(urls))
            print(f"Lightning full-history CSV links discovered: {len(urls):,}")
            for sample_url in urls[:10]:
                print(f"  archive link: {sample_url}")
            if not urls:
                raise RuntimeError("SMHI Atom feed contained no downloadable CSV archive links")
        except Exception as exc:
            print(f"Lightning Atom feed unavailable: {exc}", file=sys.stderr)
            if existing:
                build_summary(existing, geo)
                return 0
            return 2

    minx, miny, maxx, maxy = geo["bounds"]
    n_new = 0
    parsed_total = 0
    diagnostic_samples = 0
    for i, url in enumerate(urls, 1):
        try:
            for text in iter_payload_text(url):
                parsed_here = 0
                for rec in parse_payload(text):
                    parsed_here += 1
                    parsed_total += 1
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
                    row.update(uncertainty_flags(rec, geo, cls))
                    key = (row["datetime_utc"], row["lat"], row["lon"])
                    if key not in existing:
                        n_new += 1
                    existing[key] = row
                if parsed_here == 0 and diagnostic_samples < 5:
                    one_line = re.sub(r"\s+", " ", text[:1200]).strip()
                    print(f"Diagnostic no UALF records from {url}: {one_line}", file=sys.stderr)
                    diagnostic_samples += 1
        except Exception as exc:
            if full_history:
                print(f"Warning: lightning file failed {url}: {exc}", file=sys.stderr)
            else:
                print(f"Lightning recent resource unavailable/empty: {url}: {exc}", file=sys.stderr)
        if i % 100 == 0:
            print(f"Processed {i}/{len(urls)} archive files; local records {len(existing):,}")

    print(f"Lightning parsed source records before geographic filtering: {parsed_total:,}")
    save_rows(existing)
    build_summary(existing, geo)
    print(f"Lightning: {len(existing):,} Lulea records, {n_new:,} new; summary written to {SUMMARY_PATH}")
    if full_history and parsed_total == 0:
        print("ERROR: no lightning observations could be parsed from discovered SMHI archive resources.", file=sys.stderr)
        return 3
    if full_history and len(existing) == 0:
        print("ERROR: lightning observations were parsed but none fell inside the Lulea municipality geometry.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
