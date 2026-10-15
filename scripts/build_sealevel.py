#!/usr/bin/env python3
"""Build transparent Strömören sea-level summaries from original SMHI semicolon CSV."""
import csv
import datetime as dt
import io
import json
import pathlib
from collections import defaultdict

BASE = pathlib.Path(__file__).resolve().parents[1]
SOURCE = BASE / "data/sealevel/stromoren"
DEST = BASE / "docs/sealevel"
CUTOFF = dt.datetime(2019, 7, 1)
VALID = {"G", "Y", "O"}
def read_file(path):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith("Datum Tid (UTC);")), None)
    if first is None:
        raise ValueError(f"No observations header in {path}")
    reader = csv.reader(lines[first+1:], delimiter=";")
    out=[]
    for row in reader:
        if len(row)<3 or not row[0].strip():continue
        try:
            t=dt.datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
            value=float(row[1].replace(",","."))
        except (ValueError,IndexError):
            continue
        quality=row[2].strip().upper()
        if quality not in VALID:continue
        out.append((t,value,quality))
    return out
def stats(records):
    if not records:return None
    values=[r[1] for r in records]
    low=min(records,key=lambda r:r[1]);high=max(records,key=lambda r:r[1])
    return {"count":len(records),"mean_cm":round(sum(values)/len(values),2),
            "min_cm":low[1],"max_cm":high[1],
            "min_utc":low[0].isoformat()+"Z","max_utc":high[0].isoformat()+"Z"}
def main():
    archives=SOURCE/"corrected-archive.csv"
    if not archives.exists():raise SystemExit("Missing archive; run bootstrap first")
    records={}
    for name in ("corrected-archive.csv","latest-day.csv"):
        path=SOURCE/name
        if not path.exists():continue
        for t,v,q in read_file(path):
            # Use newer latest-day in overlapping hours.
            records[t]=(t,v,q)
    all_rows=[records[k] for k in sorted(records)]
    if not all_rows:raise SystemExit("No valid records parsed")
    # G-only primary statistics, with unverified pre-2019 explicitly flagged separately.
    usable=[r for r in all_rows if r[2]=="G"]
    daily=defaultdict(list);annual=defaultdict(list);monthly=defaultdict(list)
    for r in usable:
        daily[r[0].strftime("%Y-%m-%d")].append(r)
        annual[r[0].year].append(r)
        monthly[r[0].strftime("%Y-%m")].append(r)
    result={"station":"Strömören","station_id":"35183","parameter":6,"unit":"cm","reference":"RH 2000",
            "time_basis":"UTC","quality_policy":"Only G observations used in statistics; data before 2019-07-01 lack equivalent quality control",
            "quality_counts":{q:sum(r[2]==q for r in all_rows) for q in VALID},
            "pre_2019_count":sum(r[0]<CUTOFF for r in usable),
            "coverage":{"first":all_rows[0][0].isoformat()+"Z","last":all_rows[-1][0].isoformat()+"Z","total_unique_hours":len(all_rows),"approved_hours":len(usable)},
            "all_time":stats(usable),
            "annual":[{"year":k,**stats(v)} for k,v in sorted(annual.items())],
            "monthly":[{"month":k,**stats(v)} for k,v in sorted(monthly.items())],
            "daily":[{"day":k,**stats(v)} for k,v in sorted(daily.items())]}
    DEST.mkdir(parents=True,exist_ok=True)
    (DEST/"stromoren.json").write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(f"Created sealevel summaries: {len(all_rows)} unique timestamps; {len(usable)} G records; {len(daily)} days")
if __name__=="__main__":main()
