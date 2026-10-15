#!/usr/bin/env python3
"""Extract SMHI coastal-warning lines observed in archived snapshots.

This is NOT a full coastline reference. Do not use line-length percentages
until a complete, validated SMHI coastal reference becomes available.
Source and target geometries are verified EPSG:4326 GeoJSON; lengths in EPSG:3006.
"""
import hashlib
import json
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/"data"/"warning_snapshots"
BOUNDARY=ROOT/"docs"/"snowmap_boundary.geojson"
OUT=ROOT/"docs"/"warnings"/"observed_coastal_lines.geojson"
TO_METERS=Transformer.from_crs("EPSG:4326","EPSG:3006",always_xy=True).transform

def main():
    boundary=json.loads(BOUNDARY.read_text(encoding="utf-8"))
    assert boundary.get("type")=="FeatureCollection"
    municipal=unary_union([shape(f["geometry"]) for f in boundary["features"]])
    if municipal.is_empty or not municipal.is_valid:raise RuntimeError("Invalid municipal boundary")
    features=[]
    seen=set()
    for path in sorted(ARCHIVE.glob("*.json")):
        document=json.loads(path.read_text(encoding="utf-8"))
        for warning in document.get("warnings",[]):
            if (warning.get("event") or {}).get("code")!="HIGH_SEALEVEL":continue
            for area in warning.get("warningAreas",[]):
                feature=area.get("area") or {}
                geo=feature.get("geometry")
                if not geo:continue
                geom=shape(geo)
                if geom.geom_type not in ("LineString","MultiLineString"):continue
                if not geom.intersects(municipal):continue
                key=hashlib.sha256(json.dumps(geo,sort_keys=True).encode()).hexdigest()
                if key in seen:continue
                seen.add(key)
                clipped=geom.intersection(municipal)
                if clipped.is_empty:continue
                line_parts=[clipped] if clipped.geom_type in ("LineString","MultiLineString") else [g for g in getattr(clipped,"geoms",[]) if g.geom_type in ("LineString","MultiLineString")]
                line_parts=[g for g in line_parts if not g.is_empty and g.length>0]
                if not line_parts:continue
                line=unary_union(line_parts)
                features.append({"type":"Feature","geometry":mapping(line),"properties":{
                    "snapshot_first_seen":document.get("fetched_utc"),
                    "source_event":"HIGH_SEALEVEL",
                    "source_snapshot":path.name,
                    "length_within_working_boundary_km":round(transform(TO_METERS,line).length/1000,3),
                    "geometry_hash":key,
                    "completeness":"partial_observed_only"}})
    output={"type":"FeatureCollection","name":"SMHI observed high-sea-level coastal warnings (incomplete)",
      "properties":{"source":"SMHI warning API snapshots","crs":"EPSG:4326","length_crs":"EPSG:3006",
        "method":"Observed clipped LineString geometries, deduplicated by exact geometry",
        "denominator_available":False,"coast_share_percent":None,
        "warning":"This is NOT a complete SMHI coastline. Do not add lengths of overlapping features or interpret coverage as a coastal percentage."},
      "features":features}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Observed coastal warning geometries:",len(features))

if __name__=="__main__":main()
