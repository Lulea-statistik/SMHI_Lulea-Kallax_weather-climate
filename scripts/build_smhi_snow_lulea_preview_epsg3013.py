#!/usr/bin/env python3
"""Build Lulea preview using the best symmetric SMHI snow-map CRS candidate."""

from __future__ import annotations
import io,json,tempfile,zipfile
from pathlib import Path
import requests, shapefile
from PIL import Image,ImageDraw
from pyproj import CRS,Transformer

ROOT=Path(__file__).resolve().parents[1]
FIT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_symmetric.json"
OUTPNG=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_georef_preview_epsg3013.png"
OUTJSON=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_georef_preview_epsg3013.json"

SNOW="https://www.smhi.se/pd/klimat/snow_depth/2526/sno260215.png"
COUNTY="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-Lulea-3013-preview/1.0"})
    r.raise_for_status(); return r.content

def expand(td):
    root=Path(td)
    with zipfile.ZipFile(io.BytesIO(dl(SCB))) as z:z.extractall(root)
    for zp in list(root.rglob("*.zip")):
        d=zp.parent/(zp.stem+"_expanded"); d.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zp) as z:z.extractall(d)
        except zipfile.BadZipFile:pass
    return root

def main():
    fitdata=json.loads(FIT.read_text(encoding="utf-8"))
    fit=next(r for r in fitdata["results"] if r["crs"]=="EPSG:3013")
    p=fit["params"]; sc=float(p["scale"]); ox=float(p["ox"]); oy=float(p["oy"])

    snow=Image.open(io.BytesIO(dl(SNOW))).convert("RGBA")
    county=Image.open(io.BytesIO(dl(COUNTY))).convert("RGBA")
    base=Image.alpha_composite(snow,county)
    draw=ImageDraw.Draw(base)

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Kommun_Sweref99TM.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        tr=Transformer.from_crs(src,"EPSG:3013",always_xy=True)
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        fields=[f[0] for f in sf.fields[1:]]
        target=None; rec_used=None
        for sr in sf.iterShapeRecords():
            rec=dict(zip(fields,list(sr.record)))
            code=str(rec.get("KnKod") or rec.get("knkod") or rec.get("KNKOD") or "").strip()
            name=str(rec.get("KnNamn") or rec.get("knnamn") or rec.get("KNNAMN") or "").strip()
            if code=="2580" or name.lower()=="luleå":
                target=sr.shape; rec_used={"code":code,"name":name}; break
        if target is None: raise RuntimeError("Lulea municipality not found")

        parts=list(target.parts)+[len(target.points)]
        allpix=[]
        for a,b in zip(parts[:-1],parts[1:]):
            ring=target.points[a:b]
            xs,ys=zip(*ring)
            X,Y=tr.transform(xs,ys)
            pix=[(sc*x+ox,-sc*y+oy) for x,y in zip(X,Y)]
            allpix.extend(pix)
            if len(pix)>=2:
                draw.line(pix+[pix[0]],fill=(255,255,255,255),width=3)
                draw.line(pix+[pix[0]],fill=(0,0,0,255),width=1)

        xs=[q[0] for q in allpix]; ys=[q[1] for q in allpix]
        bbox=[min(xs),min(ys),max(xs),max(ys)]
        inside=[0<=x<snow.size[0] and 0<=y<snow.size[1] for x,y in allpix]
        report={
            "map_fit_crs":"EPSG:3013",
            "fit_objective":fit["objective"],
            "fit_forward_median_px":fit["forward_median_px"],
            "fit_reverse_median_px":fit["reverse_median_px"],
            "map_fit_params":p,
            "image_size":list(snow.size),
            "municipality_record":rec_used,
            "municipality_source_file":shp.name,
            "municipality_source_crs_note":"SCB municipality PRJ operationally verified against EPSG:3006 in separate test with 0.0 m coordinate shift over Lulea vertices.",
            "lulea_pixel_bbox":[round(v,3) for v in bbox],
            "lulea_pixel_width":round(bbox[2]-bbox[0],3),
            "lulea_pixel_height":round(bbox[3]-bbox[1],3),
            "lulea_vertices_inside_image_pct":round(100*sum(inside)/len(inside),2),
            "note":"Black/white outline is Lulea municipality transformed from SCB source CRS to EPSG:3013, then through the best symmetric SMHI PNG fit."
        }
        base.save(OUTPNG)
        OUTJSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
