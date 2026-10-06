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
OUT_ROOT = ROOT / "docs" / "snowgrid"
BOUNDARY_PATH = ROOT / "docs" / "snowmap_boundary.geojson"
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


def month_url(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    name = (
        f"snd_NORDIC-3_SMHI-UERRA-Harmonie_RegRean_v1_Gridpp_v1.0.1_day_"
        f"{year:04d}{month:02d}01-{year:04d}{month:02d}{last:02d}.nc"
    )
    return f"{BASE}/{name}"


def open_snd(url: str):
    """Download the monthly NetCDF robustly, then open it locally.

    SMHI's large NetCDF responses can occasionally close mid-transfer. A full
    local file is more reliable than GDAL /vsicurl for these monthly archives.
    """
    last_error = None
    for attempt in range(1, 6):
        tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
        path = tmp.name
        tmp.close()
        try:
            print(f"Downloading NetCDF attempt {attempt}/5")
            with SESSION.get(url, timeout=(30, TIMEOUT), stream=True) as r:
                r.raise_for_status()
                expected = int(r.headers.get("Content-Length") or 0)
                written = 0
                with open(path, "wb") as out:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        out.write(chunk)
                        written += len(chunk)
                if expected and written != expected:
                    raise IOError(f"Incomplete download: {written} of {expected} bytes")
            ds = rasterio.open(f'NETCDF:"{path}":snd')
            return ds, path
        except Exception as exc:
            last_error = exc
            print(f"Download/open attempt {attempt} failed: {exc}")
            try:
                os.unlink(path)
            except OSError:
                pass
            if attempt < 5:
                import time
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not download/open GridClim NetCDF after 5 attempts: {last_error}")


def iso_dates(year: int, month: int):
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, d).isoformat() for d in range(1, last + 1)]


def cell_polygon(ds, row: int, col: int):
    t = ds.transform
    x0, y0 = t * (col, row)
    x1, y1 = t * (col + 1, row + 1)
    return Polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)])


def process_month(year: int, month: int, municipality_wgs84, grid_geom=None):
    url = month_url(year, month)
    print(f"Snow grid {year}-{month:02d}: {url}")
    ds, tmp_path = open_snd(url)
    try:
        if ds.crs is None:
            raise RuntimeError("GridClim NetCDF lacks a readable CRS")
        to_grid = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform
        to_wgs = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True).transform
        municipality_grid = transform(to_grid, municipality_wgs84)
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
                cells.append((rr,cc,transform(to_wgs, clipped)))

        dates = iso_dates(year,month)
        count = min(ds.count,len(dates))
        rows = []
        for b in range(1,count+1):
            arr = ds.read(b, window=win, masked=True)
            vals = []
            for rr,cc,_ in cells:
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
                    {"type":"Feature","id":i,"properties":{"cell_id":i},"geometry":mapping(g)}
                    for i,(_,_,g) in enumerate(cells)
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


def main():
    OUT_ROOT.mkdir(parents=True,exist_ok=True)
    municipality=load_municipality()

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

    for start_year in range(START_YEAR,END_YEAR+1):
        if start_year+1>2018:
            continue
        season=f"{start_year}-{str(start_year+1)[-2:]}"
        days=[]
        grid=None
        for year,month in season_months(start_year):
            rows,grid=process_month(year,month,municipality,grid)
            days.extend(rows)
        days.sort(key=lambda x:x["date"])
        if not days or grid is None:
            continue

        grid_file=f"{season}_grid.geojson"
        data_file=f"{season}.json"
        (OUT_ROOT/grid_file).write_text(json.dumps(grid,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        payload={
            "season":season,
            "source":"SMHIGridClim",
            "resolution_km":2.5,
            "grid_file":grid_file,
            "days":days,
            "daily":summarize(days),
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
        print(f"Snow grid {season}: {len(days)} dates, {len(grid.get('features',[]))} Lulea cells")

    index["seasons"]=sorted(by_season.values(),key=lambda x:x["season"])
    existing_index.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
