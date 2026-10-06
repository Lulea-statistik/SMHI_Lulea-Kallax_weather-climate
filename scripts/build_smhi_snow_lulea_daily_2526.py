#!/usr/bin/env python3
"""Build daily Lulea snow-depth class series for SMHI season 2025/26 from rendered PNG maps."""

from __future__ import annotations
import io,csv,json,re,tempfile,zipfile,time
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image,ImageDraw
from pyproj import CRS,Transformer
from shapely.geometry import MultiPolygon,shape as shp_shape
from shapely.ops import transform as shp_transform

ROOT=Path(__file__).resolve().parents[1]
FIT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_symmetric.json"
OUTJSON=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_daily_2526.json"
OUTCSV=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_daily_2526.csv"

API="https://www.smhi.se/pd/fodl-klimat/api/snowdepth/season/2526"
BASE="https://www.smhi.se"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
TIMEOUT=90
SS=16
MAX_COLOR_DIST=34.0

PALETTE=[
    ("200+",(129,15,124),200),
    ("150-199",(140,107,177),150),
    ("100-149",(140,150,198),100),
    ("75-99",(56,116,185),75),
    ("50-74",(59,157,220),50),
    ("30-49",(158,208,243),30),
    ("10-29",(222,235,247),10),
    ("3-9",(255,255,255),3),
    ("1-2",(183,209,198),1),
    ("barmark",(113,165,143),0),
]

def dl(url, binary=True):
    last=None
    for attempt in range(5):
        try:
            r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-snow-season/1.0"})
            r.raise_for_status()
            return r.content if binary else r.text
        except requests.RequestException as exc:
            last=exc
            if attempt<4: time.sleep(5*(attempt+1))
    raise RuntimeError(f"Download failed: {url}: {last}")

def expand(td):
    root=Path(td)
    with zipfile.ZipFile(io.BytesIO(dl(SCB))) as z:z.extractall(root)
    for zp in list(root.rglob("*.zip")):
        d=zp.parent/(zp.stem+"_expanded"); d.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zp) as z:z.extractall(d)
        except zipfile.BadZipFile:pass
    return root

def parse_depth_urls(payload):
    depths=payload.get("depths",[])
    out=[]
    for item in depths:
        if isinstance(item,str):
            url=item
        elif isinstance(item,dict):
            url=item.get("url") or item.get("src") or item.get("image") or item.get("img") or item.get("path")
            if not url:
                # Try first string value containing sno*.png
                vals=[v for v in item.values() if isinstance(v,str) and "sno" in v.lower() and ".png" in v.lower()]
                url=vals[0] if vals else None
        else:
            url=None
        if not url: continue
        if url.startswith("//"): url="https:"+url
        elif url.startswith("/"): url=BASE+url
        elif not url.startswith("http"):
            if "snow_depth" in url:
                url=BASE + ("" if url.startswith("/") else "/") + url
            else:
                url="https://www.smhi.se/pd/klimat/snow_depth/2526/"+url
        m=re.search(r"sno(\d{6})\.png",url)
        if not m: continue
        yymmdd=m.group(1)
        yy=int(yymmdd[:2]); year=2000+yy
        date=f"{year:04d}-{yymmdd[2:4]}-{yymmdd[4:6]}"
        out.append((date,url))
    # unique and chronological
    return sorted(dict(out).items())

def main():
    fitdata=json.loads(FIT.read_text(encoding="utf-8"))
    fit=next(r for r in fitdata["results"] if r["crs"]=="EPSG:3013")
    p=fit["params"]; sc=float(p["scale"]); ox=float(p["ox"]); oy=float(p["oy"])
    metres_per_pixel=1.0/sc

    payload=requests.get(API,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-snow-season/1.0"}).json()
    images=parse_depth_urls(payload)
    if not images:
        raise RuntimeError(f"No depth images parsed. API keys={list(payload.keys())}, depths sample={payload.get('depths',[])[:3]}")
    print(f"Found {len(images)} depth images, {images[0][0]}..{images[-1][0]}")

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Kommun_Sweref99TM.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        fields=[f[0] for f in sf.fields[1:]]
        target=None
        for sr in sf.iterShapeRecords():
            rec=dict(zip(fields,list(sr.record)))
            code=str(rec.get("KnKod") or rec.get("knkod") or rec.get("KNKOD") or "").strip()
            name=str(rec.get("KnNamn") or rec.get("knnamn") or rec.get("KNNAMN") or "").strip()
            if code=="2580" or name.lower()=="luleå":
                target=sr.shape; break
        if target is None: raise RuntimeError("Lulea municipality not found")

        geom_src=shp_shape(target.__geo_interface__)
        tr_3013=Transformer.from_crs(src,"EPSG:3013",always_xy=True).transform
        geom3013=shp_transform(tr_3013,geom_src)
        def to_px(x,y,z=None): return (sc*x+ox,-sc*y+oy)
        geom_px=shp_transform(to_px,geom3013)

        # Build fractional coverage once for all daily maps.
        first=Image.open(io.BytesIO(dl(images[0][1]))).convert("RGBA")
        w,h=first.size
        hi=Image.new("L",(w*SS,h*SS),0)
        hd=ImageDraw.Draw(hi)
        polys=list(geom_px.geoms) if isinstance(geom_px,MultiPolygon) else [geom_px]
        for poly in polys:
            hd.polygon([(float(x)*SS,float(y)*SS) for x,y in poly.exterior.coords],fill=255)
            for hole in poly.interiors:
                hd.polygon([(float(x)*SS,float(y)*SS) for x,y in hole.coords],fill=0)
        cov=(np.asarray(hi,dtype=float)/255.0).reshape(h,SS,w,SS).mean(axis=(1,3))
        mask=cov>0
        weights=cov[mask]
        palette=np.array([x[1] for x in PALETTE],dtype=float)
        total_weight=float(weights.sum())

        rows=[]
        failures=[]
        for idx,(date,url) in enumerate(images,1):
            try:
                im=Image.open(io.BytesIO(dl(url))).convert("RGBA")
                if im.size!=(w,h): raise RuntimeError(f"Unexpected image size {im.size}")
                arr=np.asarray(im)
                flat=arr[:,:,:3].astype(float)[mask]
                dists=np.sqrt(((flat[:,None,:]-palette[None,:,:])**2).sum(axis=2))
                nearest=dists.argmin(axis=1)
                mind=dists.min(axis=1)
                accepted=mind<=MAX_COLOR_DIST
                classified_weight=float(weights[accepted].sum())
                row={
                    "date":date,
                    "image_url":url,
                    "classified_area_share_pct":round(100*classified_weight/total_weight,3) if total_weight else None,
                }
                for i,(label,color,lower) in enumerate(PALETTE):
                    sel=(nearest==i)&accepted
                    wt=float(weights[sel].sum())
                    key="share_"+label.replace("+","plus").replace("-","_").replace(" ","_")
                    row[key]=round(100*wt/classified_weight,3) if classified_weight else None
                rows.append(row)
                if idx%25==0 or idx==len(images): print(f"Processed {idx}/{len(images)}")
            except Exception as exc:
                failures.append({"date":date,"url":url,"error":str(exc)})
                print(f"FAILED {date}: {exc}")

        if not rows: raise RuntimeError("No daily maps processed successfully")

        area_km2=total_weight*(metres_per_pixel**2)/1e6
        report={
            "season":"2025/26",
            "api":API,
            "map_fit_crs":"EPSG:3013",
            "map_fit_objective":fit["objective"],
            "metres_per_pixel_approx":round(metres_per_pixel,2),
            "supersampling_factor":SS,
            "fractional_mask_area_km2":round(area_km2,3),
            "image_count_api":len(images),
            "processed_days":len(rows),
            "failed_days":len(failures),
            "failures":failures,
            "palette_source":"SMHI snow-depth app legend",
            "max_rgb_distance":MAX_COLOR_DIST,
            "warning":"Derived from rendered SMHI PNG maps; classes are display legend categories, not original numeric raster values.",
            "daily":rows
        }
        OUTJSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        with OUTCSV.open("w",newline="",encoding="utf-8-sig") as fh:
            writer=csv.DictWriter(fh,fieldnames=list(rows[0].keys()),delimiter=";")
            writer.writeheader(); writer.writerows(rows)
        print(json.dumps({k:report[k] for k in ["season","image_count_api","processed_days","failed_days","fractional_mask_area_km2"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
