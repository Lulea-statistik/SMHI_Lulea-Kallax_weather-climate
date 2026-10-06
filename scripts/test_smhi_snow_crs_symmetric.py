#!/usr/bin/env python3
"""Robustly compare CRS candidates against the SMHI county overlay.

Uses a symmetric Chamfer-style objective:
1) projected SCB county boundary points -> nearest observed SMHI boundary pixel
2) observed SMHI boundary pixels -> nearest projected boundary point
This prevents the false-small-map solution possible with a one-sided objective.
"""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import differential_evolution,minimize
from scipy.spatial import cKDTree
from pyproj import CRS,Transformer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_crs_symmetric.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
CANDS=[
 "EPSG:3006","EPSG:3007","EPSG:3008","EPSG:3009","EPSG:3010","EPSG:3011",
 "EPSG:3012","EPSG:3013","EPSG:3014","EPSG:3015","EPSG:3016","EPSG:3017",
 "EPSG:3018","EPSG:3021","EPSG:3035","EPSG:3857","EPSG:4326"
]
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-symmetric-CRS/1.0"})
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

def sample(shape,step=6000):
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
    arr=np.asarray(im); h,w=arr.shape[:2]
    obs=arr[:,:,3]>20
    yy,xx=np.where(obs)
    if len(xx)<100: raise RuntimeError("Too few observed county-overlay pixels")
    obs_pts=np.column_stack([xx,yy]).astype(float)
    # deterministic downsample for reverse-distance calculations
    if len(obs_pts)>3500:
        idx=np.linspace(0,len(obs_pts)-1,3500,dtype=int)
        obs_sample=obs_pts[idx]
    else:
        obs_sample=obs_pts
    obs_bbox=[float(xx.min()),float(yy.min()),float(xx.max()),float(yy.max())]
    obs_w=obs_bbox[2]-obs_bbox[0]; obs_h=obs_bbox[3]-obs_bbox[1]
    dt=distance_transform_edt(~obs)

    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Lan_Sweref99TM_region.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        pts=np.vstack([sample(sr.shape) for sr in sf.iterShapeRecords()])
        if len(pts)>12000:
            idx=np.linspace(0,len(pts)-1,12000,dtype=int); pts=pts[idx]

        results=[]
        for crs in CANDS:
            tr=Transformer.from_crs(src,crs,always_xy=True)
            X,Y=tr.transform(pts[:,0],pts[:,1])
            xy=np.column_stack([X,Y])
            xy=xy[np.isfinite(xy).all(axis=1)]
            xmin,ymin=xy.min(axis=0); xmax,ymax=xy.max(axis=0)
            dx=max(xmax-xmin,1e-12); dy=max(ymax-ymin,1e-12)
            # Fit projected extent to observed alpha bbox as physically meaningful start.
            sw=obs_w/dx; sh=obs_h/dy
            s0=math.sqrt(abs(sw*sh))
            cx=(xmin+xmax)/2; cy=(ymin+ymax)/2
            ocx=(obs_bbox[0]+obs_bbox[2])/2; ocy=(obs_bbox[1]+obs_bbox[3])/2
            ox0=ocx-s0*cx; oy0=ocy+s0*cy

            def objective(p):
                sc,ox,oy=p
                col=sc*xy[:,0]+ox
                row=-sc*xy[:,1]+oy
                inside=(col>=0)&(col<w)&(row>=0)&(row<h)
                frac=float(inside.mean())
                if frac<0.92:
                    return 500.0+(0.92-frac)*1000.0
                pp=np.column_stack([col[inside],row[inside]])
                rr=np.clip(np.rint(pp[:,1]).astype(int),0,h-1)
                cc=np.clip(np.rint(pp[:,0]).astype(int),0,w-1)
                forward=float(np.median(dt[rr,cc]))

                # Reverse distance: observed line pixels must also be represented.
                tree=cKDTree(pp)
                rev,_=tree.query(obs_sample,k=1)
                reverse=float(np.median(rev))

                pb=[pp[:,0].min(),pp[:,1].min(),pp[:,0].max(),pp[:,1].max()]
                pw=pb[2]-pb[0]; ph=pb[3]-pb[1]
                bbox_pen=abs(pw-obs_w)/max(obs_w,1)+abs(ph-obs_h)/max(obs_h,1)
                return forward+reverse+8.0*bbox_pen

            slo,shi=sorted((s0*0.65,s0*1.35))
            bounds=[
                (slo,shi),
                (ox0-max(120,obs_w),ox0+max(120,obs_w)),
                (oy0-max(180,obs_h),oy0+max(180,obs_h))
            ]
            de=differential_evolution(objective,bounds,seed=42,popsize=8,maxiter=55,polish=False,workers=1)
            res=minimize(objective,de.x,method="Nelder-Mead",options={"maxiter":1000})
            sc,ox,oy=res.x
            col=sc*xy[:,0]+ox; row=-sc*xy[:,1]+oy
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            pp=np.column_stack([col[inside],row[inside]])
            rr=np.clip(np.rint(pp[:,1]).astype(int),0,h-1)
            cc=np.clip(np.rint(pp[:,0]).astype(int),0,w-1)
            forward_vals=dt[rr,cc]
            tree=cKDTree(pp)
            rev,_=tree.query(obs_sample,k=1)
            pb=[float(pp[:,0].min()),float(pp[:,1].min()),float(pp[:,0].max()),float(pp[:,1].max())]
            results.append({
                "crs":crs,
                "objective":round(float(objective(res.x)),4),
                "inside_pct":round(float(inside.mean()*100),2),
                "forward_median_px":round(float(np.median(forward_vals)),3),
                "reverse_median_px":round(float(np.median(rev)),3),
                "forward_p90_px":round(float(np.percentile(forward_vals,90)),3),
                "reverse_p90_px":round(float(np.percentile(rev,90)),3),
                "projected_bbox_px":[round(v,3) for v in pb],
                "observed_bbox_px":[round(v,3) for v in obs_bbox],
                "params":{"scale":float(sc),"ox":float(ox),"oy":float(oy)}
            })

        results.sort(key=lambda r:r["objective"])
        report={
            "method":"symmetric boundary fit with isotropic scale+offset and bbox-size penalty",
            "image_size":[w,h],
            "observed_alpha_bbox_px":[round(v,3) for v in obs_bbox],
            "source_prj_explicit_epsg3006":'AUTHORITY["EPSG",3006]' in prj,
            "results":results
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
