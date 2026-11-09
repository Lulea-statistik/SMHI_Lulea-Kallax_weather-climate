#!/usr/bin/env python3
"""Download and maintain SMHI MetObs data for Lulea-Kallax Flygplats."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "parameters.json"
DATA_DIR = ROOT / "data"
METADATA_DIR = ROOT / "metadata"
BASE_URL = os.environ.get(
    "SMHI_METOBS_BASE_URL",
    "https://opendata-download-metobs.smhi.se/api/version/latest",
).rstrip("/")
STOCKHOLM = ZoneInfo("Europe/Stockholm")
TIMEOUT_SECONDS = 60
MAX_RETRIES = 4

FIELDS = [
    "station_id",
    "station_name",
    "parameter_id",
    "parameter_name",
    "parameter_summary",
    "unit",
    "datetime_utc",
    "datetime_local",
    "from_ms",
    "to_ms",
    "value",
    "value_numeric",
    "quality",
    "reference",
    "source_period",
]

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "LuleaRobert2-SMHI-Kallax-vaderdata/1.0",
        "Accept": "application/json",
    }
)


def request_json(url: str, allow_404: bool = False) -> dict[str, Any] | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = SESSION.get(url, timeout=TIMEOUT_SECONDS)
            if response.status_code == 404 and allow_404:
                return None
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc
            wait_seconds = 2 ** (attempt - 1)
            print(
                f"Temporary error for {url}; retry {attempt}/{MAX_RETRIES} "
                f"after {wait_seconds}s: {exc}",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)
    return None


def request_text(url: str, allow_404: bool = False) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = SESSION.get(url, timeout=TIMEOUT_SECONDS, headers={'Accept':'text/csv, text/plain, */*'})
            if response.status_code == 404 and allow_404:
                return None
            response.raise_for_status()

            raw = response.content
            for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc
            wait_seconds = 2 ** (attempt - 1)
            print(
                f"Temporary error for {url}; retry {attempt}/{MAX_RETRIES} "
                f"after {wait_seconds}s: {exc}",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)
    return None


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def epoch_ms_to_iso(value: Any, local: bool = False) -> str:
    if value in (None, ""):
        return ""
    dt = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    if local:
        return dt.astimezone(STOCKHOLM).isoformat(timespec="seconds")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def numeric_value(value: Any) -> str:
    if value is None:
        return ""
    candidate = str(value).strip().replace(",", ".")
    try:
        float(candidate)
        return candidate
    except ValueError:
        return ""


def payload_metadata(
    payload: dict[str, Any], parameter_cfg: dict[str, Any], station_cfg: dict[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    parameter = payload.get("parameter") or {}
    station = payload.get("station") or {}

    parameter_meta = {
        "parameter_id": str(parameter.get("key") or parameter_cfg["id"]),
        "parameter_name": str(parameter.get("name") or parameter_cfg.get("name") or ""),
        "parameter_summary": str(parameter.get("summary") or ""),
        "unit": str(parameter.get("unit") or ""),
    }
    station_meta = {
        "station_id": str(station.get("key") or station_cfg["id"]),
        "station_name": str(station.get("name") or station_cfg.get("name") or ""),
    }
    return parameter_meta, station_meta


def datetime_text_to_epoch_ms(value: str) -> int:
    text = value.strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        except ValueError:
            continue

    raise ValueError(f"Unsupported SMHI datetime: {value!r}")


def fetch_period_csv(
    parameter_cfg: dict[str, Any], station_cfg: dict[str, Any], period: str
) -> tuple[list[dict[str, str]], dict[str, str], dict[str, str]]:
    parameter_id = str(parameter_cfg["id"])
    station_id = str(station_cfg["id"])

    urls = [
        (
            f"{BASE_URL}/parameter/{parameter_id}/station/{station_id}"
            f"/period/{period}/data.csv"
        ),
        (
            "https://opendata-download.smhi.se/stream"
            f"?type=metobs&parameterIds={parameter_id}"
            f"&stationId={station_id}&period={period}"
        ),
    ]

    content: str | None = None
    source_url = ""
    failures=[]
    for url in urls:
        try:
            content = request_text(url, allow_404=True)
        except RuntimeError as exc:
            failures.append(str(exc))
            continue
        if content:
            source_url = url
            break
    if not content and failures:
        raise RuntimeError('CSV archive sources failed: '+'; '.join(failures))

    if not content:
        return [], {}, {}

    parsed_rows = list(csv.reader(io.StringIO(content), delimiter=";"))
    parameter_meta = {
        "parameter_id": parameter_id,
        "parameter_name": str(parameter_cfg.get("name") or ""),
        "parameter_summary": "",
        "unit": "",
    }
    station_meta = {
        "station_id": station_id,
        "station_name": str(station_cfg.get("name") or ""),
    }

    for index, cells in enumerate(parsed_rows[:-1]):
        normalized = [cell.strip() for cell in cells]
        if normalized and normalized[0].lower().startswith("stationsnamn"):
            values = parsed_rows[index + 1]
            if values:
                station_meta["station_name"] = values[0].strip() or station_meta["station_name"]
            if len(values) > 1:
                station_meta["station_id"] = values[1].strip() or station_meta["station_id"]

        if normalized and normalized[0].lower().startswith("parameternamn"):
            values = parsed_rows[index + 1]
            if values:
                parameter_meta["parameter_name"] = values[0].strip() or parameter_meta["parameter_name"]
            if len(values) > 1:
                parameter_meta["parameter_summary"] = values[1].strip()
            if len(values) > 2:
                parameter_meta["unit"] = values[2].strip()

    header_index = None
    for index, cells in enumerate(parsed_rows):
        if not cells:
            continue
        first = cells[0].strip().lower()
        second = cells[1].strip().lower() if len(cells) > 1 else ""
        if (first == "datum" and "tid" in second) or (
            "datum tid" in first and ("från" in first or "fran" in first)
        ):
            header_index = index
            break

    if header_index is None:
        print(
            f"  CSV fallback did not find a data header for parameter {parameter_id} "
            f"({source_url})",
            file=sys.stderr,
        )
        return [], parameter_meta, station_meta

    header = [cell.strip() for cell in parsed_rows[header_index]]
    quality_index = next(
        (i for i, name in enumerate(header) if "kvalitet" in name.lower()),
        None,
    )
    if quality_index is None or quality_index < 1:
        print(
            f"  CSV fallback did not find the quality/value columns for parameter {parameter_id}",
            file=sys.stderr,
        )
        return [], parameter_meta, station_meta

    value_index = quality_index - 1
    interval_format = "datum tid" in header[0].lower() and (
        "från" in header[0].lower() or "fran" in header[0].lower()
    )

    rows: list[dict[str, str]] = []
    for cells in parsed_rows[header_index + 1 :]:
        if len(cells) <= quality_index:
            continue

        try:
            if interval_format:
                start_text = cells[0].strip()
                end_text = cells[1].strip()
                if not start_text:
                    continue
                start_ms = datetime_text_to_epoch_ms(start_text)
                end_ms = datetime_text_to_epoch_ms(end_text) if end_text else None
            else:
                date_text = cells[0].strip()
                time_text = cells[1].strip()
                if not date_text:
                    continue
                start_ms = datetime_text_to_epoch_ms(
                    f"{date_text} {time_text}".strip()
                )
                end_ms = None
        except ValueError:
            continue

        raw_value = cells[value_index].strip()
        rows.append(
            {
                "station_id": station_meta["station_id"],
                "station_name": station_meta["station_name"],
                "parameter_id": parameter_meta["parameter_id"],
                "parameter_name": parameter_meta["parameter_name"],
                "parameter_summary": parameter_meta["parameter_summary"],
                "unit": parameter_meta["unit"],
                "datetime_utc": epoch_ms_to_iso(start_ms),
                "datetime_local": epoch_ms_to_iso(start_ms, local=True),
                "from_ms": str(start_ms),
                "to_ms": "" if end_ms is None else str(end_ms),
                "value": text_value(raw_value),
                "value_numeric": numeric_value(raw_value),
                "quality": cells[quality_index].strip(),
                "reference": "",
                "source_period": f"{period}-csv",
            }
        )

    return rows, parameter_meta, station_meta


def fetch_period(
    parameter_cfg: dict[str, Any], station_cfg: dict[str, Any], period: str
) -> tuple[list[dict[str, str]], dict[str, str], dict[str, str]]:
    parameter_id = str(parameter_cfg["id"])
    station_id = str(station_cfg["id"])
    url = (
        f"{BASE_URL}/parameter/{parameter_id}/station/{station_id}"
        f"/period/{period}/data.json"
    )
    if period == 'corrected-archive':
        return fetch_period_csv(parameter_cfg, station_cfg, period)
    try:
        payload = request_json(url, allow_404=True)
    except RuntimeError:
        return fetch_period_csv(parameter_cfg, station_cfg, period)
    if payload is None:
        return fetch_period_csv(parameter_cfg, station_cfg, period)

    parameter_meta, station_meta = payload_metadata(payload, parameter_cfg, station_cfg)
    rows: list[dict[str, str]] = []

    for observation in payload.get("value") or []:
        # SMHI uses "date" for point observations (temperature, wind etc.)
        # and "from"/"to" for interval observations (for example precipitation).
        observation_ms = observation.get("date")
        from_ms = observation.get("from")
        to_ms = observation.get("to")
        timestamp_ms = observation_ms if observation_ms not in (None, "") else from_ms
        if timestamp_ms in (None, ""):
            continue

        raw_value = observation.get("value")
        rows.append(
            {
                "station_id": station_meta["station_id"],
                "station_name": station_meta["station_name"],
                "parameter_id": parameter_meta["parameter_id"],
                "parameter_name": parameter_meta["parameter_name"],
                "parameter_summary": parameter_meta["parameter_summary"],
                "unit": parameter_meta["unit"],
                "datetime_utc": epoch_ms_to_iso(timestamp_ms),
                "datetime_local": epoch_ms_to_iso(timestamp_ms, local=True),
                "from_ms": str(timestamp_ms),
                "to_ms": "" if to_ms is None else str(to_ms),
                "value": text_value(raw_value),
                "value_numeric": numeric_value(raw_value),
                "quality": str(observation.get("quality") or ""),
                "reference": str(observation.get("ref") or ""),
                "source_period": period,
            }
        )
    return rows, parameter_meta, station_meta


def fetch_recent(
    parameter_cfg: dict[str, Any], station_cfg: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, str], dict[str, str], str]:
    last_parameter_meta: dict[str, str] = {}
    last_station_meta: dict[str, str] = {}
    for period in ("latest-months", "latest-day", "latest-hour"):
        rows, parameter_meta, station_meta = fetch_period(parameter_cfg, station_cfg, period)
        last_parameter_meta = parameter_meta or last_parameter_meta
        last_station_meta = station_meta or last_station_meta
        if rows:
            return rows, parameter_meta, station_meta, period
    return [], last_parameter_meta, last_station_meta, ""


def row_key(row: dict[str, str]) -> tuple[str, str]:
    return row.get("from_ms", ""), row.get("to_ms", "")


def sort_key(row: dict[str, str]) -> tuple[int, int]:
    def as_int(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return as_int(row.get("from_ms", "")), as_int(row.get("to_ms", ""))


def read_partition(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row_key(row): row for row in csv.DictReader(handle)}


def csv_text(rows: Iterable[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_partition(path: Path, incoming: list[dict[str, str]]) -> tuple[int, int]:
    existing = read_partition(path)
    before = len(existing)

    for row in incoming:
        existing[row_key(row)] = row

    ordered = sorted(existing.values(), key=sort_key)
    content = csv_text(ordered)
    old_content = path.read_text(encoding="utf-8-sig") if path.exists() else ""

    if content != old_content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")

    return before, len(ordered)


def merge_rows(parameter_id: str, rows: list[dict[str, str]]) -> tuple[int, int, set[str]]:
    by_year: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        year = row["datetime_utc"][:4]
        if len(year) == 4 and year.isdigit():
            by_year[year].append(row)

    total_before = 0
    total_after = 0
    touched: set[str] = set()

    for year, year_rows in sorted(by_year.items()):
        path = DATA_DIR / f"parameter_{parameter_id}" / f"{year}.csv"
        before, after = write_partition(path, year_rows)
        total_before += before
        total_after += after
        touched.add(str(path.relative_to(ROOT)).replace("\\", "/"))

    return total_before, total_after, touched


def write_dict_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    content = buffer.getvalue()
    old = path.read_text(encoding="utf-8-sig") if path.exists() else ""

    if content != old:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")


def build_manifest() -> None:
    rows: list[dict[str, Any]] = []

    for path in sorted(DATA_DIR.glob("parameter_*/*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            data = list(csv.DictReader(handle))

        if not data:
            continue

        dates = [row.get("datetime_utc", "") for row in data if row.get("datetime_utc")]

        rows.append(
            {
                "parameter_id": data[0].get(
                    "parameter_id", path.parent.name.replace("parameter_", "")
                ),
                "parameter_name": data[0].get("parameter_name", ""),
                "year": path.stem,
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "row_count": len(data),
                "min_datetime_utc": min(dates) if dates else "",
                "max_datetime_utc": max(dates) if dates else "",
            }
        )

    write_dict_rows(
        DATA_DIR / "manifest.csv",
        [
            "parameter_id",
            "parameter_name",
            "year",
            "path",
            "row_count",
            "min_datetime_utc",
            "max_datetime_utc",
        ],
        rows,
    )


def determine_mode(requested: str) -> str:
    if requested != "auto":
        return requested

    has_data = any(DATA_DIR.glob("parameter_*/*.csv"))
    if not has_data:
        return "bootstrap"

    if datetime.now(timezone.utc).day == 1:
        return "refresh-all"

    return "update"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("auto", "bootstrap", "update", "refresh-all"),
        default="auto",
    )
    args = parser.parse_args()

    config = load_config()
    station_cfg = config["station"]
    mode = determine_mode(args.mode)

    print(f"SMHI station {station_cfg['id']} - mode: {mode}")

    run_started = datetime.now(timezone.utc)
    parameter_status: list[dict[str, Any]] = []
    touched_files: set[str] = set()
    total_downloaded = 0

    for parameter_cfg in config["parameters"]:
        parameter_id = str(parameter_cfg["id"])
        parameter_station = parameter_cfg.get("station") or station_cfg
        print(f"Parameter {parameter_id}: {parameter_cfg.get('name', '')} (station {parameter_station['id']})")

        incoming: list[dict[str, str]] = []
        parameter_meta: dict[str, str] = {}
        periods_used: list[str] = []
        status = "ok"
        error_message = ""

        try:
            if mode in ("bootstrap", "refresh-all"):
                archive_rows, pmeta, _ = fetch_period(
                    parameter_cfg, parameter_station, "corrected-archive"
                )
                if archive_rows:
                    incoming.extend(archive_rows)
                    periods_used.append("corrected-archive")
                    parameter_meta = pmeta or parameter_meta
                    print(f"  corrected-archive: {len(archive_rows):,} rows")
                else:
                    print("  corrected-archive: unavailable or empty")

            recent_rows, pmeta, _, recent_period = fetch_recent(parameter_cfg, parameter_station)
            if recent_rows:
                incoming.extend(recent_rows)
                periods_used.append(recent_period)
                parameter_meta = pmeta or parameter_meta
                print(f"  {recent_period}: {len(recent_rows):,} rows")
            else:
                print("  recent data: unavailable or empty")

            if incoming:
                _, total_after, touched = merge_rows(parameter_id, incoming)
                touched_files.update(touched)
                total_downloaded += len(incoming)
                print(f"  stored rows after merge: {total_after:,}")
            else:
                status = "unavailable"

        except Exception as exc:
            status = "error"
            error_message = str(exc)
            print(f"  ERROR: {exc}", file=sys.stderr)

        parameter_status.append(
            {
                "parameter_id": parameter_id,
                "configured_name": parameter_cfg.get("name", ""),
                "parameter_name": parameter_meta.get("parameter_name", ""),
                "parameter_summary": parameter_meta.get("parameter_summary", ""),
                "unit": parameter_meta.get("unit", ""),
                "status": status,
                "periods_used": "+".join(periods_used),
                "error": error_message,
            }
        )

    build_manifest()

    write_dict_rows(
        METADATA_DIR / "parameters.csv",
        [
            "parameter_id",
            "configured_name",
            "parameter_name",
            "parameter_summary",
            "unit",
            "status",
            "periods_used",
            "error",
        ],
        parameter_status,
    )

    run_finished = datetime.now(timezone.utc)
    ok_parameters = [row for row in parameter_status if row["status"] == "ok"]
    unavailable_parameters = [row for row in parameter_status if row["status"] == "unavailable"]
    error_parameters = [row for row in parameter_status if row["status"] == "error"]
    last_run = {
        "station_id": str(station_cfg["id"]),
        "station_name": station_cfg.get("name", ""),
        "mode": mode,
        "started_utc": run_started.isoformat(timespec="seconds"),
        "finished_utc": run_finished.isoformat(timespec="seconds"),
        "downloaded_rows_before_deduplication": total_downloaded,
        "parameters_configured": len(parameter_status),
        "parameters_ok": len(ok_parameters),
        "parameters_unavailable": len(unavailable_parameters),
        "parameters_error": len(error_parameters),
        "health": (
            "ok"
            if len(ok_parameters) == len(parameter_status)
            else "partial"
            if len(ok_parameters) >= max(1, len(parameter_status) // 2)
            else "failed"
        ),
        "touched_partition_count": len(touched_files),
        "touched_partitions": sorted(touched_files),
    }

    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    (METADATA_DIR / "last_run.json").write_text(
        json.dumps(last_run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = error_parameters
    print(
        f"Done. Downloaded {total_downloaded:,} rows before deduplication; "
        f"{len(ok_parameters)}/{len(parameter_status)} parameters returned data; "
        f"{len(errors)} parameter errors."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
