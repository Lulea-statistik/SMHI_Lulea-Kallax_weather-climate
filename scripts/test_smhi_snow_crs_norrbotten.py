#!/usr/bin/env python3
"""Validate top SMHI snow-map CRS candidates specifically in Norrbotten."""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import differential_evolution,minimize
from pyproj import Transformer,CRS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_norrbotten.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
CANDS=["EPSG:4326","EPSG:3857","EPSG:3006"]
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-Norrbotten-CRS/1.0"})
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

def sample(shape,step=3500):
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
        recs=[]
        for sr in sf.iterShapeRecords():
            rec=dict(zip(fields,list(sr.record)))
            if str(rec.get("lnkod") or rec.get("LNKOD") or rec.get("LnKod") or "").zfill(2)=="25":
                recs.append(sr)
        if not recs: raise RuntimeError("Norrbotten county not found")
        pts=np.vstack([sample(sr.shape) for sr in recs])

        results=[]
        for crs in CANDS:
            tr=Transformer.from_crs(src,crs,always_xy=True)
            X,Y=tr.transform(pts[:,0],pts[:,1]); xy=np.column_stack([X,Y])
            good=np.isfinite(xy).all(axis=1); xy=xy[good]
            xmin,ymin=xy.min(axis=0); xmax,ymax=xy.max(axis=0)
            sx0=(w-20)/(xmax-xmin); sy0=(h-20)/(ymax-ymin)
            s0=min(abs(sx0),abs(sy0))
            p0=np.array([s0,10-s0*xmin,h-10+s0*ymin],float)
            def obj(p):
                sc,ox,oy=p
                col=sc*xy[:,0]+ox; row=-sc*xy[:,1]+oy
                inside=(col>=0)&(col<w)&(row>=0)&(row<h)
                if inside.mean()<0.98:return 999+(0.98-inside.mean())*1000
                rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
                cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
                vals=dist[rr,cc]
                return float(np.median(vals)+0.3*np.percentile(vals,80))
            slo,shi=sorted((s0*0.4,s0*2.2))
            oxspan=max(1000.0,abs(p0[1])*2.0); oyspan=max(1000.0,abs(p0[2])*2.0)
            bounds=[(slo,shi),(p0[1]-oxspan,p0[1]+oxspan),(p0[2]-oyspan,p0[2]+oyspan)]
            de=differential_evolution(obj,bounds,seed=42,popsize=12,maxiter=100,polish=False)
            res=minimize(obj,de.x,method="Nelder-Mead",options={"maxiter":2000})
            p=res.x
            col=p[0]*xy[:,0]+p[1]; row=-p[0]*xy[:,1]+p[2]
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            if inside.any():
                rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
                cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
                vals=dist[rr,cc]
                med=round(float(np.median(vals)),3)
                p90=round(float(np.percentile(vals,90)),3)
            else:
                med=None
                p90=None
            results.append({
                "crs":crs,
                "objective":round(float(obj(p)),4),
                "inside_pct":round(float(inside.mean()*100),2),
                "valid":bool(inside.any()),
                "median_pixel_error":med,
                "p90_pixel_error":p90,
                "params":{"scale":float(p[0]),"ox":float(p[1]),"oy":float(p[2])}
            })
        results.sort(key=lambda r:r["objective"])
        out={"region":"Norrbotten county (lnkod 25)","model":"isotropic north-up scale+offset","image_size":[w,h],"results":results}
        OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
