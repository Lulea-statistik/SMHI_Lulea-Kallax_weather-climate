# SMHI algae: source and classification audit (2026-11-09)

## Confirmed sources

- The site's importer uses the vector WFS endpoint `https://opendata-view.smhi.se/algae/wfs`, layer `algae:SR.SeaSurfaceArea`.
- SMHI's separately documented Algae Maps download API at `https://opendata-download-algae.smhi.se/api` serves **daily map images**, weekly map images, and Swedish/English reports. Documentation: https://opendata.smhi.se/apidocs/algae/index.html
- This distinction matters: a WFS feature class cannot be assumed equivalent to the colors or spatial detail of the rendered daily map.

## Verified repository findings (2026)

- The saved 2026 manifest contains 86 observation dates: raw `class_1` on 85 dates, `class_4` on one.
- 2026-06-19: `class_4` is reported for 100% of the municipal sea polygon.
- 2026-06-25: `class_1` covers 77.48% of that polygon.
- In the checked 2026 GeoJSON features, `surface`, `sub_surfac`, `cloud`, `no_data`, and `color_hex` are all null. Therefore the names of raw class 1 and class 4 are **not verified**.
- Never treat an unrecognized class as proof of no algae.

## Follow-up before semantic relabeling

1. Obtain authoritative numeric value definitions for `class` in this exact WFS layer from SMHI (or its published schema / styling configuration).
2. Compare WFS polygons with the official daily *image* for 2026-06-19 and 2026-06-25 using the same spatial extent.
3. If spatial patterns differ, source the correct underlying classification grid / vector layer rather than assigning names to the current coarse polygons.
4. Preserve the original geometry CRS and the requested WFS output CRS separately. The current script explicitly requests WFS EPSG:4326 and performs area calculations in EPSG:3006; validate those properties before any alternative pipeline.
5. If a raster-based overlay is later implemented, perform full raster reprojection to the Leaflet display CRS (EPSG:3857), not just transformed bounds.
6. Reprocess historical years only when class meanings and source equivalence are established.

## Safe ingestion update

`scripts/fetch_algae.py` now pages WFS queries with `startIndex` and `count`, rather than truncating annual requests at 10,000 features or trusting the daily default. It checks `numberMatched` where provided and fails on apparent repeated pages. This change does not alter classification labels.
