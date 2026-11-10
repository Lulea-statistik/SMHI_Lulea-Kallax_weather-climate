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
warnings = []

def get(name, endpoint, params, *, required=True):
    try:
        response = session.get(BASE + endpoint, params=params, timeout=45)
        response.raise_for_status()
        content = response.content
        if len(content) > 15_000_000:
            raise ValueError("Response exceeds 15 MB safety limit")
        if b"ExceptionReport" in content[:1000] or b"ServiceException" in content[:1000]:
            (OUT / (name + ".service-exception.xml")).write_bytes(content)
            try:
                root = ET.fromstring(content)
                detail = " | ".join(
                    " ".join("".join(e.itertext()).split())
                    for e in root.iter()
                    if e.tag.split("}")[-1] in {"ServiceException", "ExceptionText"}
                )[:1000]
            except ET.ParseError:
                detail = content[:500].decode("utf-8", errors="replace")
            raise ValueError("OGC ServiceException: " + detail)
        (OUT / name).write_bytes(content)
        return response
    except (requests.RequestException, ValueError) as exc:
        (errors if required else warnings).append(f"{name}: {exc}")
        return None

def all_text(root, local):
    return [" ".join("".join(e.itertext()).split()) for e in root.iter() if e.tag.split("}")[-1] == local]

summary = {"source": BASE, "type_name": TYPE, "dates": {}, "errors": errors, "warnings": warnings}
for kind in ("wfs", "wms"):
    result = get(kind + "-capabilities.xml", "/" + kind, {"service": kind.upper(), "request": "GetCapabilities"})
    if result is None:
        continue
    try:
        xml = ET.fromstring(result.content)
        summary[kind] = {
            "layer_or_feature_titles": all_text(xml, "Title")[:30],
            "all_names_untyped": all_text(xml, "Name")[:60],
        }
        if kind == "wms":
            summary[kind]["named_layers"] = [
                {"name": next((e.text for e in node if e.tag.split("}")[-1] == "Name"), None),
                 "title": next((e.text for e in node if e.tag.split("}")[-1] == "Title"), None)}
                for node in xml.iter() if node.tag.split("}")[-1] == "Layer"
                and any(child.tag.split("}")[-1] == "Name" for child in node)
            ]
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

# Only use actual WMS Layer/Name values, not nested Layer/Title strings.
# OGC WMS 1.1.1 uses lon/lat order for EPSG:4326 BBOX.
# Per-layer failures are diagnostic warnings, not mandatory WFS failures.
layers = sorted({
    layer["name"]
    for layer in summary.get("wms", {}).get("named_layers", [])
    if layer.get("name")
})
summary["wms_layer_comparison"] = {}
summary["wms_audit_note"] = (
    "Only advertised Layer/Name values are queried; "
    "SR.SeaSurfaceArea.Algae was a title, not an addressable WMS layer."
)
if not layers:
    warnings.append("No addressable WMS layers found in GetCapabilities")
for layer in layers:
    clean = layer.replace(".", "_")
    info = {"layer": layer, "legends": [], "maps": []}
    summary["wms_layer_comparison"][layer] = info
    legend = get(f"legend-{clean}.png", "/wms", {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetLegendGraphic",
        "LAYER": layer, "FORMAT": "image/png", "WIDTH": 28, "HEIGHT": 28
    }, required=False)
    if legend is not None:
        info["legend_content_type"] = legend.headers.get("Content-Type")
        info["legends"].append(f"legend-{clean}.png")
    for day in ("2026-06-19", "2026-06-25"):
        filename = f"map-{clean}-{day}.png"
        image = get(filename, "/wms", {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": layer, "STYLES": "", "FORMAT": "image/png",
            "TRANSPARENT": "TRUE", "SRS": "EPSG:4326",
            "BBOX": "21.0,65.1,23.6,66.1", "WIDTH": 1040, "HEIGHT": 600,
            "CQL_FILTER": f"date='{day}'"
        }, required=False)
        if image is not None:
            info["maps"].append(filename)
            info[f"map_{day}_content_type"] = image.headers.get("Content-Type")

(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
if warnings:
    print("Non-fatal WMS warnings recorded; inspect service-exception XML and named_layers.")
if errors:
    raise SystemExit("Some metadata requests failed; see saved audit files and summary.json")
