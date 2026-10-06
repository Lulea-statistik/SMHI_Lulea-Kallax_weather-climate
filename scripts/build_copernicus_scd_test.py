#!/usr/bin/env python3
"""Aggregate Copernicus HR-WSI SP_S2 Snow Cover Duration to Lulea 2.5 km cells."""

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
OUT = ROOT / "docs" / "snowgrid" / "copernicus_scd_2023_test.json"

ENDPOINT = os.environ["HRWSI_ENDPOINT"]
ACCESS_KEY = os.environ["HRWSI_ACCESS_KEY"]
SECRET_KEY = os.environ["HRWSI_SECRET_KEY"]
BUCKET = os.environ.get("HRWSI_BUCKET", "HRWSI")

PRODUCT = "SP_S2"
YEAR = 2023
TILES = ["34WET", "34WEU"]

CLASSES = [
    ("0–4 veckor", 0, 28),
    ("5–8 veckor", 29, 56),
    ("9–12 veckor", 57, 84),
    ("13–16 veckor", 85, 112),
    ("17–20 veckor", 113, 140),
    ("21–24 veckor", 141, 168),
    ("25+ veckor", 169, 366),
]


def find_scd_key(bucket, tile):
    prefix = f"{PRODUCT}/{tile}/{YEAR}/"
    keys = [o.key for o in bucket.objects.filter(Prefix=prefix) if o.key.endswith("_SCD.tif")]
    if not keys:
        raise RuntimeError(f"No SCD raster found for {tile} {YEAR}")
    return sorted(keys)[0]


def load_grid():
    data = json.loads(GRID.read_text(encoding="utf-8"))
    feats = []
    for f in data.get("features", []):
        cid = int((f.get("properties") or {}).get("cell_id", f.get("id", 0)))
        geom = shape(f["geometry"]).buffer(0)
        if not geom.is_empty:
            feats.append((cid, geom))
    if not feats:
        raise RuntimeError("No Lulea 2.5 km grid found")
    return feats


def classify(days):
    if days is None:
        return None
    for label, lo, hi in CLASSES:
        if lo <= days <= hi:
            return label
    return None


def main():
    grid = load_grid()
    n = max(cid for cid, _ in grid) + 1
    sums = np.zeros(n, dtype="float64")
    counts = np.zeros(n, dtype="int64")
    tile_reports = []

    s3 = boto3.resource(
        "s3",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT,
    )
    bucket = s3.Bucket(BUCKET)

    with tempfile.TemporaryDirectory() as td:
        for tile in TILES:
            key = find_scd_key(bucket, tile)
            local = Path(td) / f"{tile}_SCD.tif"
            bucket.download_file(key, str(local))

            with rasterio.open(local) as ds:
                if ds.crs is None:
                    raise RuntimeError(f"{tile}: missing CRS")

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

                raw = np.asarray(arr.filled(-9999))
                base = (labels > 0) & (~np.asarray(arr.mask)) & np.isfinite(raw)
                valid = base & (raw >= 0) & (raw <= 366)
                ids = labels[valid] - 1
                vals = raw[valid].astype("float64")

                if vals.size:
                    sums += np.bincount(ids, weights=vals, minlength=n)
                    counts += np.bincount(ids, minlength=n)

                excluded = raw[base & ~((raw >= 0) & (raw <= 366))]
                tile_reports.append({
                    "tile": tile,
                    "key": key,
                    "crs": str(ds.crs),
                    "shape": [ds.height, ds.width],
                    "dtype": str(ds.dtypes[0]),
                    "nodata": ds.nodata,
                    "tags": ds.tags(),
                    "band_tags": ds.tags(1),
                    "valid_pixels": int(valid.sum()),
                    "valid_min": float(vals.min()) if vals.size else None,
                    "valid_mean": round(float(vals.mean()), 2) if vals.size else None,
                    "valid_max": float(vals.max()) if vals.size else None,
                    "excluded_values_sample": sorted({int(v) for v in excluded[:500000]})[:30],
                })

    cells = []
    class_counts = defaultdict(int)
    for cid in range(n):
        mean_days = round(float(sums[cid] / counts[cid]), 1) if counts[cid] else None
        cls = classify(mean_days)
        if cls:
            class_counts[cls] += 1
        cells.append({
            "cell_id": cid,
            "mean_snow_cover_days": mean_days,
            "weeks": round(mean_days / 7, 1) if mean_days is not None else None,
            "class": cls,
            "pixels": int(counts[cid]),
        })

    classified = sum(class_counts.values())
    class_pct = {
        label: round(100 * class_counts.get(label, 0) / classified, 1) if classified else 0
        for label, _, _ in CLASSES
    }

    report = {
        "product": "Copernicus HR-WSI SP_S2 Snow Cover Duration",
        "hydrological_year": "2023-09-01–2024-08-31",
        "source_resolution_m": 20,
        "target_grid_km": 2.5,
        "aggregation": "mean valid SCD days per existing Lulea grid cell",
        "tiles": tile_reports,
        "classified_cells": classified,
        "class_counts": dict(class_counts),
        "class_pct": class_pct,
        "cells": cells,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "classified_cells": classified,
        "class_pct": class_pct,
        "tiles": [
            {k: t[k] for k in ["tile", "crs", "valid_pixels", "valid_min", "valid_mean", "valid_max", "excluded_values_sample"]}
            for t in tile_reports
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
