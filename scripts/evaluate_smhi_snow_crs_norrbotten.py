#!/usr/bin/env python3
"""Evaluate national SMHI snow CRS fits specifically on Norrbotten, without local refitting."""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image
from scipy.ndimage import distance_transform_edt
from pyproj import Transformer,CRS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_norrbotten_eval.json"
NATIONAL=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_candidates.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
CANDS=["EPSG:4326","EPSG:3857","EPSG:3006"]
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-Norrbotten-eval/1.0"})
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

def sample(shape,step=2500):
    pts=[]; parts=list(shape.parts)+[len(shape.points)]
    for a,b in zip(parts[:-1],parts[1:]):
        ring=shape.points[a:b]
        for p0,p1 in zip(ring,ring[1:]+ring[:1]):
            x0,y0=p0;x1,y1=p1
            L=math.hypot(x1-x0,y1-y0); n=max(1,int(L/step))
            for k in range(n+1):
                q=k/n; pts.append((x0+(x1-x0)*q,y0+(y1-y0)*q))
    return np.asarray(pts,float)

def main():
    nat=json.loads(NATIONAL.read_text(encoding="utf-8"))
    fits={r["crs"]:r for r in nat["results"] if r["crs"] in CANDS}
    im=Image.open(io.BytesIO(dl(SMHI))).convert("RGBA")
    a=np.asarray(im); h,w=a.shape[:2]
    mask=a[:,:,3]>20
    dist=distance_transform_edt(~mask)

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Lan_Sweref99TM_region.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        fields=[x[0] for x in sf.fields[1:]]
        pts=[]
        for sr in sf.iterShapeRecords():
            rec=dict(zip(fields,list(sr.record)))
            code=str(rec.get("lnkod") or rec.get("LNKOD") or rec.get("LnKod") or "").zfill(2)
            if code=="25":
                pts.append(sample(sr.shape))
        if not pts: raise RuntimeError("Norrbotten county not found")
        pts=np.vstack(pts)

        results=[]
        for crs in CANDS:
            fit=fits[crs]
            p=fit["params"]
            tr=Transformer.from_crs(src,crs,always_xy=True)
            X,Y=tr.transform(pts[:,0],pts[:,1])
            xy=np.column_stack([X,Y])
            good=np.isfinite(xy).all(axis=1); xy=xy[good]
            col=float(p["scale"])*xy[:,0]+float(p["ox"])
            row=-float(p["scale"])*xy[:,1]+float(p["oy"])
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            if inside.any():
                rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
                cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
                vals=dist[rr,cc]
                med=float(np.median(vals)); p90=float(np.percentile(vals,90)); mean=float(np.mean(vals))
            else:
                med=p90=mean=None
            results.append({
                "crs":crs,
                "inside_pct":round(float(inside.mean()*100),2),
                "median_pixel_error":None if med is None else round(med,3),
                "mean_pixel_error":None if mean is None else round(mean,3),
                "p90_pixel_error":None if p90 is None else round(p90,3),
                "national_objective":fit.get("objective"),
                "national_median_pixel_error":fit.get("median_pixel_error"),
                "national_p90_pixel_error":fit.get("p90_pixel_error"),
                "params":p
            })
        results.sort(key=lambda r:(999 if r["median_pixel_error"] is None else r["median_pixel_error"],
                                   999 if r["p90_pixel_error"] is None else r["p90_pixel_error"]))
        report={
            "region":"Norrbotten county (lnkod 25)",
            "method":"evaluate national isotropic CRS fits from #5 on Norrbotten only; no local refit",
            "image_size":[w,h],
            "results":results
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
