#!/usr/bin/env python3
"""Create a visual Lulea georeference preview on the SMHI snow PNG using the national EPSG:4326 fit."""

from __future__ import annotations
import io, json, tempfile, zipfile
from pathlib import Path
import requests, numpy as np, shapefile
from PIL import Image, ImageDraw
from pyproj import CRS, Transformer

ROOT=Path(__file__).resolve().parents[1]
FIT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_candidates.json"
OUTPNG=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_georef_preview.png"
OUTJSON=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_georef_preview.json"

SNOW="https://www.smhi.se/pd/klimat/snow_depth/2526/sno260215.png"
COUNTY="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-Lulea-georef/1.0"})
    r.raise_for_status()
    return r.content

def expand(td):
    root=Path(td)
    with zipfile.ZipFile(io.BytesIO(dl(SCB))) as z:
        z.extractall(root)
    for zp in list(root.rglob("*.zip")):
        d=zp.parent/(zp.stem+"_expanded")
        d.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zp) as z:
                z.extractall(d)
        except zipfile.BadZipFile:
            pass
    return root

def project_ring(points,tr,scale,ox,oy):
    xs,ys=zip(*points)
    lon,lat=tr.transform(xs,ys)
    return [(scale*x+ox, -scale*y+oy) for x,y in zip(lon,lat)]

def main():
    fits=json.loads(FIT.read_text(encoding="utf-8"))["results"]
    fit=next(r for r in fits if r["crs"]=="EPSG:4326")
    p=fit["params"]
    scale=float(p["scale"]); ox=float(p["ox"]); oy=float(p["oy"])

    snow=Image.open(io.BytesIO(dl(SNOW))).convert("RGBA")
    county=Image.open(io.BytesIO(dl(COUNTY))).convert("RGBA")
    if snow.size != county.size:
        raise RuntimeError(f"Image size mismatch: snow={snow.size}, county={county.size}")

    # Composite snow and county-border overlay, then draw official Lulea municipal boundary.
    base=Image.alpha_composite(snow,county)
    draw=ImageDraw.Draw(base)

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Kommun_Sweref99TM.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        tr=Transformer.from_crs(src,"EPSG:4326",always_xy=True)
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        fields=[f[0] for f in sf.fields[1:]]

        target=None
        rec_used=None
        for sr in sf.iterShapeRecords():
            rec=dict(zip(fields,list(sr.record)))
            code=str(rec.get("KnKod") or rec.get("knkod") or rec.get("KNKOD") or "").strip()
            name=str(rec.get("KnNamn") or rec.get("knnamn") or rec.get("KNNAMN") or "").strip()
            if code=="2580" or name.lower()=="luleå":
                target=sr.shape
                rec_used={"code":code,"name":name}
                break
        if target is None:
            raise RuntimeError("Lulea municipality not found in SCB municipality shapefile")

        parts=list(target.parts)+[len(target.points)]
        allpix=[]
        for a,b in zip(parts[:-1],parts[1:]):
            ring=target.points[a:b]
            pix=project_ring(ring,tr,scale,ox,oy)
            allpix.extend(pix)
            if len(pix)>=2:
                # Thick white halo + black line for visibility without assuming thematic colors.
                draw.line(pix+[pix[0]],fill=(255,255,255,255),width=3)
                draw.line(pix+[pix[0]],fill=(0,0,0,255),width=1)

        arr=np.asarray(allpix,float)
        bbox=[float(arr[:,0].min()),float(arr[:,1].min()),float(arr[:,0].max()),float(arr[:,1].max())]
        inside=((arr[:,0]>=0)&(arr[:,0]<snow.size[0])&(arr[:,1]>=0)&(arr[:,1]<snow.size[1]))

        report={
            "source_snow_png":SNOW,
            "source_county_overlay":COUNTY,
            "municipality_source":"SCB Kommun_Sweref99TM.shp",
            "municipality_record":rec_used,
            "municipality_source_crs_wkt_prefix":prj[:500],
            "municipality_source_explicit_epsg3006":'AUTHORITY["EPSG",3006]' in prj,
            "map_fit_crs":"EPSG:4326",
            "map_fit_params":p,
            "image_size":list(snow.size),
            "lulea_pixel_bbox":[round(x,3) for x in bbox],
            "lulea_vertices_inside_image_pct":round(float(inside.mean()*100),2),
            "note":"Preview only. Black/white outline is SCB Lulea municipality transformed from verified SWEREF 99 TM to EPSG:4326, then through the national SMHI PNG fit."
        }
        base.save(OUTPNG)
        OUTJSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
