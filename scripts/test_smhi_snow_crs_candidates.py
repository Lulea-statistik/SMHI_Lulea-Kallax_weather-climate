#!/usr/bin/env python3
"""Compare SMHI-advertised CRS candidates against the fixed snow-map county overlay."""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import differential_evolution, minimize
from pyproj import Transformer, CRS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_candidates.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
CANDS=["EPSG:3006","EPSG:3007","EPSG:3008","EPSG:3009","EPSG:3010","EPSG:3011","EPSG:3012","EPSG:3013","EPSG:3014","EPSG:3015","EPSG:3016","EPSG:3017","EPSG:3018","EPSG:3021","EPSG:3035","EPSG:3857","EPSG:4326"]
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-CRS-test/1.0"})
    r.raise_for_status(); return r.content

def expand(td):
    root=Path(td)
    with zipfile.ZipFile(io.BytesIO(dl(SCB))) as z: z.extractall(root)
    for zp in list(root.rglob("*.zip")):
        dest=zp.parent/(zp.stem+"_expanded"); dest.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zp) as z: z.extractall(dest)
        except zipfile.BadZipFile: pass
    return root

def sample(sh,step=7000):
    out=[]; parts=list(sh.parts)+[len(sh.points)]
    for a,b in zip(parts[:-1],parts[1:]):
        ring=sh.points[a:b]
        for p0,p1 in zip(ring,ring[1:]+ring[:1]):
            x0,y0=p0;x1,y1=p1
            L=math.hypot(x1-x0,y1-y0); n=max(1,int(L/step))
            for k in range(n+1):
                q=k/n; out.append((x0+(x1-x0)*q,y0+(y1-y0)*q))
    return np.asarray(out,float)

def main():
    im=Image.open(io.BytesIO(dl(SMHI))).convert("RGBA")
    a=np.asarray(im); h,w=a.shape[:2]
    mask=a[:,:,3]>20
    dist=distance_transform_edt(~mask)

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Lan_Sweref99TM_region.shp"))
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        pts=np.vstack([sample(sr.shape) for sr in sf.iterShapeRecords()])

        # Verify actual source CRS from PRJ.
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        src_epsg=src.to_epsg()
        # ESRI WKT may not round-trip through to_epsg(), even when the WKT
        # explicitly carries an EPSG authority code. Capture that authority.
        src_authority=src.to_authority()
        results=[]

        for crs in CANDS:
            tr=Transformer.from_crs(src,crs,always_xy=True)
            X,Y=tr.transform(pts[:,0],pts[:,1])
            xy=np.column_stack([X,Y])
            good=np.isfinite(xy).all(axis=1)
            xy=xy[good]
            xmin,ymin=xy.min(axis=0); xmax,ymax=xy.max(axis=0)
            sx0=(w-20)/(xmax-xmin); sy0=(h-20)/(ymax-ymin)
            # only independent x/y scales + offsets; no shear/rotation.
            p0=np.array([sx0,10-sx0*xmin,-sy0,h-10+sy0*ymin],float)

            def obj(p):
                sx,ox,sy,oy=p
                col=sx*xy[:,0]+ox
                row=sy*xy[:,1]+oy
                inside=(col>=0)&(col<w)&(row>=0)&(row<h)
                if inside.mean()<0.96: return 999+(0.96-inside.mean())*1000
                rr=np.rint(row[inside]).astype(int); cc=np.rint(col[inside]).astype(int)
                vals=dist[rr,cc]
                return float(np.median(vals)+0.3*np.percentile(vals,80))

            # Offset terms are in pixel space after multiplying very large
            # projected coordinates, so they may be hundreds or thousands of
            # pixels in magnitude. Centre bounds on the analytically derived p0.
            sxlo,sxhi=sorted((p0[0]*0.6,p0[0]*1.5))
            sylo,syhi=sorted((p0[2]*0.6,p0[2]*1.5))
            oxspan=max(500.0,abs(p0[1])*1.5)
            oyspan=max(500.0,abs(p0[3])*1.5)
            bounds=[
                (sxlo,sxhi),
                (p0[1]-oxspan,p0[1]+oxspan),
                (sylo,syhi),
                (p0[3]-oyspan,p0[3]+oyspan)
            ]
            de=differential_evolution(obj,bounds,seed=42,popsize=10,maxiter=80,polish=False)
            res=minimize(obj,de.x,method="Nelder-Mead",options={"maxiter":1500})
            p=res.x
            col=p[0]*xy[:,0]+p[1]; row=p[2]*xy[:,1]+p[3]
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            if inside.any():
                vals=dist[np.rint(row[inside]).astype(int),np.rint(col[inside]).astype(int)]
                med=round(float(np.median(vals)),3)
                p90=round(float(np.percentile(vals,90)),3)
            else:
                vals=np.array([],dtype=float)
                med=None
                p90=None
            results.append({
                "crs":crs,
                "objective":round(float(obj(p)),4),
                "inside_pct":round(float(inside.mean()*100),2),
                "valid":bool(inside.any()),
                "median_pixel_error":med,
                "p90_pixel_error":p90,
                "params":{"sx":float(p[0]),"ox":float(p[1]),"sy":float(p[2]),"oy":float(p[3])}
            })
        results.sort(key=lambda r:r["objective"])
        report={
            "source_shapefile":shp.name,
            "source_prj_epsg_verified":src_epsg,
            "source_prj_authority":list(src_authority) if src_authority else None,
            "source_prj_explicit_epsg3006":'AUTHORITY["EPSG",3006]' in prj,
            "source_prj_wkt_prefix":prj[:500],
            "image_size":[w,h],
            "model":"candidate CRS + independent x/y scale and offset only; no rotation/shear/polynomial",
            "results":results
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
