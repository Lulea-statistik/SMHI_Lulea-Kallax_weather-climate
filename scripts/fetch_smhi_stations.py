#!/usr/bin/env python3
"""Independent, configurable SMHI multi-station observation import.

Preserves the existing Kallax data/parameter_* pipeline.
Storage: data/stations/<station-id>/parameter_<parameter-id>.csv
Missing parameters remain unavailable, never silently mapped to another station.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_smhi import fetch_period, fetch_recent, FIELDS

CONFIG = ROOT / "config" / "stations.json"
DATA = ROOT / "data" / "stations"
METADATA = ROOT / "metadata" / "stations_last_run.json"


def load_existing(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        return {(r.get("from_ms", ""), r.get("to_ms", "")): r for r in csv.DictReader(f)}


def save_merged(path: Path, incoming: list[dict[str, str]]) -> tuple[int, int]:
    existing = load_existing(path)
    before = len(existing)
    for row in incoming:
        key = (row.get("from_ms", ""), row.get("to_ms", ""))
        if key[0]:
            existing[key] = {k: str(row.get(k, "") or "") for k in FIELDS}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(existing.values(), key=lambda r: (r["from_ms"], r["to_ms"])))
    os.replace(temp, path)
    return before, len(existing)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["update", "bootstrap"], default="update")
    parser.add_argument("--stations", help="Comma-separated SMHI station IDs; default all configured")
    parser.add_argument("--parameters", help="Comma-separated parameter IDs; default all configured")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    stations = {x.strip() for x in args.stations.split(",")} if args.stations else None
    params = {int(x.strip()) for x in args.parameters.split(",")} if args.parameters else None
    results = []
    for station in config["stations"]:
        sid = str(station["id"])
        if stations is not None and sid not in stations:
            continue
        for pid in station["parameters"]:
            pid = int(pid)
            if params is not None and pid not in params:
                continue
            pcfg = {"id": str(pid), "name": config.get("parameter_names", {}).get(str(pid), str(pid))}
            target = DATA / sid / ("parameter_" + str(pid) + ".csv")
            incoming = []
            problems = []
            if args.mode == "bootstrap":
                try:
                    archived, _, _ = fetch_period(pcfg, station, "corrected-archive")
                    incoming.extend(archived)
                except Exception as exc:
                    problems.append("archive: " + str(exc))
            if station.get("active") is False:
                print("Inactive station: skip recent fetch for " + station["name"])
            else:
                try:
                    recent, _, _, _ = fetch_recent(pcfg, station)
                    incoming.extend(recent)
                except Exception as exc:
                    problems.append("recent: " + str(exc))
            before, after = save_merged(target, incoming) if incoming else (len(load_existing(target)), len(load_existing(target)))
            status = "ok" if incoming else ("existing" if after and not problems else "unavailable")
            print(f"{station['name']} ({sid}), parameter {pid}: {status}, {before} -> {after} observations")
            results.append({"station_id": sid, "station_name": station["name"], "parameter_id": pid,
                            "status": status, "downloaded": len(incoming), "stored": after, "warnings": problems})
    if not results:
        raise SystemExit("No station/parameter pairs match requested filters")
    METADATA.parent.mkdir(parents=True, exist_ok=True)
    METADATA.write_text(json.dumps({"generated_utc": datetime.now(timezone.utc).isoformat(),
                                     "mode": args.mode, "results": results}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    if any(x["warnings"] for x in results):
        print("Warning: some station/parameter requests failed. Review metadata/stations_last_run.json")
    if not any(x["stored"] for x in results):
        raise SystemExit("No station observations available; refusing empty import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
