#!/usr/bin/env python3
"""Build a static Lulea land/island/sea mask from Naturvardsverket NMD.

The mask is created once and then committed to the repository. Normal lightning
updates reuse the static mask and do not redownload land-cover history.

Classes:
- mainland: land components >= 100 km2 plus small non-marine land components
- islands: smaller land components adjacent to NMD class 62 (sea)
- sea: NMD class 62
- inland_water: NMD class 61
- coast_uncertain is not stored as a polygon; it is computed as <=500 m from
  the shoreline when lightning points are classified.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.io import MemoryFile
from shapely.geometry import Polygon, shape, mapping
from shapely.ops import transform, unary_union
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "lightning"
OUT_PATH = OUT_DIR / "geography_nmd.geojson"

MUNICIPALITY_ARCGIS = "https://services-eu1.arcgis.com/Ek4rv9ndj9nQOpV3/arcgis/rest/services/Region_kommun/FeatureServer/1/query"
NMD_WMS = "https://geodata.naturvardsverket.se/inspire/lc-nmd/ows"
NMD_LAYER = None
PIXEL_SIZE_M = 20.0
TILE_SIZE = 1536
MAINLAND_MIN_AREA_KM2 = 100.0
TIMEOUT = 120

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Lulea-statistik-NMD-lightning-geometry/1.0"})

TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def fetch_municipality_wgs84():
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    r = SESSION.get(MUNICIPALITY_ARCGIS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    geoms = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        vals = [str(v).lower() for v in props.values() if v is not None]
        if any(v == "2580" or "luleå" in v or "lulea" in v for v in vals):
            geoms.append(shape(feat["geometry"]))
    if not geoms:
        raise RuntimeError("Could not find Lulea municipality geometry")
    return unary_union(geoms)


def discover_nmd_layer():
    """Read GetCapabilities and choose the current NMD base land-cover raster layer."""
    params = {"service": "WMS", "request": "GetCapabilities"}
    r = SESSION.get(NMD_WMS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    names = []
    for elem in root.iter():
        if elem.tag.endswith("Name") and elem.text:
            names.append(elem.text.strip())
    candidates = [
        n for n in names
        if "landcoverraster" in n.lower()
        and "produktiv" not in n.lower()
        and "fjallskog" not in n.lower()
    ]
    # Prefer explicit base/bas layer. The public WMS currently exposes the stable
    # NMD2018 base layer; land/water boundaries are sufficient for this analysis.
    candidates.sort(key=lambda n: (0 if "bas" in n.lower() else 1, 0 if "2018" in n.lower() else 1, len(n)))
    if not candidates:
        raise RuntimeError(f"Could not discover NMD base layer from WMS capabilities; sample names={names[:80]}")
    chosen = candidates[0]
    print(f"NMD WMS layer discovered: {chosen}")
    return chosen


def fetch_tile(bounds, width, height, layer_name):
    minx, miny, maxx, maxy = bounds
    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetMap",
        "layers": layer_name,
        "styles": "",
        "srs": "EPSG:3006",
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "width": str(width),
        "height": str(height),
        "format": "image/geotiff",
        "transparent": "false",
    }
    r = SESSION.get(NMD_WMS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    if "image" not in (r.headers.get("Content-Type") or "").lower() and "tiff" not in (r.headers.get("Content-Type") or "").lower():
        raise RuntimeError(f"NMD WMS did not return GeoTIFF: {r.text[:400]}")
    return r.content


def polygons_from_tile(raw):
    out = {1: [], 61: [], 62: []}
    with MemoryFile(raw) as mem:
        with mem.open() as ds:
            band = ds.read(1)
            transform_affine = ds.transform
            nodata = ds.nodata
            vals = np.unique(band)

            # Naturvardsverket's WMS returns a paletted GeoTIFF. Pixel values are
            # palette indexes (typically 1..25), not the original NMD GRID_CODE.
            # Resolve inland/marine water from the documented NMD colours:
            # 61 inland water = RGB 102,153,205
            # 62 marine water = RGB 138,204,250
            inland_indexes = set()
            marine_indexes = set()
            try:
                cmap = ds.colormap(1)
            except Exception:
                cmap = {}

            for idx, rgba in (cmap or {}).items():
                rgb = tuple(rgba[:3])
                if rgb == (102, 153, 205):
                    inland_indexes.add(int(idx))
                elif rgb == (138, 204, 250):
                    marine_indexes.add(int(idx))

            # Some WMS variants may preserve the original class codes directly.
            if 61 in vals:
                inland_indexes.add(61)
            if 62 in vals:
                marine_indexes.add(62)

            if not inland_indexes or not marine_indexes:
                sample_cmap = list((cmap or {}).items())[:40]
                raise RuntimeError(
                    "Could not identify NMD inland/marine water in GeoTIFF palette; "
                    f"unique sample={vals[:40].tolist()}, colormap sample={sample_cmap}"
                )

            cls = np.ones(band.shape, dtype=np.uint8)
            for idx in inland_indexes:
                cls[band == idx] = 61
            for idx in marine_indexes:
                cls[band == idx] = 62

            mask = np.ones(band.shape, dtype=bool)
            if nodata is not None:
                mask &= band != nodata
            mask &= band != 0

            for geom, value in shapes(cls, mask=mask, transform=transform_affine):
                iv = int(value)
                if iv in out:
                    out[iv].append(shape(geom))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists() and os.environ.get("REBUILD_LIGHTNING_GEOGRAPHY") != "1":
        print(f"Using existing static NMD geography: {OUT_PATH}")
        return 0

    municipality_wgs = fetch_municipality_wgs84()
    municipality = transform(TO_3006, municipality_wgs)
    nmd_layer = discover_nmd_layer()
    minx, miny, maxx, maxy = municipality.bounds

    tile_span = TILE_SIZE * PIXEL_SIZE_M
    nx = math.ceil((maxx - minx) / tile_span)
    ny = math.ceil((maxy - miny) / tile_span)
    print(f"NMD geometry: {nx} x {ny} tiles at {PIXEL_SIZE_M:.0f} m resolution")

    acc = {1: [], 61: [], 62: []}
    n = 0
    for iy in range(ny):
        for ix in range(nx):
            x0 = minx + ix * tile_span
            y0 = miny + iy * tile_span
            x1 = min(x0 + tile_span, maxx)
            y1 = min(y0 + tile_span, maxy)
            width = max(1, round((x1 - x0) / PIXEL_SIZE_M))
            height = max(1, round((y1 - y0) / PIXEL_SIZE_M))
            raw = fetch_tile((x0, y0, x1, y1), width, height, nmd_layer)
            parts = polygons_from_tile(raw)
            for k in acc:
                acc[k].extend(parts[k])
            n += 1
            print(f"Processed NMD tile {n}/{nx*ny}")

    land = unary_union(acc[1]).intersection(municipality).buffer(0)
    inland_water = unary_union(acc[61]).intersection(municipality).buffer(0)
    sea = unary_union(acc[62]).intersection(municipality).buffer(0)

    land_parts = list(land.geoms) if land.geom_type == "MultiPolygon" else [land]
    main_parts, island_parts = [], []
    sea_near = sea.buffer(PIXEL_SIZE_M * 1.5)
    for g in land_parts:
        if g.is_empty:
            continue
        area_km2 = g.area / 1_000_000
        # A marine island is a smaller disconnected land component adjacent to sea.
        if area_km2 < MAINLAND_MIN_AREA_KM2 and g.boundary.intersects(sea_near):
            island_parts.append(g)
        else:
            main_parts.append(g)

    mainland = unary_union(main_parts).buffer(0)
    islands = unary_union(island_parts).buffer(0)

    water = unary_union([sea, inland_water]).buffer(0)
    shoreline = land.boundary.intersection(water.boundary.buffer(PIXEL_SIZE_M * 2))

    features = []
    for name, geom in [
        ("municipality", municipality),
        ("mainland", mainland),
        ("islands", islands),
        ("sea", sea),
        ("inland_water", inland_water),
        ("shoreline", shoreline),
    ]:
        if geom.is_empty:
            continue
        simple = geom.simplify(20, preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {
                "class": name,
                "source": "NMD",
                "pixel_size_m": PIXEL_SIZE_M,
            },
            "geometry": mapping(transform(TO_4326, simple)),
        })

    out = {
        "type": "FeatureCollection",
        "name": "Lulea lightning analysis geography",
        "properties": {
            "source": "Nationella Marktackedata, Naturvardsverket public WMS",
            "license": "CC0",
            "water_classes": {"61": "inland_water", "62": "sea"},
            "pixel_size_m": PIXEL_SIZE_M,
            "mainland_component_min_km2": MAINLAND_MIN_AREA_KM2,
        },
        "features": features,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(
        "NMD geography written:",
        OUT_PATH,
        f"mainland={mainland.area/1e6:.1f} km2",
        f"islands={islands.area/1e6:.1f} km2",
        f"sea={sea.area/1e6:.1f} km2",
        f"inland_water={inland_water.area/1e6:.1f} km2",
    )
    if islands.is_empty or sea.is_empty:
        raise RuntimeError("NMD geography validation failed: islands or sea is empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
