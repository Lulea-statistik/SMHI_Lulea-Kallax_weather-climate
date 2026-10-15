# Flera SMHI-stationer – oberoende uppdatering

Detta flöde kompletterar, men ersätter inte, befintliga Kallax-jobbet `update-smhi.yml`.

## Körning
GitHub Actions → **Update SMHI station observations** → Run workflow.
- `update`: hämtar senast tillgängliga observationer.
- `bootstrap`: hämtar korrigerat historiskt arkiv och senaste observationer.
- `stations`: valfri kommaseparerad lista SMHI-ID.
- `parameters`: valfri kommaseparerad lista parameter-ID.

Lägg till eller ta bort kombinationer i `config/stations.json`. Kontrollera att respektive SMHI-station verkligen stöder parametern innan den inkluderas.

## Datamodell
En rad per observation med `station_id`, `parameter_id`, tidpunkt, enhet, värde och kvalitetsmarkering.
Lagring: `data/stations/<station_id>/parameter_<parameter_id>.csv`.
Importen deduplicerar på observationsintervallets start/slut och bevarar tidigare poster. Senare observationer får uppdatera tidigare värden (SMHI kan korrigera data).
Resultat och eventuella fel loggas i `metadata/stations_last_run.json`.

**Separat från produktionsflödet:** Webbplatsen läser fortfarande huvuddata från `docs/dashboard_data.json`; nederbördsstationernas separat byggda fil `docs/precip_stations.json` skapas av nuvarande stora workflow. Detta nya flöde uppdaterar i första versionen bara råobservationer. För att koppla fler stationsparametrar till diagrammen behövs ett separat byggsteg som konsumerar `data/stations`. Stationernas temperatur och nederbörd får inte blandas med olika enheter, observationstidpunkter eller otillräcklig täckning.

## Kvalitetsregler inför kommunmedel
- Separera mätvariabler och observationstyper (t.ex. 24-timmarsnederbörd kontra timnederbörd).
- Redovisa antal stationer per tidsperiod, deras datatäckning och eventuella byte av underlag.
- Tillämpa variabelspecifik aggregering: temperaturmedel från observationer, nederbördssumma av jämförbara dygnsvärden. Inkludera inte ofullständiga månader som fullständiga.
- Använd inte beteckningen geografiskt representativt kommunmedel för ett enkelt oviktat stationsmedel.
- Utför inte en ny lång `bootstrap` samtidigt som `update-smhi.yml` körs, eftersom arbetsflödena har separata lås och därmed kan konkurrera om Git-skrivningar.
