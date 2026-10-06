#!/usr/bin/env python3
"""Match SMHI snow observation marker pixels to known local station coordinates."""

from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"smhi_snow_station_georef.json"
COMP=ROOT/"docs"/"snowgrid"/"smhi_snow_obs_components.json"
FIT=ROOT/"docs"/"snowgrid"/"smhi_snow_georef_fit.json"
INDEX=ROOT/"docs"/"snowmap"/"index.json"
SEASON=ROOT/"docs"/"snowmap"/"2025-26.json"
DATE="2026-02-15"

TO3006=Transformer.from_crs("EPSG:4326","EPSG:3006",always_xy=True)

def aff_apply(p,xy):
    a,b,c,d,e,f=p
    x=xy[:,0]; y=xy[:,1]
    return np.column_stack((a*x+b*y+c,d*x+e*y+f))

def fit_affine(xy,uv):
    X=np.column_stack((xy[:,0],xy[:,1],np.ones(len(xy))))
    cu,*_=np.linalg.lstsq(X,uv[:,0],rcond=None)
    rv,*_=np.linalg.lstsq(X,uv[:,1],rcond=None)
    return np.array([cu[0],cu[1],cu[2],rv[0],rv[1],rv[2]],float)

def main():
    comps=json.loads(COMP.read_text(encoding="utf-8"))["components"]
    # Small repeated 9x7-ish objects are treated as station markers.
    marks=[c for c in comps if 8<=c["width"]<=10 and 6<=c["height"]<=8 and c["visible_pixels"]>=18]
    uv=np.array([[c["centroid_col"],c["centroid_row"]] for c in marks],float)

    idx=json.loads(INDEX.read_text(encoding="utf-8"))
    meta={str(s["id"]):s for s in idx["stations"]}
    seas=json.loads(SEASON.read_text(encoding="utf-8"))
    obs=[r for r in seas["observations"] if r.get("date")==DATE and str(r.get("station_id")) in meta]
    # Unique station list for date.
    ids=sorted({str(r["station_id"]) for r in obs})
    stations=[]
    for sid in ids:
        s=meta[sid]
        x,y=TO3006.transform(float(s["longitude"]),float(s["latitude"]))
        stations.append({"id":sid,"name":s["name"],"x":x,"y":y,"lat":s["latitude"],"lon":s["longitude"]})
    xy=np.array([[s["x"],s["y"]] for s in stations],float)

    g=json.loads(FIT.read_text(encoding="utf-8"))["affine_epsg3006_to_pixel"]
    p=np.array([g["a"],g["b"],g["c"],g["d"],g["e"],g["f"]],float)

    history=[]
    pairs=None
    # Iterative nearest one-to-one matching + robust refit.
    for it in range(8):
        pred=aff_apply(p,xy)
        D=np.sqrt(((pred[:,None,:]-uv[None,:,:])**2).sum(axis=2))
        rr,cc=linear_sum_assignment(D)
        cand=[(int(i),int(j),float(D[i,j])) for i,j in zip(rr,cc) if D[i,j] <= 18.0]
        if len(cand)<3: break
        src=np.array([xy[i] for i,j,d in cand],float)
        dst=np.array([uv[j] for i,j,d in cand],float)
        pnew=fit_affine(src,dst)
        resid=np.sqrt(((aff_apply(pnew,src)-dst)**2).sum(axis=1))
        # reject clear mismatches
        med=float(np.median(resid))
        keep=resid <= max(2.5,med*2.5)
        if keep.sum()>=3 and keep.sum()<len(keep):
            pnew=fit_affine(src[keep],dst[keep])
            cand=[c for c,k in zip(cand,keep) if k]
        history.append({"iteration":it+1,"candidate_pairs":len(cand),"median_residual_px":round(float(np.median(np.sqrt(((aff_apply(pnew,np.array([xy[i] for i,j,d in cand]))-np.array([uv[j] for i,j,d in cand]))**2).sum(axis=1)))),3)})
        if np.max(np.abs(pnew-p))<1e-9:
            p=pnew; pairs=cand; break
        p=pnew; pairs=cand

    if not pairs or len(pairs)<3:
        raise RuntimeError(f"Too few marker/station matches: {0 if not pairs else len(pairs)}")

    src=np.array([xy[i] for i,j,d in pairs],float)
    dst=np.array([uv[j] for i,j,d in pairs],float)
    pred=aff_apply(p,src)
    resid=np.sqrt(((pred-dst)**2).sum(axis=1))

    # local metres/pixel from affine Jacobian
    A=np.array([[p[0],p[1]],[p[3],p[4]]],float)
    sv=np.linalg.svd(A,compute_uv=False)
    mpp=float(np.mean([1/s for s in sv if s>0]))

    matches=[]
    for (i,j,d),r in zip(pairs,resid):
        matches.append({
            "station_id":stations[i]["id"],"station_name":stations[i]["name"],
            "latitude":stations[i]["lat"],"longitude":stations[i]["lon"],
            "marker_component_id":marks[j]["id"],
            "marker_col":marks[j]["centroid_col"],"marker_row":marks[j]["centroid_row"],
            "initial_match_distance_px":round(d,3),
            "final_residual_px":round(float(r),3),
            "final_residual_km_approx":round(float(r*mpp/1000),2)
        })

    report={
        "date":DATE,
        "marker_count":len(marks),
        "observing_local_station_count":len(stations),
        "matched_control_points":len(matches),
        "method":"iterative one-to-one marker matching initialized from county affine, robust affine refit",
        "affine_epsg3006_to_pixel":{
            "a":float(p[0]),"b":float(p[1]),"c":float(p[2]),
            "d":float(p[3]),"e":float(p[4]),"f":float(p[5])
        },
        "approx_metres_per_pixel":round(mpp,1),
        "median_residual_px":round(float(np.median(resid)),3),
        "p90_residual_px":round(float(np.percentile(resid,90)),3),
        "median_residual_km_approx":round(float(np.median(resid)*mpp/1000),2),
        "p90_residual_km_approx":round(float(np.percentile(resid,90)*mpp/1000),2),
        "iterations":history,
        "matches":matches
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
