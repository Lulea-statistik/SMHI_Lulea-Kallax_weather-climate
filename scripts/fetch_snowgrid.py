#!/usr/bin/env python3
"""Build a 2.5 km analysed snow-depth layer for Lulea from SMHIGridClim.

The source is SMHIGridClim daily snow depth (snd), 1961-2018. To keep GitHub
Pages light, only grid cells intersecting Lulea municipality are retained.
"""

from __future__ import annotations

import calendar
import json
import math
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from shapely.geometry import shape, mapping, Polygon
from shapely.ops import transform, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
NMD_GEO_PATH = ROOT / "data" / "lightning" / "geography_nmd.geojson"
LIGHTNING_GEO_PATH = ROOT / "data" / "lightning" / "geography.geojson"
OUT_ROOT = ROOT / "docs" / "snowgrid"
BOUNDARY_PATH = ROOT / "docs" / "snowmap_boundary.geojson"
SERIES_PATH = OUT_ROOT / "series.json"
BASE = "https://opendata-download-metanalys.smhi.se/gridclim/snd"
TIMEOUT = 180

START_YEAR = int(os.getenv("SNOWGRID_START_YEAR", "2017"))
END_YEAR = int(os.getenv("SNOWGRID_END_YEAR", str(START_YEAR)))

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Lulea-statistik-SMHI-snowgrid/1.0"})
_retry = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "HEAD"]),
)
SESSION.mount("https://", HTTPAdapter(max_retries=_retry))


def load_municipality():
    data = json.loads(NMD_GEO_PATH.read_text(encoding="utf-8"))
    geoms = []
    for feat in data.get("features", []):
        try:
            g = shape(feat["geometry"]).buffer(0)
        except Exception:
            continue
        if not g.is_empty:
            geoms.append(g)
    if not geoms:
        raise RuntimeError("Lulea municipality geometry is missing")
    return unary_union(geoms).buffer(0)


def load_mainland_geometry():
    """Use the same mainland classification already produced for the lightning page."""
    if not LIGHTNING_GEO_PATH.exists():
        return None
    data = json.loads(LIGHTNING_GEO_PATH.read_text(encoding="utf-8"))
    geoms = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        if props.get("class") != "mainland" or not feat.get("geometry"):
            continue
        try:
            g = shape(feat["geometry"]).buffer(0)
        except Exception:
            continue
        if not g.is_empty:
            geoms.append(g)
    return unary_union(geoms).buffer(0) if geoms else None


def month_url(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    name = (
        f"snd_NORDIC-3_SMHI-UERRA-Harmonie_RegRean_v1_Gridpp_v1.0.1_day_"
        f"{year:04d}{month:02d}01-{year:04d}{month:02d}{last:02d}.nc"
    )
    return f"{BASE}/{name}"


def open_snd(url: str):
    """Download a monthly NetCDF with resumable HTTP Range requests.

    SMHI's server sometimes closes large transfers early. Keep the partial file
    and request the remaining byte range instead of restarting from byte zero.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
    path = tmp.name
    tmp.close()

    try:
        # Discover the expected size. If HEAD is unavailable, the first GET
        # will populate it from Content-Length / Content-Range.
        expected = 0
        try:
            h = SESSION.head(url, timeout=(30, 60), allow_redirects=True)
            if h.ok:
                expected = int(h.headers.get("Content-Length") or 0)
        except Exception as exc:
            print(f"HEAD warning: {exc}")

        max_attempts = 30
        for attempt in range(1, max_attempts + 1):
            current = os.path.getsize(path) if os.path.exists(path) else 0
            if expected and current >= expected:
                break

            headers = {}
            mode = "wb"
            if current > 0:
                headers["Range"] = f"bytes={current}-"
                mode = "ab"

            print(
                f"Downloading NetCDF chunk attempt {attempt}/{max_attempts}"
                + (f" from byte {current}" if current else "")
            )

            try:
                with SESSION.get(
                    url,
                    headers=headers,
                    timeout=(30, TIMEOUT),
                    stream=True,
                    allow_redirects=True,
                ) as r:
                    r.raise_for_status()

                    # A server that ignores Range returns 200. In that case
                    # restart the local file to avoid duplicating bytes.
                    if current > 0 and r.status_code != 206:
                        print("Server ignored Range request; restarting local file.")
                        current = 0
                        mode = "wb"

                    content_range = r.headers.get("Content-Range") or ""
                    if "/" in content_range:
                        try:
                            expected = int(content_range.rsplit("/", 1)[1])
                        except Exception:
                            pass
                    elif not expected:
                        length = int(r.headers.get("Content-Length") or 0)
                        if length:
                            expected = current + length if r.status_code == 206 else length

                    with open(path, mode) as out:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                out.write(chunk)

            except Exception as exc:
                size = os.path.getsize(path) if os.path.exists(path) else 0
                print(f"Chunk attempt {attempt} interrupted at {size} bytes: {exc}")
                if attempt < max_attempts:
                    import time
                    time.sleep(min(30, 1 + attempt))
                continue

            size = os.path.getsize(path)
            print(f"Downloaded {size}" + (f" of {expected} bytes" if expected else " bytes"))
            if expected and size >= expected:
                break

        final_size = os.path.getsize(path) if os.path.exists(path) else 0
        if expected and final_size < expected:
            raise RuntimeError(
                f"Incomplete GridClim download after {max_attempts} resumptions: "
                f"{final_size} of {expected} bytes"
            )
        if final_size == 0:
            raise RuntimeError("GridClim download produced an empty file")

        ds = rasterio.open(f'NETCDF:"{path}":snd')
        return ds, path

    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def iso_dates(year: int, month: int):
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, d).isoformat() for d in range(1, last + 1)]


def cell_polygon(ds, row: int, col: int):
    t = ds.transform
    x0, y0 = t * (col, row)
    x1, y1 = t * (col + 1, row + 1)
    return Polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)])


def process_month(year: int, month: int, municipality_wgs84, mainland_wgs84=None, grid_geom=None):
    url = month_url(year, month)
    print(f"Snow grid {year}-{month:02d}: {url}")
    ds, tmp_path = open_snd(url)
    try:
        if ds.crs is None:
            raise RuntimeError("GridClim NetCDF lacks a readable CRS")
        to_grid = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform
        to_wgs = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True).transform
        municipality_grid = transform(to_grid, municipality_wgs84)
        mainland_grid = transform(to_grid, mainland_wgs84) if mainland_wgs84 is not None else None
        minx,miny,maxx,maxy = municipality_grid.bounds
        win = from_bounds(minx,miny,maxx,maxy,transform=ds.transform)
        win = win.round_offsets().round_lengths()
        row0,col0 = int(win.row_off),int(win.col_off)
        h,w = int(win.height),int(win.width)

        shapes = []
        cells = []
        for r in range(h):
            for c in range(w):
                rr,cc = row0+r,col0+c
                poly = cell_polygon(ds,rr,cc)
                if not poly.intersects(municipality_grid):
                    continue
                clipped = poly.intersection(municipality_grid)
                if clipped.is_empty:
                    continue
                touches_mainland = bool(mainland_grid is not None and clipped.intersects(mainland_grid))
                mainland_share_pct = 0.0
                if mainland_grid is not None and clipped.area > 0:
                    mainland_part = clipped.intersection(mainland_grid)
                    mainland_share_pct = max(0.0, min(100.0, 100.0 * mainland_part.area / clipped.area))
                mainland_majority = mainland_share_pct >= 50.0
                cells.append((rr,cc,transform(to_wgs, clipped),touches_mainland,mainland_share_pct,mainland_majority))

        dates = iso_dates(year,month)
        count = min(ds.count,len(dates))
        rows = []
        for b in range(1,count+1):
            arr = ds.read(b, window=win, masked=True)
            vals = []
            for rr,cc,_,_,_,_ in cells:
                local_r,local_c = rr-row0,cc-col0
                if local_r<0 or local_c<0 or local_r>=arr.shape[0] or local_c>=arr.shape[1]:
                    vals.append(None)
                    continue
                v = arr[local_r,local_c]
                if getattr(v,"mask",False):
                    vals.append(None)
                else:
                    fv = float(v)
                    if not math.isfinite(fv) or fv < 0:
                        vals.append(None)
                    else:
                        vals.append(round(fv*100,1))
            rows.append({"date":dates[b-1],"values_cm":vals})

        if grid_geom is None:
            grid_geom = {
                "type":"FeatureCollection",
                "features":[
                    {"type":"Feature","id":i,"properties":{
                        "cell_id":i,
                        "touches_mainland":bool(touch),
                        "mainland_share_pct":round(float(share),1),
                        "mainland_majority":bool(majority)
                    },"geometry":mapping(g)}
                    for i,(_,_,g,touch,share,majority) in enumerate(cells)
                ]
            }
        return rows,grid_geom
    finally:
        ds.close()
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def season_months(start_year: int):
    out=[]
    for m in range(8,13):
        out.append((start_year,m))
    for m in range(1,8):
        out.append((start_year+1,m))
    return out


def summarize(days):
    summary=[]
    for d in days:
        vals=[v for v in d["values_cm"] if v is not None]
        summary.append({
            "date":d["date"],
            "mean_cm":round(sum(vals)/len(vals),1) if vals else None,
            "max_cm":round(max(vals),1) if vals else None,
            "snow_cover_share_pct":round(100*sum(v>=1 for v in vals)/len(vals),1) if vals else None,
            "cells":len(vals),
        })
    return summary


SNOW_WEEK_CLASSES = [
    ("0–4 veckor", 0, 4),
    ("5–8 veckor", 5, 8),
    ("9–12 veckor", 9, 12),
    ("13–16 veckor", 13, 16),
    ("17–20 veckor", 17, 20),
    ("21–24 veckor", 21, 24),
    ("25+ veckor", 25, None),
]


def season_cell_stats(days, grid):
    features = grid.get("features", [])
    n_cells = len(features)
    snow_days = [0] * n_cells
    valid_days = [0] * n_cells
    mainland_ids = {
        int((f.get("properties") or {}).get("cell_id", f.get("id", -1)))
        for f in features
        if (f.get("properties") or {}).get("mainland_majority")
    }

    daily_mainland = []
    daily_depth_classes = []
    depth_classes = [
        ("Barmark", lambda v: v < 1),
        ("1–2 cm", lambda v: 1 <= v < 3),
        ("3–9 cm", lambda v: 3 <= v < 10),
        ("10–29 cm", lambda v: 10 <= v < 30),
        ("30–49 cm", lambda v: 30 <= v < 50),
        ("50–74 cm", lambda v: 50 <= v < 75),
        ("75–99 cm", lambda v: 75 <= v < 100),
        ("100–149 cm", lambda v: 100 <= v < 150),
        ("150–199 cm", lambda v: 150 <= v < 200),
        ("200+ cm", lambda v: v >= 200),
    ]
    for d in days:
        vals = d.get("values_cm") or []
        mainland_vals = []
        for i, v in enumerate(vals[:n_cells]):
            if v is None:
                continue
            valid_days[i] += 1
            if v >= 1:
                snow_days[i] += 1
            if i in mainland_ids:
                mainland_vals.append(v)
        daily_mainland.append({
            "date": d["date"],
            "snow_cover_share_pct": round(
                100 * sum(v >= 1 for v in mainland_vals) / len(mainland_vals), 1
            ) if mainland_vals else None,
            "cells": len(mainland_vals),
        })
        valid_vals = [float(v) for v in vals[:n_cells] if v is not None]
        counts = {label: sum(test(v) for v in valid_vals) for label, test in depth_classes}
        total_valid = len(valid_vals)
        daily_depth_classes.append({
            "date": d["date"],
            "cells": total_valid,
            "class_pct": {
                label: round(100.0 * count / total_valid, 2) if total_valid else 0.0
                for label, count in counts.items()
            },
        })

    class_counts = {label: 0 for label, _, _ in SNOW_WEEK_CLASSES}
    for i in range(n_cells):
        if not valid_days[i]:
            continue
        weeks = snow_days[i] / 7.0
        for label, lo, hi in SNOW_WEEK_CLASSES:
            if weeks >= lo and (hi is None or weeks <= hi):
                class_counts[label] += 1
                break

    classified = sum(class_counts.values())
    class_pct = {
        label: round(100 * count / classified, 2) if classified else 0.0
        for label, count in class_counts.items()
    }
    return {
        "snow_duration_pct": class_pct,
        "snow_duration_counts": class_counts,
        "classified_cells": classified,
        "mainland_majority_cells": len(mainland_ids),
        "daily_mainland_majority": daily_mainland,
        "daily_depth_class_pct": daily_depth_classes,
    }


def main():
    OUT_ROOT.mkdir(parents=True,exist_ok=True)
    municipality=load_municipality()
    mainland=load_mainland_geometry()

    # Keep the same boundary file used by the station map.
    if not BOUNDARY_PATH.exists():
        BOUNDARY_PATH.write_text(
            json.dumps({"type":"FeatureCollection","features":[
                {"type":"Feature","properties":{"name":"Lulea kommun"},"geometry":mapping(municipality)}
            ]},ensure_ascii=False,separators=(",",":")),
            encoding="utf-8",
        )

    index={
        "source":"SMHIGridClim (UERRA-Harmonie / GridPP)",
        "source_url":"https://www.smhi.se/data/sok-oppna-data-i-utforskaren/meteorologisk-ateranalys-smhigridclim-uerra-harmonie",
        "resolution_km":2.5,
        "available_period":"1961-01-01–2018-12-31",
        "seasons":[],
    }
    existing_index=OUT_ROOT/"index.json"
    if existing_index.exists():
        try:
            old=json.loads(existing_index.read_text(encoding="utf-8"))
            index["seasons"]=old.get("seasons",[])
        except Exception:
            pass

    by_season={x["season"]:x for x in index["seasons"] if x.get("season")}

    series_by_season={}
    if SERIES_PATH.exists():
        try:
            old_series=json.loads(SERIES_PATH.read_text(encoding="utf-8"))
            series_by_season={x["season"]:x for x in old_series.get("seasons",[]) if x.get("season")}
        except Exception:
            series_by_season={}
    elif index["seasons"]:
        # One-time migration: build the lightweight chart series from already
        # generated season files without re-downloading GridClim.
        for meta in index["seasons"]:
            p=OUT_ROOT/meta.get("file","")
            if not p.exists():
                continue
            try:
                old_payload=json.loads(p.read_text(encoding="utf-8"))
                series_by_season[meta["season"]]={
                    "season":meta["season"],
                    "daily":old_payload.get("daily",[]),
                    "daily_mainland_majority":old_payload.get("daily_mainland_majority",old_payload.get("daily_mainland",[])),
                    "snow_duration_pct":old_payload.get("snow_duration_pct",{}),
                    "classified_cells":old_payload.get("classified_cells"),
                    "mainland_majority_cells":old_payload.get("mainland_majority_cells",old_payload.get("mainland_touching_cells")),
                }
            except Exception as exc:
                print(f"Series migration warning for {p}: {exc}")

    for start_year in range(START_YEAR,END_YEAR+1):
        if start_year+1>2018:
            continue
        season=f"{start_year}-{str(start_year+1)[-2:]}"
        days=[]
        grid=None
        for year,month in season_months(start_year):
            rows,grid=process_month(year,month,municipality,mainland,grid)
            days.extend(rows)
        days.sort(key=lambda x:x["date"])
        if not days or grid is None:
            continue

        grid_file=f"{season}_grid.geojson"
        data_file=f"{season}.json"
        (OUT_ROOT/grid_file).write_text(json.dumps(grid,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        stats=season_cell_stats(days,grid)
        payload={
            "season":season,
            "source":"SMHIGridClim",
            "resolution_km":2.5,
            "grid_file":grid_file,
            "days":days,
            "daily":summarize(days),
            "daily_mainland_majority":stats["daily_mainland_majority"],
            "daily_depth_class_pct":stats["daily_depth_class_pct"],
            "snow_duration_pct":stats["snow_duration_pct"],
            "snow_duration_counts":stats["snow_duration_counts"],
            "classified_cells":stats["classified_cells"],
            "mainland_majority_cells":stats["mainland_majority_cells"],
        }
        (OUT_ROOT/data_file).write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        by_season[season]={
            "season":season,
            "file":data_file,
            "grid_file":grid_file,
            "first_date":days[0]["date"],
            "last_date":days[-1]["date"],
            "dates":len(days),
            "cells":len(grid.get("features",[])),
        }
        series_by_season[season]={
            "season":season,
            "daily":payload["daily"],
            "daily_mainland_majority":payload["daily_mainland_majority"],
            "daily_depth_class_pct":payload["daily_depth_class_pct"],
            "snow_duration_pct":payload["snow_duration_pct"],
            "classified_cells":payload["classified_cells"],
            "mainland_majority_cells":payload["mainland_majority_cells"],
        }
        print(f"Snow grid {season}: {len(days)} dates, {len(grid.get('features',[]))} Lulea cells")

    index["seasons"]=sorted(by_season.values(),key=lambda x:x["season"])
    existing_index.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding="utf-8")
    series_payload={
        "source":"SMHIGridClim",
        "resolution_km":2.5,
        "seasons":sorted(series_by_season.values(),key=lambda x:x["season"]),
    }
    SERIES_PATH.write_text(json.dumps(series_payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")


if __name__=="__main__":
    main()
