#!/usr/bin/env python3
"""Read-only diagnostic of SMHI algae WFS/WMS metadata and sampled records."""
import json
import os
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET
import requests

BASE = "https://opendata-view.smhi.se/algae"
TYPE = "algae:SR.SeaSurfaceArea"
OUT = Path(os.environ.get("ALGAE_AUDIT_DIR", "algae-service-audit"))
OUT.mkdir(parents=True, exist_ok=True)
session = requests.Session()
session.headers["User-Agent"] = "Lulea-statistik-SMHI-algae-audit/1.0"
errors = []

def get(name, endpoint, params):
    try:
        response = session.get(BASE + endpoint, params=params, timeout=45)
        response.raise_for_status()
        content = response.content
        if len(content) > 15_000_000:
            raise ValueError("Response exceeds 15 MB safety limit")
        (OUT / name).write_bytes(content)
        if b"ExceptionReport" in content[:1000] or b"ServiceException" in content[:1000]:
            raise ValueError("OGC service returned an exception document")
        return response
    except (requests.RequestException, ValueError) as exc:
        errors.append(f"{name}: {exc}")
        return None

def all_text(root, local):
    return [" ".join("".join(e.itertext()).split()) for e in root.iter() if e.tag.split("}")[-1] == local]

summary = {"source": BASE, "type_name": TYPE, "dates": {}, "errors": errors}
for kind in ("wfs", "wms"):
    result = get(kind + "-capabilities.xml", "/" + kind, {"service": kind.upper(), "request": "GetCapabilities"})
    if result is None:
        continue
    try:
        xml = ET.fromstring(result.content)
        summary[kind] = {
            "layer_or_feature_titles": all_text(xml, "Title")[:30],
            "style_names": all_text(xml, "Name")[:60],
        }
    except ET.ParseError as exc:
        errors.append(f"{kind} capability XML: {exc}")

schema = get("describe-feature-type.xsd", "/wfs", {
    "service": "WFS", "version": "2.0.0", "request": "DescribeFeatureType", "typeNames": TYPE
})
if schema is not None:
    try:
        xml = ET.fromstring(schema.content)
        summary["schema_elements"] = [
            {"name": e.attrib.get("name"), "type": e.attrib.get("type")}
            for e in xml.iter() if e.tag.split("}")[-1] == "element"
        ][:100]
    except ET.ParseError as exc:
        errors.append(f"DescribeFeatureType: {exc}")

for day in ("2026-06-19", "2026-06-25"):
    data = get(day + "-wfs-sample.json", "/wfs", {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": TYPE, "outputFormat": "application/json", "srsName": "EPSG:4326",
        "count": 100, "startIndex": 0,
        "CQL_FILTER": f"date='{day}' AND BBOX(geom,21.0,65.1,23.6,66.1,'EPSG:4326')",
    })
    if data is None:
        continue
    try:
        payload = data.json()
        features = payload.get("features", [])
        summary["dates"][day] = {
            "numberMatched": payload.get("numberMatched"),
            "numberReturned": payload.get("numberReturned"),
            "sample_size": len(features),
            "classes": dict(Counter(str((f.get("properties") or {}).get("class")) for f in features)),
            "sample_properties": [(f.get("properties") or {}) for f in features[:3]],
        }
    except (ValueError, TypeError) as exc:
        errors.append(f"{day}: {exc}")

(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
if errors:
    raise SystemExit("Some metadata requests failed; see saved audit files and summary.json")
