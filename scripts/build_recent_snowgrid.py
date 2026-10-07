#!/usr/bin/env python3
"""Build a recent 2.5 km snow-depth grid from SMHI station observations.

This is intentionally a separate method from SMHIGridClim. It uses inverse-
distance weighting (IDW) of daily snow-depth observations from nearby SMHI
stations, projected in EPSG:3006, onto the existing Lulea 2.5 km grid.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

import fetch_snowgrid as snow

ROOT = Path(__file__).resolve().parents[1]
SNOWMAP = ROOT / "docs" / "snowmap"
OUT = ROOT / "docs" / "snowgrid"
START_SEASON = 2018
K_NEAREST = 8
MIN_STATIONS = 3
MAX_DISTANCE_KM = 100.0
POWER = 2.0

TO_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform


def season_start(s: str) -> int:
    return int(str(s).split("-", 1)[0])


def idw_value(x, y, stations):
    ds = []
    for sx, sy, value in stations:
        d = math.hypot(x - sx, y - sy)
        if d <= 1.0:
            return float(value)
        if d <= MAX_DISTANCE_KM * 1000:
            ds.append((d, float(value)))
    if len(ds) < MIN_STATIONS:
        return None
    ds.sort(key=lambda t: t[0])
    ds = ds[:K_NEAREST]
    num = 0.0
    den = 0.0
    for d, v in ds:
        w = 1.0 / (d ** POWER)
        num += w * v
        den += w
    return num / den if den else None


def load_base_grid():
    candidates = [
        OUT / "2017-18_grid.geojson",
        *sorted(OUT.glob("*_grid.geojson")),
    ]
    for p in candidates:
        if p.exists():
            grid = json.loads(p.read_text(encoding="utf-8"))
            if grid.get("features"):
                return grid
    raise RuntimeError("No existing snow grid geometry found")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    station_index = json.loads((SNOWMAP / "index.json").read_text(encoding="utf-8"))
    station_meta = {str(x["id"]): x for x in station_index.get("stations", [])}

    base_grid = load_base_grid()
    grid_features = base_grid.get("features", [])
    grid_points = []
    for f in grid_features:
        g = transform(TO_3006, shape(f["geometry"]))
        c = g.centroid
        grid_points.append((c.x, c.y))

    station_xy = {}
    for sid, m in station_meta.items():
        try:
            from shapely.geometry import Point
            p = transform(TO_3006, Point(float(m["longitude"]), float(m["latitude"])))
            station_xy[sid] = (p.x, p.y)
        except Exception:
            continue

    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"seasons": []}
    by_season = {x["season"]: x for x in index.get("seasons", []) if x.get("season")}

    series_path = OUT / "series.json"
    series = json.loads(series_path.read_text(encoding="utf-8")) if series_path.exists() else {"seasons": []}
    series_by = {x["season"]: x for x in series.get("seasons", []) if x.get("season")}

    built = 0
    for meta in station_index.get("seasons", []):
        season = meta.get("season")
        if not season or season_start(season) < START_SEASON:
            continue
        p = SNOWMAP / meta.get("file", f"{season}.json")
        if not p.exists():
            continue
        obs = json.loads(p.read_text(encoding="utf-8"))
        grouped = defaultdict(list)
        for r in obs.get("observations", []):
            sid = str(r.get("station_id", ""))
            xy = station_xy.get(sid)
            v = r.get("depth_cm")
            if xy is None or v is None:
                continue
            grouped[r["date"]].append((xy[0], xy[1], float(v)))

        days = []
        for d in sorted(grouped):
            stations = grouped[d]
            values = []
            for x, y in grid_points:
                v = idw_value(x, y, stations)
                values.append(None if v is None else round(max(0.0, v), 1))
            days.append({"date": d, "values_cm": values, "station_count": len(stations)})

        if not days:
            continue

        # Preserve current majority-mainland properties in the shared geometry.
        grid_file = f"{season}_grid.geojson"
        (OUT / grid_file).write_text(
            json.dumps(base_grid, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        stats = snow.season_cell_stats(days, base_grid)
        threshold_stats = snow.seasonal_threshold_cover(days, base_grid)
        payload = {
            "season": season,
            "source": "SMHI MetObs IDW interpolation",
            "source_type": "observations_interpolated",
            "method": f"IDW p={POWER:g}, max {K_NEAREST} nearest stations, max distance {MAX_DISTANCE_KM:g} km, minimum {MIN_STATIONS} stations",
            "resolution_km": 2.5,
            "grid_file": grid_file,
            "days": days,
            "daily": snow.summarize_mainland(days, base_grid),
            "daily_mainland_majority": stats["daily_mainland_majority"],
            "daily_depth_class_pct": stats["daily_depth_class_pct"],
            "seasonal_threshold_cover_pct": threshold_stats["seasonal_threshold_cover_pct"],
            "seasonal_threshold_cover_days_used": threshold_stats["seasonal_threshold_cover_days_used"],
            "snow_duration_pct": stats["snow_duration_pct"],
            "snow_duration_counts": stats["snow_duration_counts"],
            "classified_cells": stats["classified_cells"],
            "mainland_touching_cells": stats.get("mainland_touching_cells"),
            "mainland_majority_cells": stats["mainland_majority_cells"],
        }
        data_file = f"{season}.json"
        (OUT / data_file).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        by_season[season] = {
            "season": season,
            "file": data_file,
            "grid_file": grid_file,
            "first_date": days[0]["date"],
            "last_date": days[-1]["date"],
            "dates": len(days),
            "cells": len(grid_features),
            "source": payload["source"],
            "source_type": payload["source_type"],
        }
        series_by[season] = {
            "season": season,
            "source": payload["source"],
            "source_type": payload["source_type"],
            "daily": payload["daily"],
            "daily_mainland_majority": payload["daily_mainland_majority"],
            "daily_depth_class_pct": payload["daily_depth_class_pct"],
            "seasonal_threshold_cover_pct": payload.get("seasonal_threshold_cover_pct", {}),
            "seasonal_threshold_cover_days_used": payload.get("seasonal_threshold_cover_days_used"),
            "snow_duration_pct": payload["snow_duration_pct"],
            "classified_cells": payload["classified_cells"],
            "mainland_touching_cells": payload.get("mainland_touching_cells"),
            "mainland_majority_cells": payload["mainland_majority_cells"],
        }
        built += 1
        print(f"Built {season}: {len(days)} days")

    index["seasons"] = sorted(by_season.values(), key=lambda x: x["season"])
    index["recent_extension"] = {
        "source": "SMHI MetObs snow-depth observations",
        "method": "IDW interpolation onto existing 2.5 km Lulea grid",
        "from_season": "2018-19",
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    series["seasons"] = sorted(series_by.values(), key=lambda x: x["season"])
    series["recent_extension"] = index["recent_extension"]
    series_path.write_text(
        json.dumps(series, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Recent snow grid seasons built: {built}")


if __name__ == "__main__":
    main()
