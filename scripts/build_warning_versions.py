#!/usr/bin/env python3
"""Track observed versions of SMHI warning areas from archived Lulea snapshots.
A change is an observed difference between polls, not necessarily an SMHI issuance.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"docs/warnings/history.json"
CURRENT=ROOT/"docs/warnings/current.json"
OUT=ROOT/"docs/warnings/versions.json"

def stable_hash(record):
    values={k:record.get(k) for k in ("event_code","level_code","start","end","title","geometry","geography_kind")}
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def key(row):
    return str(row.get("id") or "")+":"+str(row.get("area_id") or "")

def main():
    history=json.loads(HISTORY.read_text(encoding="utf-8"))
    if not isinstance(history,list):raise RuntimeError("Unexpected history format")
    # Older snapshots are read-only and may contain unclipped geometry. Use the
    # saved current.json only for the newest state; source snapshots themselves
    # preserve historical originals. Rebuild from raw snapshots when possible.
    from shapely.geometry import shape,mapping
    boundary=json.loads((ROOT/"docs/snowmap_boundary.geojson").read_text(encoding="utf-8"))
    land=shape(boundary["features"][0]["geometry"])
    observations=[]
    for h in sorted(history,key=lambda r:r["fetched_utc"]):
        file=ROOT/"data/warning_snapshots"/h["snapshot"]
        if not file.exists():continue
        payload=json.loads(file.read_text(encoding="utf-8"))
        states={}
        for warning in payload.get("warnings",[]):
            for area in warning.get("warningAreas",[]):
                geo=(area.get("area") or {}).get("geometry")
                if not geo:continue
                geom=shape(geo)
                if geom.is_empty or not geom.intersects(land):continue
                clipped=geom.intersection(land)
                if clipped.is_empty:continue
                record={"id":str(warning.get("id") or ""),"area_id":str(area.get("id") or ""),
                    "event_code":(warning.get("event") or {}).get("code"),
                    "level_code":(area.get("warningLevel") or {}).get("code"),
                    "title":(area.get("eventDescription") or {}).get("sv"),
                    "start":area.get("approximateStart"),"end":area.get("approximateEnd"),
                    "geography_kind":geom.geom_type,"geometry":mapping(clipped)}
                record["geometry_sha256"]=hashlib.sha256(json.dumps(record["geometry"],sort_keys=True).encode()).hexdigest()
                states[key(record)]=record
        observations.append((h["fetched_utc"],states))
    events=[]
    last={}
    for timestamp,now in observations:
        for ident,record in sorted(now.items()):
            fingerprint=stable_hash(record)
            previous=last.get(ident)
            if previous is None:action="first_observed"
            elif fingerprint!=previous["fingerprint"]:action="changed"
            else:continue
            events.append({"observed_at":timestamp,"key":ident,"action":action,
                "warning_id":record["id"],"area_id":record["area_id"],
                "event_code":record["event_code"],"level_code":record["level_code"],
                "previous_level":previous["record"]["level_code"] if previous else None,
                "geometry_changed":previous is not None and record["geometry_sha256"]!=previous["record"]["geometry_sha256"],
                "version_hash":fingerprint,"geometry":record["geometry"],
                "geography_kind":record["geography_kind"],"start":record["start"],"end":record["end"]})
        for ident,previous in sorted(last.items()):
            if ident not in now:
                events.append({"observed_at":timestamp,"key":ident,"action":"no_longer_observed",
                               "warning_id":previous["record"]["id"],"area_id":previous["record"]["area_id"],
                               "event_code":previous["record"]["event_code"],"level_code":previous["record"]["level_code"]})
        last={ident:{"record":record,"fingerprint":stable_hash(record)} for ident,record in now.items()}
    OUT.write_text(json.dumps({"generated_at":datetime.now().astimezone().isoformat(),
        "snapshots_processed":len(observations),"events":events,
        "caveat":"Only sampled changes; absence from feed does not prove precise warning end time. No event counts are inferred from hourly polls."},
        ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"Tracked {len(events)} observed changes across {len(observations)} snapshots")

if __name__=="__main__":main()
