#!/usr/bin/env python3
"""Verify practical equivalence of SCB municipality PRJ to EPSG:3006 over Lulea."""

from __future__ import annotations
import io,json,tempfile,zipfile
from pathlib import Path
import requests,numpy as np,shapefile
from pyproj import CRS,Transformer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"snowgrid"/"scb_lulea_crs_equivalence.json"
SCB="https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip"
TIMEOUT=90

def dl(url):
    r=requests.get(url,timeout=TIMEOUT,headers={"User-Agent":"Lulea-statistik-SCB-CRS-check/1.0"})
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
    with tempfile.TemporaryDirectory() as td:
        root=expand(td)
        shp=next(root.rglob("Kommun_Sweref99TM.shp"))
        prj=shp.with_suffix(".prj").read_text(encoding="utf-8",errors="replace")
        src=CRS.from_wkt(prj)
        sf=shapefile.Reader(str(shp),encoding="cp1252")
        fields=[f[0] for f in sf.fields[1:]]
        target=None
        for sr in sf.iterShapeRecords():
            rec=dict(zip(fields,list(sr.record)))
            code=str(rec.get("KnKod") or rec.get("knkod") or rec.get("KNKOD") or "").strip()
            name=str(rec.get("KnNamn") or rec.get("knnamn") or rec.get("KNNAMN") or "").strip()
            if code=="2580" or name.lower()=="luleå":
                target=sr.shape; break
        if target is None: raise RuntimeError("Lulea not found")

        pts=np.asarray(target.points,float)
        # Transform source CRS -> EPSG:3006. If operationally the same, coordinates should barely move.
        tr=Transformer.from_crs(src,"EPSG:3006",always_xy=True)
        X,Y=tr.transform(pts[:,0],pts[:,1])
        out=np.column_stack([X,Y])
        delta=np.sqrt(((out-pts)**2).sum(axis=1))

        # Also compare geographic transforms at representative vertices.
        to_ll_src=Transformer.from_crs(src,"EPSG:4326",always_xy=True)
        to_ll_3006=Transformer.from_crs("EPSG:3006","EPSG:4326",always_xy=True)
        idx=np.linspace(0,len(pts)-1,min(100,len(pts)),dtype=int)
        lon1,lat1=to_ll_src.transform(pts[idx,0],pts[idx,1])
        lon2,lat2=to_ll_3006.transform(pts[idx,0],pts[idx,1])
        geodiff_deg=np.sqrt((np.asarray(lon1)-np.asarray(lon2))**2+(np.asarray(lat1)-np.asarray(lat2))**2)

        report={
            "source_file":shp.name,
            "source_wkt_prefix":prj[:700],
            "pyproj_equals_epsg3006":bool(src.equals(CRS.from_epsg(3006),ignore_axis_order=True)),
            "vertex_count":int(len(pts)),
            "coordinate_shift_to_epsg3006_m":{
                "max":float(delta.max()),
                "mean":float(delta.mean()),
                "p95":float(np.percentile(delta,95))
            },
            "geographic_difference_deg":{
                "max":float(geodiff_deg.max()),
                "mean":float(geodiff_deg.mean())
            },
            "operationally_equivalent_within_1m":bool(delta.max()<=1.0),
            "operationally_equivalent_within_10m":bool(delta.max()<=10.0)
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
