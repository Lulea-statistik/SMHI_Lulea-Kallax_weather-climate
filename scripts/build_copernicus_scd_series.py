#!/usr/bin/env python3
"""Build Copernicus HR-WSI SP_S2 Snow Cover Duration series for Lulea.

For each hydrological year 2016/17–2025/26, download SCD 20 m rasters for
MGRS tiles 34WET and 34WEU, aggregate valid pixels to the existing 2.5 km
Lulea grid, and write compact class shares for the report.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

import boto3
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds, Window
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / "docs" / "snowgrid" / "2017-18_grid.geojson"
OUT = ROOT / "docs" / "snowgrid" / "copernicus_scd_series.json"

ENDPOINT = os.environ["HRWSI_ENDPOINT"]
ACCESS_KEY = os.environ["HRWSI_ACCESS_KEY"]
SECRET_KEY = os.environ["HRWSI_SECRET_KEY"]
BUCKET = os.environ.get("HRWSI_BUCKET", "HRWSI")

PRODUCT = "SP_S2"
YEARS = range(2016, 2026)
TILES = ["34WET", "34WEU"]

# Continuous week classes. Extra high-duration bins preserve useful
# variation in northern Sweden where most land is snow-covered >24 weeks.
CLASSES = [
    ("0–4 veckor", 0.0, 5.0),
    ("5–8 veckor", 5.0, 9.0),
    ("9–12 veckor", 9.0, 13.0),
    ("13–16 veckor", 13.0, 17.0),
    ("17–20 veckor", 17.0, 21.0),
    ("21–24 veckor", 21.0, 25.0),
    ("25–28 veckor", 25.0, 29.0),
    ("29–32 veckor", 29.0, 33.0),
    ("33+ veckor", 33.0, 100.0),
]


def load_grid():
    data = json.loads(GRID.read_text(encoding="utf-8"))
    feats = []
    for f in data.get("features", []):
        cid = int((f.get("properties") or {}).get("cell_id", f.get("id", 0)))
        geom = shape(f["geometry"]).buffer(0)
        if not geom.is_empty:
            feats.append((cid, geom))
    if not feats:
        raise RuntimeError("No Lulea 2.5 km grid geometry found")
    return feats


def find_scd_key(bucket, tile, year):
    prefix = f"{PRODUCT}/{tile}/{year}/"
    keys = [o.key for o in bucket.objects.filter(Prefix=prefix) if o.key.endswith("_SCD.tif")]
    return sorted(keys)[0] if keys else None


def classify_weeks(weeks):
    if weeks is None:
        return None
    for label, lo, hi in CLASSES:
        if lo <= weeks < hi:
            return label
    return None


def aggregate_year(bucket, grid, year, tmpdir):
    n = max(cid for cid, _ in grid) + 1
    sums = np.zeros(n, dtype="float64")
    counts = np.zeros(n, dtype="int64")
    tile_meta = []

    for tile in TILES:
        key = find_scd_key(bucket, tile, year)
        if not key:
            tile_meta.append({"tile": tile, "missing": True})
            continue

        local = Path(tmpdir) / f"{tile}_{year}_SCD.tif"
        bucket.download_file(key, str(local))

        with rasterio.open(local) as ds:
            if ds.crs is None:
                raise RuntimeError(f"{tile} {year}: raster CRS missing")

            to_raster = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform
            grid_r = [(cid, transform(to_raster, geom)) for cid, geom in grid]
            union = unary_union([g for _, g in grid_r])

            win = from_bounds(*union.bounds, transform=ds.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, ds.width, ds.height))
            arr = ds.read(1, window=win, masked=True)
            tr = ds.window_transform(win)

            labels = rasterize(
                [(mapping(g), cid + 1) for cid, g in grid_r],
                out_shape=arr.shape,
                transform=tr,
                fill=0,
                dtype="int32",
                all_touched=False,
            )

            raw = np.asarray(arr.astype("int32").filled(-9999))
            base = (labels > 0) & (~np.asarray(arr.mask)) & np.isfinite(raw)

            # Copernicus SCD physical range is 0–366 days. Values outside
            # this range (e.g. 420) are product flags and are excluded.
            valid = base & (raw >= 0) & (raw <= 366)
            ids = labels[valid] - 1
            vals = raw[valid].astype("float64")

            if vals.size:
                sums += np.bincount(ids, weights=vals, minlength=n)
                counts += np.bincount(ids, minlength=n)

            tile_meta.append({
                "tile": tile,
                "key": key,
                "crs": str(ds.crs),
                "valid_pixels": int(valid.sum()),
            })

    cells = []
    class_counts = defaultdict(int)
    for cid in range(n):
        mean_days = float(sums[cid] / counts[cid]) if counts[cid] else None
        weeks = mean_days / 7.0 if mean_days is not None else None
        cls = classify_weeks(weeks)
        if cls:
            class_counts[cls] += 1
        cells.append({
            "cell_id": cid,
            "mean_snow_cover_days": round(mean_days, 1) if mean_days is not None else None,
            "weeks": round(weeks, 1) if weeks is not None else None,
            "class": cls,
            "valid_pixels": int(counts[cid]),
        })

    classified = sum(class_counts.values())
    class_pct = {
        label: round(100 * class_counts.get(label, 0) / classified, 2) if classified else 0.0
        for label, _, _ in CLASSES
    }

    return {
        "season": f"{year}-{str(year + 1)[-2:]}",
        "hydrological_year": f"{year}-09-01–{year+1}-08-31",
        "classified_cells": classified,
        "class_counts": dict(class_counts),
        "class_pct": class_pct,
        "tiles": tile_meta,
        "cells": cells,
    }


def main():
    grid = load_grid()
    s3 = boto3.resource(
        "s3",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT,
    )
    bucket = s3.Bucket(BUCKET)

    seasons = []
    with tempfile.TemporaryDirectory() as td:
        for year in YEARS:
            print(f"Copernicus SCD {year}/{year+1}")
            seasons.append(aggregate_year(bucket, grid, year, td))

    payload = {
        "source": "Copernicus HR-WSI SP_S2 Snow Phenology – Snow Cover Duration",
        "product": "SP_S2 SCD",
        "source_resolution_m": 20,
        "aggregation_grid_km": 2.5,
        "period_definition": "hydrological year September–August",
        "note": "Only 2.5 km cells with valid Copernicus SCD pixels are included in class shares. Product flag values outside 0–366 days are excluded.",
        "classes": [x[0] for x in CLASSES],
        "seasons": seasons,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(json.dumps({
        "classes": payload["classes"],
        "seasons": [
            {"season": s["season"], "classified_cells": s["classified_cells"], "class_pct": s["class_pct"]}
            for s in seasons
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
