#!/usr/bin/env python3
"""Audit algae class coverage without assigning unverified meanings to SMHI codes."""
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWN = {"surface", "risk", "cloud", "no_data"}

def run(year):
    folder = ROOT / "docs" / "algae" / str(year)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    polygons = Counter()
    days = Counter()
    null_flags = 0
    mismatches = []
    for row in manifest.get("dates", []):
        geo = json.loads((folder / row["file"]).read_text(encoding="utf-8"))
        present = Counter()
        for feature in geo.get("features", []):
            p = feature.get("properties") or {}
            key = p.get("algae_class", "other")
            polygons[key] += 1
            present[key] += 1
            if all(p.get(k) is None for k in ("surface", "sub_surfac", "cloud", "no_data")):
                null_flags += 1
        for key in present:
            days[key] += 1
        in_manifest = set((row.get("classes_area_km2") or {}).keys())
        if set(present) != in_manifest:
            mismatches.append(row["date"])
    return {
        "year": year,
        "dates": len(manifest.get("dates", [])),
        "polygon_counts": dict(sorted(polygons.items())),
        "days_by_class": dict(sorted(days.items())),
        "polygons_all_category_flags_null": null_flags,
        "unverified_classes": sorted(k for k in polygons if k not in KNOWN),
        "manifest_mismatch_dates": mismatches,
        "note": "Unverified classes cannot be interpreted as no algae."
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = run(args.year)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and (report["unverified_classes"] or report["manifest_mismatch_dates"]):
        raise SystemExit(1)
