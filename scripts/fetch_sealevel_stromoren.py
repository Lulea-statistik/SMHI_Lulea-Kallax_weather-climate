#!/usr/bin/env python3
"""Independent Strömören RH 2000 bootstrap. Preserve source CSVs without rewriting observations."""
import argparse
import datetime as dt
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sealevel" / "stromoren"
API = "https://opendata-download-ocobs.smhi.se/api/version/1.0"
STATION = "35183"
HEADERS = {"User-Agent": "Lulea-statistik-sealevel/1.0 (GitHub Actions)", "Accept": "application/json,text/csv,*/*"}

def fetch(url):
    if not url.startswith("https://opendata-download-ocobs.smhi.se/"):
        raise ValueError("Unexpected API host: " + url)
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=90) as response:
        return response.read()

def get_json(url):
    return json.loads(fetch(url).decode("utf-8-sig"))

def links(record):
    return record.get("link", []) if isinstance(record, dict) else []

def source_csv(period):
    # Prefer the official data CSV link described by the selected period resource.
    for link in links(period):
        href = link.get("href", "")
        if link.get("type", "").lower() in ("text/csv", "application/csv") or href.lower().endswith(".csv"):
            return href
    # Some SMHI versions expose the file under a data node.
    for data in period.get("data", []):
        for link in links(data):
            href = link.get("href", "")
            if link.get("type", "").lower() in ("text/csv", "application/csv") or href.lower().endswith(".csv"):
                return href
    raise RuntimeError("SMHI period metadata has no downloadable CSV link")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("bootstrap", "update"), default="bootstrap")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    # Never silently conflate reference systems. SMHI has multiple sea-level parameters.
    candidates = []
    for number in (6, 13):
        info = get_json(f"{API}/parameter/{number}.json")
        title = str(info.get("title", ""))
        print(f"Parameter {number}: {title}")
        if "rh 2000" in title.lower() or "rh2000" in title.lower():
            candidates.append(number)
    if len(candidates) != 1:
        raise RuntimeError(f"Could not uniquely verify an RH 2000 sea-level parameter (matches: {candidates}); refusing to publish RW or unknown datum")
    parameter = candidates[0]
    station = get_json(f"{API}/parameter/{parameter}/station/{STATION}.json")
    title = str(station.get("title", station.get("name", "")))
    if "strömören" not in title.lower() and "stromoren" not in title.lower():
        raise RuntimeError(f"Station identity not confirmed: {title!r}")
    periods = station.get("period", [])
    required = ("corrected-archive", "latest-months") if args.mode == "bootstrap" else ("latest-months",)
    manifest = {"station_id": STATION, "station_name": title, "parameter": parameter, "reference": "RH 2000",
                "unit": "cm", "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "sources": {}, "mode": args.mode}
    for key in required:
        matching = [p for p in periods if str(p.get("key", "")).lower() == key]
        if not matching:
            raise RuntimeError(f"SMHI station does not advertise required period {key}; options: {[p.get('key') for p in periods]}")
        item = matching[0]
        details = next((l["href"] for l in links(item) if l.get("type") == "application/json" and l.get("href", "").endswith(".json")), None)
        if not details:
            details = f"{API}/parameter/{parameter}/station/{STATION}/period/{key}.json"
        period_info = get_json(details)
        url = source_csv(period_info)
        raw = fetch(url)
        # Cheap content check, never commit an HTML error page as measurements.
        if not raw or raw.lstrip()[:1] == b"<":
            raise RuntimeError(f"Unexpected empty/HTML response for {key}")
        file = OUT / f"{key}.csv"
        file.write_bytes(raw)
        manifest["sources"][key] = {"url": url, "file": file.name, "bytes": len(raw)}
        print(f"Saved {file} ({len(raw)} bytes)")
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Water-level bootstrap completed; original SMHI CSV format retained.")

if __name__ == "__main__":
    main()
