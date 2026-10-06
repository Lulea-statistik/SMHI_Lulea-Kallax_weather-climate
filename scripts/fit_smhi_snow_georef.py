#!/usr/bin/env python3
"""Fit SMHI snow-map image pixels to SCB county boundaries in EPSG:3006."""

from __future__ import annotations
import io,json,math,tempfile,zipfile
from pathlib import Path
import requests
import numpy as np
from PIL import Image
import shapefile
from scipy.ndimage import distance_transform_edt
from scipy.optimize import differential_evolution, minimize

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_georef_fit.json"
SMHI="https://www.smhi.se/pd/klimat/snow_depth/layer_imgs/lan2425.png"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
TIMEOUT=90

def download(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SMHI-georef-fit/1.0"})
    r.raise_for_status()
    return r.content

def pick_county_shp(folder: Path):
    cands=list(folder.rglob("*.shp"))
    scored=[]
    for p in cands:
        try:
            sf=shapefile.Reader(str(p), encoding="cp1252")
            fields=[f[0].lower() for f in sf.fields[1:]]
            n=len(sf)
            # Counties are normally about 21 polygons and often have lan/län fields.
            score=(50 if 15<=n<=30 else 0)+(20 if any("lan" in f or "län" in f for f in fields) else 0)
            scored.append((score,n,p,fields))
        except Exception:
            pass
    if not scored:
        raise RuntimeError("No readable shapefile in SCB zip")
    scored.sort(key=lambda x:(x[0],-abs(x[1]-21)),reverse=True)
    return scored[0], scored

def sample_shape_boundaries(sf, step_m=6000.0):
    pts=[]
    rec_info=[]
    fields=[f[0] for f in sf.fields[1:]]
    for idx,sr in enumerate(sf.iterShapeRecords()):
        sh=sr.shape
        rec=dict(zip(fields,list(sr.record)))
        parts=list(sh.parts)+[len(sh.points)]
        local=[]
        for a,b in zip(parts[:-1],parts[1:]):
            ring=sh.points[a:b]
            if len(ring)<2: continue
            for p0,p1 in zip(ring,ring[1:]+ring[:1]):
                x0,y0=p0; x1,y1=p1
                length=math.hypot(x1-x0,y1-y0)
                n=max(1,int(length/step_m))
                for k in range(n+1):
                    q=k/n
                    local.append((x0+(x1-x0)*q,y0+(y1-y0)*q))
        if local:
            arr=np.asarray(local,dtype=float)
            pts.append(arr)
            rec_info.append({"index":idx,"record":rec,"points":arr})
    return np.vstack(pts), rec_info

def main():
    img=Image.open(io.BytesIO(download(SMHI))).convert("RGBA")
    arr=np.asarray(img)
    h,w=arr.shape[:2]
    alpha=arr[:,:,3]
    rgb=arr[:,:,:3]

    # County overlay is expected to be transparent outside line work.
    if np.mean(alpha==0)>0.2:
        mask=alpha>20
        mask_mode="alpha>20"
    else:
        flat=rgb.reshape(-1,3)
        vals,cnt=np.unique(flat,axis=0,return_counts=True)
        bg=vals[np.argmax(cnt)]
        diff=np.linalg.norm(rgb.astype(float)-bg.astype(float),axis=2)
        mask=diff>20
        mask_mode=f"rgb distance from dominant {bg.tolist()} > 20"

    # Dilate tolerance implicitly through a distance field.
    dist=distance_transform_edt(~mask)

    with tempfile.TemporaryDirectory() as td:
        raw=download(SCB)
        z=zipfile.ZipFile(io.BytesIO(raw))
        z.extractall(td)

        # SCB packages may contain nested ZIP archives. Expand those too.
        root=Path(td)
        expanded=True
        while expanded:
            expanded=False
            for zp in list(root.rglob("*.zip")):
                marker=zp.with_suffix(zp.suffix+".expanded")
                if marker.exists():
                    continue
                try:
                    with zipfile.ZipFile(zp) as nz:
                        dest=zp.parent/(zp.stem+"_expanded")
                        dest.mkdir(exist_ok=True)
                        nz.extractall(dest)
                    marker.write_text("ok",encoding="utf-8")
                    expanded=True
                except zipfile.BadZipFile:
                    marker.write_text("bad",encoding="utf-8")

        all_files=[str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
        print(json.dumps({"scb_archive_files":all_files[:400]},ensure_ascii=False,indent=2))

        (score,n,p,fields),scored=pick_county_shp(root)
        sf=shapefile.Reader(str(p), encoding="cp1252")
        pts, county_info=sample_shape_boundaries(sf)

        # Affine mapping EPSG:3006 (x,y) -> image (col,row)
        xmin,ymin=pts.min(axis=0); xmax,ymax=pts.max(axis=0)
        # Reasonable north-up initialization.
        sx=(w-12)/(xmax-xmin)
        sy=-(h-12)/(ymax-ymin)
        tx=6-sx*xmin
        ty=h-6-sy*ymin
        x0=np.array([sx,0,tx,0,sy,ty],dtype=float)

        # Keep a representative sample for optimization speed.
        rng=np.random.default_rng(42)
        if len(pts)>12000:
            optpts=pts[rng.choice(len(pts),12000,replace=False)]
        else:
            optpts=pts

        def score_affine(par, pset=optpts):
            a,b,c,d,e,f=par
            col=a*pset[:,0]+b*pset[:,1]+c
            row=d*pset[:,0]+e*pset[:,1]+f
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            if inside.mean()<0.65:
                return 1000+(0.65-inside.mean())*5000
            cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
            rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
            vals=dist[rr,cc]
            # Robust objective; penalize outliers less.
            return float(np.percentile(vals,70)+0.35*np.mean(np.minimum(vals,20)))

        bounds=[
            (x0[0]*0.65,x0[0]*1.35),(-0.00025,0.00025),(x0[2]-120,x0[2]+120),
            (-0.00025,0.00025),(x0[4]*1.35,x0[4]*0.65),(x0[5]-120,x0[5]+120)
        ]
        de=differential_evolution(score_affine,bounds,seed=42,maxiter=80,popsize=10,tol=1e-5,polish=False)
        loc=minimize(score_affine,de.x,method="Nelder-Mead",options={"maxiter":2500,"xatol":1e-8,"fatol":1e-5})
        par=loc.x

        def eval_points(pset):
            a,b,c,d,e,f=par
            col=a*pset[:,0]+b*pset[:,1]+c
            row=d*pset[:,0]+e*pset[:,1]+f
            inside=(col>=0)&(col<w)&(row>=0)&(row<h)
            cc=np.clip(np.rint(col[inside]).astype(int),0,w-1)
            rr=np.clip(np.rint(row[inside]).astype(int),0,h-1)
            px=dist[rr,cc]
            return {
                "n":int(len(pset)),"inside_pct":round(float(inside.mean()*100),2),
                "median_pixel_error":round(float(np.median(px)),3) if len(px) else None,
                "p90_pixel_error":round(float(np.percentile(px,90)),3) if len(px) else None,
                "mean_pixel_error":round(float(np.mean(px)),3) if len(px) else None
            }

        all_eval=eval_points(pts)
        counties=[]
        norr=None
        for ci in county_info:
            ev=eval_points(ci["points"])
            rec=ci["record"]
            row={"record":rec,**ev}
            counties.append(row)
            recstr=" ".join(str(v) for v in rec.values()).lower()
            if "norrbotten" in recstr or any(str(v)=="25" for v in rec.values()):
                norr=row

        # Approx metres/pixel based on affine Jacobian.
        A=np.array([[par[0],par[1]],[par[3],par[4]]],float)
        singular=np.linalg.svd(A,compute_uv=False)
        m_per_px=[float(1/s) for s in singular if s>0]
        mean_mpp=float(np.mean(m_per_px))
        for ev in [all_eval,norr] if norr else [all_eval]:
            if ev:
                ev["median_error_km_approx"]=round(ev["median_pixel_error"]*mean_mpp/1000,2)
                ev["p90_error_km_approx"]=round(ev["p90_pixel_error"]*mean_mpp/1000,2)

        report={
            "smhi_layer":SMHI,
            "scb_source":SCB,
            "scb_crs":"EPSG:3006 (source page states SWEREF 99 TM)",
            "image_size":[w,h],
            "mask_mode":mask_mode,
            "mask_pixels":int(mask.sum()),
            "selected_shapefile":str(p.name),
            "shapefile_feature_count":len(sf),
            "shapefile_fields":fields,
            "candidate_shapefiles":[{"score":s,"features":nn,"name":pp.name,"fields":ff} for s,nn,pp,ff in scored[:20]],
            "affine_epsg3006_to_pixel":{
                "col":"a*x + b*y + c","row":"d*x + e*y + f",
                "a":float(par[0]),"b":float(par[1]),"c":float(par[2]),
                "d":float(par[3]),"e":float(par[4]),"f":float(par[5])
            },
            "approx_metres_per_pixel":round(mean_mpp,1),
            "fit_all_counties":all_eval,
            "fit_norrbotten":norr,
            "county_evaluations":counties
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        print(json.dumps({
            "image_size":[w,h],"mask_pixels":int(mask.sum()),
            "selected_shapefile":p.name,"features":len(sf),
            "affine":report["affine_epsg3006_to_pixel"],
            "approx_metres_per_pixel":report["approx_metres_per_pixel"],
            "all":all_eval,"norrbotten":norr
        },ensure_ascii=False,indent=2,default=str))

if __name__=="__main__":
    main()
