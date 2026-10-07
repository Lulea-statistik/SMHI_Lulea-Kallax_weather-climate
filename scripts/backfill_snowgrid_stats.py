#!/usr/bin/env python3
"""Backfill derived GridClim snow statistics from already generated season files."""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

import fetch_snowgrid as snow

OUT_ROOT = snow.OUT_ROOT
SERIES_PATH = snow.SERIES_PATH


def main():
    mainland = snow.load_mainland_geometry()
    if mainland is None:
        raise RuntimeError("Mainland geometry is missing from lightning geography")

    to_3006 = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
    mainland_3006 = transform(to_3006, mainland)

    seasons = []
    for data_path in sorted(OUT_ROOT.glob("????-??.json")):
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        season = payload.get("season")
        grid_path = OUT_ROOT / payload.get("grid_file", f"{season}_grid.geojson")
        if not season or not grid_path.exists():
            continue

        grid = json.loads(grid_path.read_text(encoding="utf-8"))
        # Classify each clipped municipality-cell by how much of its mapped
        # area is mainland. This separates coast/sea cells more clearly than
        # the previous "touches mainland" flag.
        for feat in grid.get("features", []):
            props = feat.setdefault("properties", {})
            try:
                cell_3006 = transform(to_3006, shape(feat["geometry"]))
                props["touches_mainland"] = bool(cell_3006.intersects(mainland_3006))
                if cell_3006.area > 0:
                    share = 100.0 * cell_3006.intersection(mainland_3006).area / cell_3006.area
                else:
                    share = 0.0
                share = max(0.0, min(100.0, share))
                props["mainland_share_pct"] = round(share, 1)
                props["mainland_majority"] = bool(share >= 50.0)
            except Exception:
                props["touches_mainland"] = False
                props["mainland_share_pct"] = 0.0
                props["mainland_majority"] = False
        grid_path.write_text(
            json.dumps(grid, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        stats = snow.season_cell_stats(payload.get("days", []), grid)
        payload["daily"] = snow.summarize_mainland(payload.get("days", []), grid)
        payload["daily_mainland_majority"] = stats["daily_mainland_majority"]
        payload["daily_depth_class_pct"] = stats["daily_depth_class_pct"]
        payload["snow_duration_pct"] = stats["snow_duration_pct"]
        payload["snow_duration_counts"] = stats["snow_duration_counts"]
        payload["classified_cells"] = stats["classified_cells"]
        payload["mainland_touching_cells"] = stats.get("mainland_touching_cells")
        payload["mainland_majority_cells"] = stats["mainland_majority_cells"]
        data_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        seasons.append({
            "season": season,
            "daily": payload.get("daily", []),
            "daily_mainland_majority": payload.get("daily_mainland_majority", []),
            "daily_depth_class_pct": payload.get("daily_depth_class_pct", []),
            "snow_duration_pct": payload.get("snow_duration_pct", {}),
            "classified_cells": payload.get("classified_cells"),
            "mainland_touching_cells": payload.get("mainland_touching_cells"),
            "mainland_majority_cells": payload.get("mainland_majority_cells"),
        })
        print(f"Backfilled {season}: {stats['classified_cells']} cells, {stats['mainland_majority_cells']} majority-mainland")

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
