"""Read-only release checks; warnings are not proof of missing observations."""
import csv
import json
import math
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
errors, warnings = [], []
def check(ok, message):
    if not ok:
        errors.append(message)

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.pages = []
        self.stack = []
        self.structural = {'html','head','body','main','section','div','nav','header','footer'}
        self.main_count = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'main': self.main_count += 1
        if tag in self.structural: self.stack.append(tag)
        if a.get("id"): self.ids.append(a["id"])
        if a.get("data-page"): self.pages.append(a["data-page"])
        if tag in ("script", "link", "img", "a"):
            url = a.get("src") or a.get("href")
            if url: self.links.append(url)

    def handle_endtag(self, tag):
        if tag not in self.structural: return
        if not self.stack or self.stack[-1] != tag:
            errors.append('Unexpected structural end tag: ' + tag)
        else: self.stack.pop()

page = Page()
page.feed((DOCS / "index.html").read_text(encoding="utf-8"))
check(page.main_count == 1, 'Expected exactly one main element')
check(not page.stack, 'Unclosed structural HTML elements: ' + str(page.stack))
check(len(page.ids) == len(set(page.ids)), "Duplicate HTML IDs")
for p in page.pages:
    check("page-" + p in page.ids, "Missing page: " + p)
for url in page.links:
    if url.startswith(("https:", "http:", "#", "mailto:", "//", "data:")): continue
    check((DOCS / url.split("?")[0].split("#")[0]).exists(), "Missing local resource: " + url)
data = json.loads((DOCS / "dashboard_data.json").read_text(encoding="utf-8"))
for k in ("years", "temperature", "precipitation", "coverage"):
    check(bool(data.get(k)), "Missing or empty dashboard field: " + k)
years = data.get("years", [])
check(years == sorted(set(years)), "Dashboard years unsorted or duplicated")
manifest = list(csv.DictReader((ROOT / "data/manifest.csv").open(encoding="utf-8-sig")))
check(bool(manifest), "Empty manifest")
latest = {}
by_parameter = defaultdict(set)
now = datetime.now(timezone.utc)
for row in manifest:
    p, y = row["parameter_id"], int(row["year"])
    check(y not in by_parameter[p], "Duplicate manifest parameter/year: " + p + "/" + str(y))
    by_parameter[p].add(y)
    path = ROOT / row["path"]
    check(path.is_file(), "Missing manifest file: " + row["path"])
    check(int(row["row_count"]) > 0, "Empty manifest entry: " + row["path"])
    a = datetime.fromisoformat(row["min_datetime_utc"].replace("Z","+00:00"))
    b = datetime.fromisoformat(row["max_datetime_utc"].replace("Z","+00:00"))
    check(a <= b, "Reversed time range: " + row["path"])
    check(b <= now.replace(microsecond=0) or (b-now).total_seconds()<86400, "Future observations: " + row["path"])
    if p not in latest or b > latest[p][0]: latest[p] = (b,path)
for p, ys in by_parameter.items():
    gaps = sorted(set(range(min(ys),max(ys)+1))-ys)
    if gaps: warnings.append(f"Parameter {p}: missing years {gaps}")
# Broad screening limits, not official SMHI quality thresholds. Raw units verified
# from each CSV before applying a range. Only latest manifest file per parameter.
limits = {"1":(-80,60), "5":(0,500), "6":(0,100), "8":(0,15)}
units = {"1":{"celsius","°c","degree celsius","grader celsius"}, "5":{"millimeter","mm"}, "6":{"procent","%","percent"}, "8":{"meter","m"}}
for p,(date,path) in latest.items():
    age=(now-date).days
    if p in {"1","5","6"} and age>7: warnings.append(f"Parameter {p}: latest observation {age} days old")
    if p not in limits or not path.exists(): continue
    count=0
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw=row.get("value_numeric","")
            if not raw: continue
            if row.get("unit","").strip().lower() not in units[p]:
                warnings.append(f"Parameter {p}: unknown unit {row.get('unit')}; screening skipped")
                break
            try: v=float(raw)
            except ValueError: errors.append(f"Non-numeric value in {path.name}"); continue
            if not math.isfinite(v) or not limits[p][0]<=v<=limits[p][1]: count+=1
        if count: warnings.append(f"Parameter {p}: {count} values outside screening range")
for k, field in (("temperature","avg"),("precipitation","sum")):
    section=data.get(k,{})
    monthly=section.get("monthly",section.get("monthly_total",[]))
    periods=defaultdict(set)
    for row in monthly:
        if row.get(field) is not None: periods[row["year"]].add(row["month"])
    for row in section.get("annual",[]):
        if len(periods.get(row["year"],set()))!=12:
            warnings.append(f"{k}: annual value {row['year']} without twelve monthly values")
for w in warnings: print("WARNING:",w)
for e in errors: print("ERROR:",e)
print(f"{len(errors)} errors; {len(warnings)} warnings")
raise SystemExit(bool(errors))
