#!/usr/bin/env python3
"""Fit a second-order polynomial georeference from EPSG:3006 to SMHI snow PNG pixels."""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import minimize

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_georef_poly2.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
GLOBAL=ROOT/"docs"/"snowgrid"/"smhi_snow_georef_fit.json"
TIMEOUT=90

def download(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-poly2-georef/1.0"})
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

def sample_shape(sh, step=5000.0):
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

def terms(pts,x0,y0,sx,sy):
    x=(pts[:,0]-x0)/sx; y=(pts[:,1]-y0)/sy
    return np.column_stack([np.ones(len(pts)),x,y,x*x,x*y,y*y])

def apply(par,pts,norm):
    T=terms(pts,*norm)
    c=T@par[:6]; r=T@par[6:]
    return np.column_stack([c,r])

def main():
    g=json.loads(GLOBAL.read_text(encoding="utf-8"))
    A=g["affine_epsg3006_to_pixel"]
    img=Image.open(io.BytesIO(download(SMHI))).convert("RGBA")
    ar=np.asarray(img); h,w=ar.shape[:2]
    mask=ar[:,:,3]>20
    dist=distance_transform_edt(~mask)

    with tempfile.TemporaryDirectory() as td:
        root=expand_scb(td)
        lsf=shapefile.Reader(str(next(root.rglob("Lan_Sweref99TM_region.shp"))),encoding="cp1252")
        ksf=shapefile.Reader(str(next(root.rglob("Kommun_Sweref99TM.shp"))),encoding="cp1252")
        lf=[f[0] for f in lsf.fields[1:]]
        kf=[f[0] for f in ksf.fields[1:]]

        allpts=[]; norr=None; county=[]
        for sr in lsf.iterShapeRecords():
            rec=dict(zip(lf,list(sr.record)))
            pts=sample_shape(sr.shape)
            allpts.append(pts)
            code=str(rec.get("LnKod") or rec.get("lnkod") or "")
            county.append((code,rec,pts))
            if code=="25": norr=pts
        pts=np.vstack(allpts)

        # Normalize coordinates for numerically stable polynomial coefficients.
        x0=float(np.mean(pts[:,0])); y0=float(np.mean(pts[:,1]))
        sx=float(np.std(pts[:,0])); sy=float(np.std(pts[:,1]))
        norm=(x0,y0,sx,sy)

        # Initialize polynomial from existing affine transform.
        # col=a*x+b*y+c -> coefficients in normalized coordinates.
        a,b,c,d,e,f=A["a"],A["b"],A["c"],A["d"],A["e"],A["f"]
        init=np.zeros(12,float)
        init[0]=a*x0+b*y0+c; init[1]=a*sx; init[2]=b*sy
        init[6]=d*x0+e*y0+f; init[7]=d*sx; init[8]=e*sy

        rng=np.random.default_rng(42)
        optpts=pts if len(pts)<=12000 else pts[rng.choice(len(pts),12000,replace=False)]

        # Weight north more heavily but still constrain nationwide geometry.
        north=np.vstack([p for code,rec,p in county if code in {"24","25"}])
        if len(north)>3500: north=north[rng.choice(len(north),3500,replace=False)]

        def errvals(par,ps):
            pr=apply(par,ps,norm); col,row=pr[:,0],pr[:,1]
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
            cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
            return inside,dist[rr,cc]

        def objective(par):
            inside,px=errvals(par,optpts)
            in2,px2=errvals(par,north)
            if inside.mean()<0.92 or in2.mean()<0.97:
                return 1e4+(0.92-inside.mean())**2*1e5+(0.97-in2.mean())**2*2e5
            # Penalize overly strong quadratic warping.
            quad=np.r_[par[3:6],par[9:12]]
            reg=0.002*np.sum(quad*quad)
            return float(np.median(px)+0.25*np.percentile(px,80)+
                         1.8*np.median(px2)+0.45*np.percentile(px2,80)+reg)

        res=minimize(objective,init,method="Powell",
                     options={"maxiter":1200,"xtol":1e-7,"ftol":1e-5,"disp":True})
        par=res.x

        def summary(ps):
            inside,px=errvals(par,ps)
            return {
                "n":int(len(ps)),"inside_pct":round(float(inside.mean()*100),2),
                "median_pixel_error":round(float(np.median(px)),3),
                "p90_pixel_error":round(float(np.percentile(px,90)),3)
            }

        # local approximate metres/pixel near Lulea via finite differences
        lulea=None
        for sr in ksf.iterShapeRecords():
            rec=dict(zip(kf,list(sr.record)))
            vals=" ".join(str(v) for v in rec.values()).lower()
            if "luleå" in vals or "lulea" in vals or any(str(v)=="2580" for v in rec.values()):
                lulea=(rec,sr.shape); break
        if not lulea: raise RuntimeError("Lulea not found")
        lrec,lshape=lulea
        lpts=np.asarray(lshape.points,float)
        centroid=np.mean(lpts,axis=0)
        base=apply(par,centroid[None,:],norm)[0]
        dx=apply(par,np.array([[centroid[0]+1000,centroid[1]]]),norm)[0]-base
        dy=apply(par,np.array([[centroid[0],centroid[1]+1000]]),norm)[0]-base
        ppm=(np.linalg.norm(dx)+np.linalg.norm(dy))/2000
        mpp=float(1/ppm)
        pix=apply(par,lpts,norm)

        ev_all=summary(pts); ev_n=summary(norr)
        for ev in (ev_all,ev_n):
            ev["approx_metres_per_pixel_near_lulea"]=round(mpp,1)
            ev["median_error_km_approx"]=round(ev["median_pixel_error"]*mpp/1000,2)
            ev["p90_error_km_approx"]=round(ev["p90_pixel_error"]*mpp/1000,2)

        report={
            "method":"second-order polynomial EPSG:3006 -> SMHI image pixels",
            "source_crs":"EPSG:3006 from SCB SWEREF99TM package",
            "image_size":[w,h],
            "normalization":{"x0":x0,"y0":y0,"sx":sx,"sy":sy},
            "coefficients_col":[float(x) for x in par[:6]],
            "coefficients_row":[float(x) for x in par[6:]],
            "optimizer":{"success":bool(res.success),"message":str(res.message),"objective":float(res.fun)},
            "fit_all_counties":ev_all,
            "fit_norrbotten":ev_n,
            "lulea_record":lrec,
            "lulea_pixel_bbox":{
                "min_col":float(pix[:,0].min()),"max_col":float(pix[:,0].max()),
                "min_row":float(pix[:,1].min()),"max_row":float(pix[:,1].max())
            },
            "lulea_all_vertices_inside_image":bool((pix[:,0]>=0).all() and (pix[:,0]<w).all() and (pix[:,1]>=0).all() and (pix[:,1]<h).all())
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
