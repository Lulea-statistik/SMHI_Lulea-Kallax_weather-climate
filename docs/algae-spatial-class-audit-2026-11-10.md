# Granskning av WFS-klass och WMS-färg – kontroll #7

Datum för kontroll: 2026-11-10  
GitHub Actions: https://github.com/Lulea-statistik/SMHI_Lulea-Kallax_weather-climate/actions/runs/42787730094  
Artifact: https://github.com/Lulea-statistik/SMHI_Lulea-Kallax_weather-climate/actions/runs/42787730094/artifacts/13748884800  
Datafil: `algae-service-audit/spatial-class-audit.json`

## Observerade resultat

| Datum | Lokala WFS-polygoner | Numerisk WFS-klass | Provpunkter med WMS-färg | Matchande WMS-färg (RGBA) |
|---|---:|---:|---:|---|
| 2026-06-19 | 1 | 4 | 1 | (0,0,0,204) |
| 2026-06-25 | 4 | 1 | 4 | (122,122,122,255) |
| 2019-08-15 | 1 | 4 | 1 | (0,0,0,204) |
| 2025-06-03 | 1 | 1 | 1 | (122,122,122,255) |

Alla sju representativa provpunkter fick synlig WMS-färg. Inga provpunkter flaggades som utanför bild eller transparenta i kontrollens rapport.

## Tolkning och begränsningar

- Klassen **4** sammanfaller på två kontrollerade punkter/år med WMS-färgen svart (alpha 204). Detta är **förenligt med** kategorin `ingen data`, men ingen officiell, fullständig kodnyckel för WFS-fältet `class` är verifierad.
- Klassen **1** sammanfaller på fem kontrollerade punkter/år med WMS-färgen grå (122,122,122,255). Detta är **förenligt med** kategorin `moln`, men ingen officiell, fullständig kodnyckel för WFS-fältet `class` är verifierad.
- Provpunkterna kommer från **lokalt klippta och förenklade WFS-GeoJSON-filer** i EPSG:4326 och jämförs med WMS 1.1.1-bilder i EPSG:4326 (longitude–latitude). Ett prov per polygon används; detta är **inte** en fullständig rumslig eller arealvägd validering.
- Datumurvalet testar endast klasserna 1 och 4. Även om det är konsekvent kan det inte belägga betydelsen av eventuella andra klasskoder, vilket behövs för att beskriva algförekomst och risk.
- Färgkopplingen säger inte att bildpixlarna kan summeras direkt till geografiska arealer. För andelar i km²/% krävs källverifierade kategorier och korrekt georefererad area-/rasteranalys.

## Beslut om produktion

**Ingen automatisk omkodning av WFS-klass 1/4 eller omräkning av befintliga arealtidsserier görs på denna evidens ensam.** Råklassvärdena ska kunna spåras tillbaka till WFS. Osäkra kategorier får inte beskrivas som fastställd algförekomst eller som verifierade nollvärden.

## Nästa metodsteg

1. Sök verifierad kodnyckel från SMHI eller testa datum/områden där WFS innehåller ytterligare klasskoder.
2. Testa flera **oberoende** provpunkter inom större polygoner, gärna slumpmässigt stratifierade och med kontroll av gränspixlar.
3. För arealstatistik: verifiera raster- och vektor-CRS och projektion. Klipp/maska i rasterts käll-CRS och reprojicera vid behov **hela rastergridet** till den faktiska visningsprojektionen (t.ex. EPSG:3857) före interaktiv rendering. Använd inte enbart transformerade bounds som approximation.
