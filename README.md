# Telescoop Calendar Hub

## Schooljaar 2027–2028 (24 november 2026)

De conceptkalender is beschikbaar via `/kalender-schooljaar/2027-2028` en de
bestaande dageditor. De gewone `/smartschool-calendar` toont deze datums pas vanaf
24 juni 2027, 00.00 uur Belgische tijd. Vanaf die datum wordt de zichtbare horizon
automatisch uitgebreid tot augustus 2028; bestaande afspraken blijven behouden.
De datum zit ook in de bestaande cache-identiteit, zodat publicatie geen herstart
of nieuwe deployment vereist.

Teamvergaderingen: dinsdag 7 september 2027 en vervolgens telkens na vier
schoolweken. Volledige vakantieweken tellen niet mee; een week met één feestdag
blijft een schoolweek. De onderzoeksreeksen lopen op 12/19/26 november 2027 en
4/11/18 februari 2028 (één namiddag en twee keer één uur). Vragen verzamelen start
op maandag 4 oktober en 20 december; doorgeven uiterlijk 8 oktober en 24 december,
vier schoolweken vóór de start. Het agendapunt staat op de voorafgaande
teamvergadering van respectievelijk 7 september en 7 december.

`app/school_year_2027.py` voegt het plan eenmalig en transactioneel toe, met een
SQLite-back-up en auditlog. Een herstart overschrijft geen latere bewerkingen.
De officiële Vlaamse schoolvakanties zijn de bron; schoolspecifieke vrije dagen
en pedagogische studiedagen moeten later worden toegevoegd wanneer die vastliggen.
`tests/school_year_2027_smoke.py` controleert de berekende datums, vakantie-onderbrekingen,
conceptweergave, de publicatiegrens met een warme cache en behoud van bestaande data.

## Opsommingstekens (15 oktober 2026)

Elk tekstvak heeft een knop **• Opsomming**. Selecteer regels om ze in een lijst te zetten of plaats de cursor in een regel; Enter maakt binnen een lijst een nieuw punt. Bestaande regels die beginnen met `* ` of `• ` verschijnen als echte opsommingen, ook in de bewerkingsvakken. Agendapunten blijven bij hun vergadering. De opslag bewaart lijstpunten als afzonderlijke regels met `• `, zodat de bestaande sortering, versiecontrole, tekstvervanging en het auditlog blijven werken. Links en opmaak blijven behouden. De weergavewijziging vereist geen migratie van de kalendergegevens.

Controle: `tests/bullets_smoke.py` controleert twee vergaderingen met hun eigen agenda, bestaande sterretjes, nieuwe lijsten in meerdere vakken, links, opnieuw openen en bewaren zonder onnodige wijzigingen, behoud van stages en het schonen van onveilige HTML.

## Actuele dagkaarten (14 oktober 2026)

De bestaande `/smartschool-calendar`-URL toont de volledige kalender als responsieve dagkaarten. Dagbalken gebruiken de bestaande maandgradiënten; alle vakken hebben een witte achtergrond. Afwezigheden en vervangingen staan bovenaan, het dagprogramma en praktische afspraken in de hoofdkolom, overleg met zijn agendapunten bij elkaar en stages in een aparte kolom. Op een smal scherm komen de vakken onder elkaar. Praktische afspraken hebben een groene rand; uitstappen hebben gewone tekst. De uurkolom is breed genoeg voor een volledig bereik op één regel en heeft geen scheidingslijnen tussen regels. Nascholingen zonder opgegeven dagdeel, expliciete volledige dagen en bosklassen voor een hele klas krijgen DAG. De regelafstand in alle vakken is 1,15; de activiteitstekst is zwart. Maand-, dag- en vaktitels en klasgroepen in het dagprogramma zijn vet. Overleg heeft rand en titel #D31996, praktische afspraken #68991C en afwezigheden #E02020. Het stagevak blijft ook op dagen met uitsluitend stages in de rechterkolom; de overbodige tekst Stage verschijnt niet in de regels.

De migratie voegt uitsluitend `activity_type` en `whole_day` aan `editor_lines` toe. Bestaande tekst, record-ID's, verwijzingen en versies blijven behouden. Nieuwe toevoegingen bewaren de gekozen typecategorie, die bij het renderen voorrang krijgt op tekstherkenning. De optie Hele dag zet DAG in de tijdkolom. Bewerkingen van één regel, volledige dagen en batchvervangingen houden deze metadata bij. De oude regels met type `auto` worden op hun bestaande tekst ingedeeld. De kalender gebruikt één DOM voor desktop en mobiel, dezelfde dagelijkse verwijdering van oude dagen en dezelfde ETag-cache.

## Bewerken met dezelfde dagindeling

`/kalender-wijzigen` toont dezelfde dagvakken, klasnadruk, maandgradiënten en regelafstand als de Smartschoolkalender. Het overzicht en de kalender gebruiken dezelfde renderer. Dagversies en de zichtbare kaarten worden uit dezelfde databaselezing opgebouwd. Zoeken toont de volledige dag; de dagvensters bevatten vijf aparte tekstvakken. Een knop Wijzigen bij elk gevuld vak opent meteen het betreffende tekstvak. Het gekozen vak bepaalt waar nieuwe of verplaatste regels terechtkomen; ongemoeid gelaten vakken behouden hun records. Ongewijzigde gestructureerde activiteiten behouden hun uren en metadata. De opslag blijft transactioneel en weigert verouderde dagversies. De oude voorstellenpagina en zijn navigatieknop zijn verwijderd.

Via Maandfocus wijzigen kan de focusregel van iedere getoonde maand worden aangepast. `/kalender-maandfocus/{YYYY-MM}` bewaart een geversioneerde override in de bestaande settings. Gelijktijdige wijzigingen worden geweigerd met HTTP 409 en oorspronkelijke teksten blijven in het auditlog bewaard.

## Zoeken en vervangen (14 oktober 2026)

`/kalender-vervangen` vervangt een stukje tekst of een volledige zichtbare regel, vanaf vandaag, in de hele kalender of in een gekozen periode. De voorafgaande vergelijking toont iedere gewijzigde regel met datum, oude tekst en nieuwe tekst; tot bevestiging blijven de gegevens onaangeroerd. Hoofdlettergevoelig zoeken is optioneel. Kleuren, links en niet-gematchte regels blijven behouden.

Een ondertekend voorbeeld blijft een uur geldig. De applicatie berekent de volledige verzameling wijzigingen opnieuw binnen één SQLite-schrijftransactie. Gewijzigde, verwijderde of nieuwe treffers laten de hele bewerking stoppen met HTTP 409. Het auditlog bewaart de originele records. De succespagina biedt een uur lang ongedaan maken; dit herstelt de hele bewerking alleen als alle betrokken records nog overeenkomen. Zoals bij de bestaande dagbewerking wordt een gewijzigde zichtbare tekst van een gestructureerde activiteit opgeslagen als kalenderregels; het oorspronkelijke event met zijn metadata blijft verborgen bewaard. Ongewijzigde gestructureerde activiteiten blijven intact.

## Actuele publieke kalender (30 september 2026)

De Railway-service start met `app.simple_calendar:app`. De oorspronkelijke SQLite-databank en JSON-kalender op `/data` blijven behouden. De eerste start bewaart een databasekopie en zet de bestaande kalenderregels transactioneel in bewerkbare regels om; latere starts importeren ze niet opnieuw. Bestaande toevoegingen uit `events` blijven beschikbaar.

- `/`: de module **Toevoegen aan kalender** voegt meerdere regels in één keer toe op één datum. Iedere regel blijft apart bewerkbaar. De invoermodule in gewone Nederlandse taal is uit dit scherm verwijderd.
- `/kalender-wijzigen`: zoeken, wijzigen en bevestigd verwijderen van oorspronkelijke en later toegevoegde activiteiten. Wijzigingsversies voorkomen dat twee open formulieren elkaar stilzwijgend overschrijven.
- `/kalender-links`: omschrijvingen en links toevoegen, aanpassen en verwijderen.
- `/smartschool-calendar`: dezelfde Smartschool-URL, met alle verwijzingen onder het logo en `🔗 Kalender wijzigen` boven de kalender. Verversing elke 7200 seconden, Aptos met lokaal geleverde Roboto-reserve.

Tekst en links worden bij opslaan geschoond. De HTML-editor kan geen scripts invoegen. Bestaande opmaak blijft in SQLite behouden; de kalender bepaalt de zichtbare tekst-, titel- en randopmaak per vak. Linkomschrijvingen hebben hun eigen editor.

Bij toevoegen bepaalt Type in welk dagvak een activiteit komt; de activiteitstekst blijft zwart. Automatisch per regel blijft beschikbaar. Uitstappen behouden hun vaste notatie; overige types accepteren vrije tekst zonder verplichte klasgroep of uren. Een expliciete hele dag verschijnt als DAG.

Stage-uren staan achter of onder de naam en gebruiken Belgische tijd. Bestaande titels, klasvermeldingen en opgeslagen uren blijven behouden. Er worden geen uren verzonnen voor stages zonder opgegeven tijden.

Deze schermen zijn bewust voor iedereen met de URL bruikbaar, zonder account of toegangscode. Verwijderen verbergt een regel; de oorspronkelijke gegevens en het auditlog blijven bewaard. De kalender rendert uit een cache die na elke databasewijziging ongeldig wordt; ongewijzigde browseraanvragen ontvangen HTTP 304. Er is geen achtergrondpolling of betaalde AI-API.

Bij de eerste ingebruikname kan `CALENDAR_LINKS_GZ_B64` de aangeleverde verwijzingen bevatten (gzip + base64 van JSON met `description` en `url`). Die schoolgegevens staan niet in nieuwe bronbestanden. Daarna zijn wijzigingen in de database leidend.

Controle: alle acht Python-smoketests slagen, inclusief meervoudig toevoegen, gedeeltelijk verwijderen, bestaande activiteiten wijzigen, behoud bij herstart, conflicten, links en HTML-validatie. Een afzonderlijke controle met de actuele online kalender behield de volledige tekst van alle 158 getoonde dagen. In Smartschool wordt de bestaande iframe-URL gebruikt. Minder verversen en Railway Serverless verminderen verbruik; dit garandeert geen onbeperkt gratis hosting.

De onderstaande documentatie beschrijft daarnaast de oorspronkelijke account- en integratiemogelijkheden; deze zijn niet nodig voor de publieke kalender.

Interne kalenderhub voor GO! BS De Telescoop. Doel: directie, secretariaat en zorg kunnen activiteiten in gewone Nederlandse zinnen invoeren, controleren en opslaan. Zodra Smartschool de ontbrekende Planner-scope en endpoints levert, kunnen directie en secretariaat dezelfde activiteiten rechtstreeks naar Smartschool Planner publiceren.

## Wat werkt al zonder Smartschool Planner API
- aanmelden met eigen account;
- rollen `director`, `secretary`, `care`;
- natuurlijke-taalinterpretatie met veilige deterministische parser;
- gestructureerde preview vóór opslaan;
- conceptactiviteiten opslaan;
- zoeken en filteren;
- dubbele afspraken signaleren;
- auditlog;
- gebruikersbeheer door directie;
- persoonlijke API-key voor een latere ChatGPT connector;
- dynamische, beveiligde kalenderweergave via `/embed?token=...`;
- OAuth2-structuur voor Smartschool;
- Smartschool dry-run: mapped payload wordt gelogd, maar er gebeurt geen write.

## Rechten
- Directie: alles, inclusief Smartschool-instellingen, gebruikers, publiceren.
- Secretariaat: activiteiten beheren en publiceren.
- Zorg: concepten aanmaken en eigen concepten beheren; kan server-side niet publiceren.

## Eerste lokale start
1. `cp .env.example .env`
2. Maak `APP_SECRET` lang en willekeurig.
3. Vul `BOOTSTRAP_ADMIN_PASSWORD` in.
4. `pip install -r requirements.txt`
5. `uvicorn app.main:app --reload`
6. Open `http://localhost:8000`.

De bootstrapbeheerder is standaard `rob.huijghe@detelescoop.be`; hij wordt alleen automatisch aangemaakt wanneer `BOOTSTRAP_ADMIN_PASSWORD` is ingevuld.

## Smartschool
Het platform staat vooraf op `https://telescoop-sgr8.smartschool.be`.
De publiek gedocumenteerde OAuth-paden zijn vooraf ingevuld:
- `/OAuth`
- `/OAuth/index/token`

Planner-scope en Planner list/create/update/delete endpoints blijven bewust leeg tot Smartschool ze officieel levert. De app kan niet per ongeluk live gaan zonder clientgegevens, alle Planner-endpoints én een geldige Smartschoolverbinding.

## Dynamische HTML in Smartschool
De instellingenpagina toont een iframe-snippet voor een dynamische kalenderweergave. Die hoeft maar één keer in Smartschool te worden geplaatst. Als Smartschool in het betreffende HTML-veld iframes blokkeert/sanitiseert, gebruik dezelfde URL als gewone beveiligde weblink; de Planner API blijft de voorkeursroute voor echte kalenderitems.

## ChatGPT connector
Maak in Instellingen een persoonlijke API-key. De connectorbeschrijving is beschikbaar op:

`/connector-openapi.json`

De API gebruikt `Authorization: Bearer tch_...`.

## Staking maandag 23 november 2026

Een eenmalige, transactionele kalendermigratie in `app/strike_nov23_2026.py` maakt maandag 23 november 2026 vrij en toont uitsluitend **School gesloten wegens staking**. De vakgroep kleuter van 15.30–17.00 uur, inclusief de agenda over bakjestijd, voorkennis en woordenschatonderwijs, verhuist met behoud van oorspronkelijke gegevens naar maandag 30 november. De overige afspraken van 23 november worden in de publieke kalender verborgen, maar blijven herstelbaar in de databaselog en SQLite-back-up. De wijzigingen worden alleen op `/data` uitgevoerd en zijn eenmalig.
