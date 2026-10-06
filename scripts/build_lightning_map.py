#!/usr/bin/env python3
"""Build lazy-loadable annual lightning map data and a 1 km density grid for GitHub Pages."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "lightning"
OUT = ROOT / "docs" / "lightning_map"
BOUNDARY_SRC = SRC / "geography.geojson"
BOUNDARY_OUT = OUT / "boundary.geojson"

TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True)
TO_4326 = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True)
CELL = 1000.0

SURFACES = {"mainland", "islands", "sea", "inland_water", "uncertain"}


def as_float(v):
    try:
        return float(v)
    except Exception:
        return None


def cell_polygon(x0, y0):
    coords = []
    for x, y in [(x0,y0),(x0+CELL,y0),(x0+CELL,y0+CELL),(x0,y0+CELL),(x0,y0)]:
        lon, lat = TO_4326.transform(x, y)
        coords.append([round(lon, 6), round(lat, 6)])
    return coords


def normalize_surface(row):
    if str(row.get("uncertain_area_500") or "").strip() in {"1", "true", "True"}:
        return "uncertain"
    s = str(row.get("surface_class") or "").strip()
    return s if s in SURFACES else "uncertain"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Reuse the already verified Lulea geography used by the lightning statistics.
    if BOUNDARY_SRC.exists():
        geo = json.loads(BOUNDARY_SRC.read_text(encoding="utf-8"))
        municipality = [f for f in geo.get("features", []) if (f.get("properties") or {}).get("class") == "municipality"]
        if municipality:
            BOUNDARY_OUT.write_text(
                json.dumps({"type":"FeatureCollection","features":municipality}, ensure_ascii=False, separators=(",",":")),
                encoding="utf-8",
            )

    index = {"cell_size_m": 1000, "years": []}

    for path in sorted(SRC.glob("20??.csv")):
        try:
            year = int(path.stem)
        except ValueError:
            continue

        points = []
        cells = defaultdict(lambda: {"count":0, "by_surface":defaultdict(int)})
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                lat = as_float(row.get("lat"))
                lon = as_float(row.get("lon"))
                if lat is None or lon is None:
                    continue
                surface = normalize_surface(row)
                current = as_float(row.get("current_ka"))
                dt = str(row.get("datetime_utc") or "")
                points.append({
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "surface": surface,
                    "current_ka": round(current, 1) if current is not None else None,
                    "datetime_utc": dt,
                })
                x, y = TO_3006.transform(lon, lat)
                x0 = math.floor(x / CELL) * CELL
                y0 = math.floor(y / CELL) * CELL
                c = cells[(x0, y0)]
                c["count"] += 1
                c["by_surface"][surface] += 1

        grid = []
        for (x0, y0), c in cells.items():
            lonc, latc = TO_4326.transform(x0 + CELL/2, y0 + CELL/2)
            grid.append({
                "count": c["count"],
                "by_surface": dict(c["by_surface"]),
                "lat": round(latc, 6),
                "lon": round(lonc, 6),
                "polygon": cell_polygon(x0, y0),
            })

        grid.sort(key=lambda x: (-x["count"], x["lat"], x["lon"]))
        payload = {
            "year": year,
            "cell_size_m": 1000,
            "points": points,
            "grid": grid,
        }
        out_name = f"{year}.json"
        (OUT / out_name).write_text(json.dumps(payload, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
        index["years"].append({
            "year": year,
            "file": out_name,
            "lightning_count": len(points),
            "grid_cells": len(grid),
            "max_cell_count": max((c["count"] for c in grid), default=0),
        })
        print(f"Lightning map {year}: {len(points)} flashes, {len(grid)} occupied 1 km cells")

    index["years"].sort(key=lambda x: x["year"])
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Lightning map index: {len(index['years'])} years")


if __name__ == "__main__":
    main()
