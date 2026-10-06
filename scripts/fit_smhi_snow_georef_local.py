#!/usr/bin/env python3
"""Locally refine SMHI snow PNG georeference for Norrbotten and map Lulea municipality."""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import minimize

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_georef_local.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
GLOBAL=ROOT/"docs"/"snowgrid"/"smhi_snow_georef_fit.json"
TIMEOUT=90

def download(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-local-georef/1.0"})
    r.raise_for_status(); return r.content

def expand_scb(td):
    root=Path(td)
    with zipfile.ZipFile(io.BytesIO(download(SCB))) as z: z.extractall(root)
    for zp in list(root.rglob("*.zip")):
        dest=zp.parent/(zp.stem+"_expanded"); dest.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zp) as nz: nz.extractall(dest)
        except zipfile.BadZipFile: pass
    return root

def sample_shape(sh, step=4000.0):
    pts=[]; parts=list(sh.parts)+[len(sh.points)]
    for a,b in zip(parts[:-1],parts[1:]):
        ring=sh.points[a:b]
        if len(ring)<2: continue
        for p0,p1 in zip(ring,ring[1:]+ring[:1]):
            x0,y0=p0; x1,y1=p1
            L=math.hypot(x1-x0,y1-y0); n=max(1,int(L/step))
            for k in range(n+1):
                q=k/n; pts.append((x0+(x1-x0)*q,y0+(y1-y0)*q))
    return np.asarray(pts,float)

def apply(par, pts):
    a,b,c,d,e,f=par
    return np.column_stack((a*pts[:,0]+b*pts[:,1]+c,d*pts[:,0]+e*pts[:,1]+f))

def eval_err(par,pts,dist,w,h):
    pr=apply(par,pts); col,row=pr[:,0],pr[:,1]
    inside=(col>=0)&(col<w)&(row>=0)&(row<h)
    rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
    cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
    px=dist[rr,cc]
    return inside,px

def main():
    g=json.loads(GLOBAL.read_text(encoding="utf-8"))
    A=g["affine_epsg3006_to_pixel"]
    p0=np.array([A["a"],A["b"],A["c"],A["d"],A["e"],A["f"]],float)

    img=Image.open(io.BytesIO(download(SMHI))).convert("RGBA")
    ar=np.asarray(img); h,w=ar.shape[:2]
    mask=ar[:,:,3]>20

    # Restrict target line mask to north-Sweden window predicted by global fit,
    # avoiding attraction to unrelated county borders in southern Sweden.
    with tempfile.TemporaryDirectory() as td:
        root=expand_scb(td)
        lshp=next(root.rglob("Lan_Sweref99TM_region.shp"))
        kshp=next(root.rglob("Kommun_Sweref99TM.shp"))
        lsf=shapefile.Reader(str(lshp),encoding="cp1252")
        ksf=shapefile.Reader(str(kshp),encoding="cp1252")
        lf=[f[0] for f in lsf.fields[1:]]
        kf=[f[0] for f in ksf.fields[1:]]

        north_pts=[]; norr_pts=[]; county_records=[]
        for sr in lsf.iterShapeRecords():
            rec=dict(zip(lf,list(sr.record)))
            code=str(rec.get("LnKod") or rec.get("lnkod") or "")
            if code in {"24","25"}:
                pts=sample_shape(sr.shape)
                north_pts.append(pts); county_records.append(rec)
                if code=="25": norr_pts=pts
        north=np.vstack(north_pts)

        pred=apply(p0,north)
        xmin=max(0,int(np.floor(pred[:,0].min()-35))); xmax=min(w-1,int(np.ceil(pred[:,0].max()+35)))
        ymin=max(0,int(np.floor(pred[:,1].min()-45))); ymax=min(h-1,int(np.ceil(pred[:,1].max()+45)))
        localmask=np.zeros_like(mask)
        localmask[ymin:ymax+1,xmin:xmax+1]=mask[ymin:ymax+1,xmin:xmax+1]
        dist=distance_transform_edt(~localmask)

        def objective(par):
            inside,px=eval_err(par,north,dist,w,h)
            if inside.mean()<0.95: return 1e4+(0.95-inside.mean())*1e5
            # Regularize toward global solution to prevent pathological line matching.
            scale=np.array([5e-5,5e-5,40,5e-5,5e-5,40],float)
            reg=np.sum(((par-p0)/scale)**2)*0.03
            return float(np.median(px)+0.35*np.percentile(px,80)+reg)

        res=minimize(objective,p0,method="Nelder-Mead",
                     options={"maxiter":5000,"xatol":1e-10,"fatol":1e-6})
        par=res.x

        def summary(pts):
            inside,px=eval_err(par,pts,dist,w,h)
            # local metres/pixel from Jacobian
            M=np.array([[par[0],par[1]],[par[3],par[4]]],float)
            sv=np.linalg.svd(M,compute_uv=False); mpp=float(np.mean([1/s for s in sv if s>0]))
            return {
                "n":int(len(pts)),"inside_pct":round(float(inside.mean()*100),2),
                "median_pixel_error":round(float(np.median(px)),3),
                "p90_pixel_error":round(float(np.percentile(px,90)),3),
                "median_error_km_approx":round(float(np.median(px)*mpp/1000),2),
                "p90_error_km_approx":round(float(np.percentile(px,90)*mpp/1000),2),
                "approx_metres_per_pixel":round(mpp,1)
            }

        # Find Lulea municipality directly in the official EPSG:3006 municipality file.
        lulea=None
        for sr in ksf.iterShapeRecords():
            rec=dict(zip(kf,list(sr.record)))
            vals=" ".join(str(v) for v in rec.values()).lower()
            if "luleå" in vals or "lulea" in vals or any(str(v)=="2580" for v in rec.values()):
                lulea=(rec,sr.shape); break
        if lulea is None: raise RuntimeError("Lulea municipality not found")
        lrec,lshape=lulea
        lpts=np.asarray(lshape.points,float)
        pix=apply(par,lpts)
        bbox={
            "min_col":float(pix[:,0].min()),"max_col":float(pix[:,0].max()),
            "min_row":float(pix[:,1].min()),"max_row":float(pix[:,1].max())
        }

        report={
            "method":"local affine refinement using SCB counties 24+25 against SMHI lan2425.png",
            "source_crs":"EPSG:3006 from SCB SWEREF99TM package",
            "image_size":[w,h],
            "north_search_window":{"xmin":xmin,"xmax":xmax,"ymin":ymin,"ymax":ymax},
            "global_affine":[float(x) for x in p0],
            "local_affine":[float(x) for x in par],
            "optimizer":{"success":bool(res.success),"message":str(res.message),"objective":float(res.fun)},
            "fit_north_counties":summary(north),
            "fit_norrbotten":summary(norr_pts),
            "lulea_record":lrec,
            "lulea_pixel_bbox":bbox,
            "lulea_all_vertices_inside_image":bool((pix[:,0]>=0).all() and (pix[:,0]<w).all() and (pix[:,1]>=0).all() and (pix[:,1]<h).all())
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
