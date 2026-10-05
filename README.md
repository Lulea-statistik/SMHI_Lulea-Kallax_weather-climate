# SMHI-Kallax-vaderdata

Automatisk historik och daglig uppdatering av meteorologiska observationer från SMHI för **Luleå-Kallax Flygplats (station 162860)**.

## Vad som hämtas

Konfigurationen finns i `config/parameters.json`. Grunduppsättningen innehåller temperatur, vind, nederbörd, luftfuktighet, snödjup, lufttryck, sikt, rådande väder, molnmängd, byvind och daggpunkt.

Om en parameter inte finns för stationen hoppas den över och status skrivs till `metadata/parameters.csv`.

## Historik och daglig uppdatering

Första körningen använder `corrected-archive` tillsammans med den längsta tillgängliga aktuella perioden, normalt `latest-months`.

Därefter kör GitHub Actions varje dag kl. **04:30 UTC**. Den dagliga körningen hämtar den aktuella perioden igen och deduplicerar på observationens start- och sluttid. Den första dagen i varje månad gör `auto` dessutom en full arkivuppdatering.

Manuell körning finns under **Actions > Update SMHI Kallax weather data > Run workflow**.

Körlägen:

- `auto` - bootstrap om data saknas, annars daglig uppdatering; den 1:a i månaden full uppdatering
- `bootstrap` - historiskt arkiv + aktuell period
- `update` - aktuell period
- `refresh-all` - historiskt arkiv + aktuell period igen

## Dataformat

Data sparas årsvis per parameter, till exempel:

```text
data/parameter_1/2025.csv
data/parameter_1/2026.csv
data/parameter_4/2026.csv
```

`data/manifest.csv` listar samtliga datafiler, antal rader och min/max-datum.

Varje observationsfil innehåller bland annat:

- `station_id`, `station_name`
- `parameter_id`, `parameter_name`, `parameter_summary`, `unit`
- `datetime_utc`
- `datetime_local` i Europe/Stockholm
- `value`, `quality`
- `source_period`

## Power BI

I `powerbi/PowerQuery_M.txt` finns en Power Query som läser `data/manifest.csv` och kombinerar alla års-/parameterfiler till en tabell.

## Källa

SMHI Open Data, MetObs API. Station: Luleå-Kallax Flygplats, id 162860.


## Viktig teknisk detalj

SMHI använder två olika tidsfält i MetObs-svaren:

- `date` för punktobservationer, till exempel temperatur och vind
- `from`/`to` för intervallobservationer, till exempel nederbörd

Importskriptet hanterar båda. `value` sparas alltid som text och `value_numeric` fylls när värdet kan tolkas numeriskt. Det gör att även kodade eller textbaserade observationer kan bevaras utan att Power BI tvingar dem till tal.

API-basen använder `version/latest`. Efter varje körning kontrolleras dessutom hur många konfigurerade parametrar som faktiskt gav data. Om färre än hälften ger data markeras workflowet som misslyckat, även om de filer som gick att hämta först har sparats för felsökning.


## Historiskt arkiv

SMHI:s `corrected-archive` beter sig annorlunda än de aktuella JSON-perioderna. Skriptet försöker därför först API:ets CSV-resurs för perioden och använder vid behov SMHI:s stream-nedladdning som reservväg. CSV-filen innehåller metadata före själva datatabellen; importen hittar automatiskt tabellhuvudet och hanterar både:

- punktobservationer: `Datum` + `Tid (UTC)`
- intervallobservationer: `Från Datum Tid (UTC)` + `Till Datum Tid (UTC)`

Historiskt arkiv hämtas endast vid `bootstrap` och `refresh-all`, samt automatiskt den första dagen i varje månad när körläget är `auto`.


## Blixtdata

Rapporten har ett separat flöde för SMHI:s historiska blixtarkiv. `scripts/fetch_lightning.py` läser Atomflödet för historiska urladdningar från 2012 och framåt och sparar endast observationer inom Luleå kommun.

Geografin byggs från SCB:s öppna WFS-data. DeSO 2025 används som landmask och kommungeometrin som yttre analysområde. Landytor klassificeras som fastland eller öar och kommunens vattenyta delas i hav respektive inlandsvatten. Observationer inom 500 meter från land-/vattenkant klassas separat som `coast_uncertain` för att hantera SMHI:s positionsosäkerhet.

Detta är en första analysgeometri. SCB:s geometri är användbar för rapporten men bör senare ersättas med Lantmäteriets mer exakta geometri om sådan görs tillgänglig i projektet.

SMHI anger också ett metodbrott i blixtlokaliseringssystemet under 2014, vilket måste beaktas vid trendtolkning.


### Effektiv blixtuppdatering

Efter att den historiska blixtserien har hämtats en gång används den sparade historiken som bas. Normala `auto`- och `update`-körningar traverserar inte längre SMHI:s historiska arkiv från 2012. I stället hämtas endast de senaste 14 dagarnas dagliga CSV-resurser direkt, vilket även fångar sena rättningar utan att göra tusentals historiska anrop.

`bootstrap` och `refresh-all` är de enda lägen som hämtar hela historiken. Vid full historikhämtning används enbart CSV-representationen av varje dag, inte parallella CSV/JSON/XML-kopior.
