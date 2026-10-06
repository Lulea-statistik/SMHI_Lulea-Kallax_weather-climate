#!/usr/bin/env python3
"""Backfill derived GridClim snow statistics from already generated season files."""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape

import fetch_snowgrid as snow

OUT_ROOT = snow.OUT_ROOT
SERIES_PATH = snow.SERIES_PATH


def main():
    mainland = snow.load_mainland_geometry()
    if mainland is None:
        raise RuntimeError("Mainland geometry is missing from lightning geography")

    seasons = []
    for data_path in sorted(OUT_ROOT.glob("????-??.json")):
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        season = payload.get("season")
        grid_path = OUT_ROOT / payload.get("grid_file", f"{season}_grid.geojson")
        if not season or not grid_path.exists():
            continue

        grid = json.loads(grid_path.read_text(encoding="utf-8"))
        # Add/update the same mainland-touch flag for every existing grid cell.
        for feat in grid.get("features", []):
            props = feat.setdefault("properties", {})
            try:
                props["touches_mainland"] = bool(shape(feat["geometry"]).intersects(mainland))
            except Exception:
                props["touches_mainland"] = False
        grid_path.write_text(
            json.dumps(grid, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        stats = snow.season_cell_stats(payload.get("days", []), grid)
        payload["daily_mainland"] = stats["daily_mainland"]
        payload["snow_duration_pct"] = stats["snow_duration_pct"]
        payload["snow_duration_counts"] = stats["snow_duration_counts"]
        payload["classified_cells"] = stats["classified_cells"]
        payload["mainland_touching_cells"] = stats["mainland_touching_cells"]
        data_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        seasons.append({
            "season": season,
            "daily": payload.get("daily", []),
            "daily_mainland": payload.get("daily_mainland", []),
            "snow_duration_pct": payload.get("snow_duration_pct", {}),
            "classified_cells": payload.get("classified_cells"),
            "mainland_touching_cells": payload.get("mainland_touching_cells"),
        })
        print(f"Backfilled {season}: {stats['classified_cells']} cells, {stats['mainland_touching_cells']} mainland-touching")

    SERIES_PATH.write_text(
        json.dumps(
            {
                "source": "SMHIGridClim",
                "resolution_km": 2.5,
                "snow_threshold_cm": 1,
                "duration_classes": [x[0] for x in snow.SNOW_WEEK_CLASSES],
                "seasons": sorted(seasons, key=lambda x: x["season"]),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(seasons)} seasons to {SERIES_PATH}")


if __name__ == "__main__":
    main()
