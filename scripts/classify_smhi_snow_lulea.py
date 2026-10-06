#!/usr/bin/env python3
"""Quality-check Lulea clipping mask and classify SMHI snow-depth colors."""

from __future__ import annotations
import io,json,tempfile,zipfile,math
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image,ImageDraw
from pyproj import CRS,Transformer
from shapely.geometry import Polygon,MultiPolygon,shape as shp_shape
from shapely.ops import transform as shp_transform

ROOT=Path(__file__).resolve().parents[1]
FIT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_symmetric.json"
OUTJSON=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_classification_2026-02-15.json"
OUTPNG=ROOT/"docs"/"snowgrid"/"smhi_snow_lulea_classification_2026-02-15.png"

SNOW="https://www.smhi.se/pd/klimat/snow_depth/2526/sno260215.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
TIMEOUT=90

# Official legend colors recovered from SMHI snow-depth app code.
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
MAX_COLOR_DIST=34.0

def dl(url):
    last=None
    for attempt in range(5):
        try:
            r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-snow-classify/1.0"})
            r.raise_for_status(); return r.content
        except requests.RequestException as exc:
            last=exc
            if attempt<4:
                import time; time.sleep(5*(attempt+1))
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

def shp_to_shapely(sh):
    return shp_shape(sh.__geo_interface__)

def main():
    fitdata=json.loads(FIT.read_text(encoding="utf-8"))
    fit=next(r for r in fitdata["results"] if r["crs"]=="EPSG:3013")
    p=fit["params"]; sc=float(p["scale"]); ox=float(p["ox"]); oy=float(p["oy"])
    metres_per_pixel=1.0/sc

    snow=Image.open(io.BytesIO(dl(SNOW))).convert("RGBA")
    arr=np.asarray(snow)
    h,w=arr.shape[:2]

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Kommun_Sweref99TM.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
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

        geom_src=shp_to_shapely(target)
        # Operational source is equivalent to EPSG:3006 for these coordinates.
        official_area_km2=float(geom_src.area/1e6)
        official_centroid=(float(geom_src.centroid.x),float(geom_src.centroid.y))

        tr_3013=Transformer.from_crs(src,"EPSG:3013",always_xy=True).transform
        geom3013=shp_transform(tr_3013,geom_src)
        area3013_km2=float(geom3013.area/1e6)

        # Map geometry into PNG pixel coordinates.
        def to_px(x,y,z=None):
            return (sc*x+ox,-sc*y+oy)
        geom_px=shp_transform(to_px,geom3013)
        exact_pixel_area=float(geom_px.area)
        area_from_exact_pixel_geom_km2=exact_pixel_area*(metres_per_pixel**2)/1e6

        # Raster mask at native 249x570 resolution.
        mask_img=Image.new("1",(w,h),0)
        d=ImageDraw.Draw(mask_img)
        polys=list(geom_px.geoms) if isinstance(geom_px,MultiPolygon) else [geom_px]
        for poly in polys:
            ext=[(float(x),float(y)) for x,y in poly.exterior.coords]
            d.polygon(ext,fill=1)
            for hole in poly.interiors:
                d.polygon([(float(x),float(y)) for x,y in hole.coords],fill=0)
        mask=np.asarray(mask_img,dtype=bool)
        raster_pixels=int(mask.sum())
        raster_area_km2=raster_pixels*(metres_per_pixel**2)/1e6

        # Color classification inside Lulea.
        rgb=arr[:,:,:3].astype(float)
        alpha=arr[:,:,3]
        palette=np.array([x[1] for x in PALETTE],dtype=float)
        flat=rgb[mask]
        dists=np.sqrt(((flat[:,None,:]-palette[None,:,:])**2).sum(axis=2))
        nearest=dists.argmin(axis=1)
        mind=dists.min(axis=1)
        accepted=mind<=MAX_COLOR_DIST

        counts=[]
        total_accept=int(accepted.sum())
        for i,(label,color,lower) in enumerate(PALETTE):
            n=int(((nearest==i)&accepted).sum())
            counts.append({
                "class":label,"legend_rgb":list(color),"lower_cm":lower,
                "pixels":n,
                "share_of_classified_pct":round(100*n/total_accept,2) if total_accept else None
            })

        # Diagnostic preview: snow image + semi-transparent outside mask + boundary.
        preview=snow.copy()
        rgba=np.asarray(preview).copy()
        rgba[~mask,:3]=(rgba[~mask,:3]*0.35).astype(np.uint8)
        rgba[~mask,3]=255
        preview=Image.fromarray(rgba,"RGBA")
        pd=ImageDraw.Draw(preview)
        for poly in polys:
            ext=[(float(x),float(y)) for x,y in poly.exterior.coords]
            pd.line(ext,fill=(0,0,0,255),width=2)
        preview.save(OUTPNG)

        minx,miny,maxx,maxy=geom_px.bounds
        report={
            "date":"2026-02-15",
            "snow_png":SNOW,
            "map_fit_crs":"EPSG:3013",
            "map_fit_objective":fit["objective"],
            "map_fit_forward_median_px":fit["forward_median_px"],
            "map_fit_reverse_median_px":fit["reverse_median_px"],
            "metres_per_pixel_approx":round(metres_per_pixel,2),
            "municipality":rec_used,
            "source_crs_note":"SCB municipality coordinates operationally verified separately as 0.0 m shift to EPSG:3006 over Lulea vertices.",
            "qa":{
                "official_polygon_area_km2_epsg3006_coords":round(official_area_km2,3),
                "polygon_area_km2_after_transform_epsg3013":round(area3013_km2,3),
                "exact_pixel_geometry_area_km2":round(area_from_exact_pixel_geom_km2,3),
                "native_raster_mask_area_km2":round(raster_area_km2,3),
                "native_raster_area_error_pct_vs_official":round(100*(raster_area_km2-official_area_km2)/official_area_km2,2),
                "exact_pixel_geometry_area_error_pct_vs_official":round(100*(area_from_exact_pixel_geom_km2-official_area_km2)/official_area_km2,2),
                "lulea_pixel_bbox":[round(minx,3),round(miny,3),round(maxx,3),round(maxy,3)],
                "lulea_pixel_width":round(maxx-minx,3),
                "lulea_pixel_height":round(maxy-miny,3),
                "native_mask_pixels":raster_pixels
            },
            "classification":{
                "palette_source":"SMHI snow-depth app legend",
                "max_rgb_distance":MAX_COLOR_DIST,
                "inside_mask_pixels":int(len(flat)),
                "classified_pixels":total_accept,
                "unclassified_pixels":int(len(flat)-total_accept),
                "classified_share_pct":round(100*total_accept/len(flat),2) if len(flat) else None,
                "classes":counts
            },
            "warning":"Derived from rendered SMHI PNG. Classes are map legend categories, not an original numeric raster. Native image resolution is coarse."
        }
        OUTJSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
