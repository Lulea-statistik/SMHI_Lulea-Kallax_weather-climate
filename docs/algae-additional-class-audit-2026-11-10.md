# Utvidgad WFS-klassgranskning – Östersjön, 2026-11-10

Källa: [Discover additional SMHI algae classes #1](https://github.com/Lulea-statistik/SMHI_Lulea-Kallax_weather-climate/actions/runs/42790958191) (36 WFS-frågor, körningsstatus `success`, 0 rapporterade fel).

Artifact: [algae-additional-classes-audit](https://github.com/Lulea-statistik/SMHI_Lulea-Kallax_weather-climate/actions/runs/42790958191/artifacts/13750494054), fil `additional-classes-audit.json`.

## Preliminär klassnyckel

| WFS-fält `class` | Punktjämförelse med WMS | Bedömning |
|---:|---|---|
| 1 | Grå (122,122,122,255) i 5 lokala provpunkter i Audit #7 | Förenligt med **moln** |
| 2 | Oftast gul (255,255,0,255) i provpunkter i denna körning | Förenligt med **risk för ytansamling** |
| 3 | Orange (255,153,0,255) i provpunkter i denna körning | Förenligt med **ytansamling** |
| 4 | Svart (0,0,0,204) i 2 lokala provpunkter i Audit #7 | Förenligt med **ingen data** |
| 5 | Inga träffar under 12 urval | Betydelse okänd, förekomst ej utesluten |

För klass 2 gav en kontrollpunkt den 15 juli 2025 i södra Östersjön **orangeaktig** WMS-färg (255,157,0,255) trots WFS-klass 2. Avvikelsen kan bero på bl.a. geometrigräns, WMS-symbolisering, överlapp eller annat; den är inte analyserad färdigt.

## Faktiska träffar

För 2026-06-25 i södra Östersjön: klass 2 `numberMatched=698`, klass 3 `numberMatched=355`; i norra Östersjön: 342 respektive 90. Båda klasserna gav 0 träffar i det provade området Bottniska viken för detta datum.

För 2026-07-15 i Bottniska viken: klass 2 `numberMatched=81`, klass 3 `numberMatched=173`. För 2025-07-15 i Bottniska viken: klass 2 `numberMatched=33`, klass 3 `numberMatched=2`. För 2019-08-15: en träff vardera för klass 2 och 3 i samma regionala utsnitt.

`numberMatched` är WFS-tjänstens träffantal per kombination av datum/klass/rektangel, **inte areal**, och utsnitten överlappar. Summera därför inte dessa rakt av. Skriptet hämtade högst 25 objekt per fråga och valde högst en representativ punkt för färgkontroll.

## Konsekvens för Luleås havsområde

Luleås publicerade lokala manifest domineras av klass 1 och enstaka klass 4, trots att klasserna 2 och 3 förekommer i den större havstjänsten. Det kan bero på geografisk täckning, datumurval eller import-/urvalsmetod. Resultaten visar **inte** ännu att algansamlingar har registrerats inom Luleås kommungräns vid dessa datum.

**Ingen produktionsomkodning eller historisk arealomräkning ska göras på denna granskning ensam.** Fortsatt QA: undersök den avvikande klass-2-punkten; kontrollera regionala WFS-geometrier mot Luleås faktiska vattengeometri; verifiera om WFS har ytterligare numeriska klasser och om den officiella Algae Maps-produkten är mer lämplig för yttäckande statistik.

För km² och procent måste källans koordinatsystem vara verifierat och arealer beräknas geodetiskt eller i lämplig projektion, inte via råpixelantal i en WMS-bild. Vid framtida interaktiv rastervisning krävs full reprojicering av hela rastergridet till kartans visnings-CRS (t.ex. EPSG:3857).
