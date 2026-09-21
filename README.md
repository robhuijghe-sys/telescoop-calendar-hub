# Telescoop Calendar Hub

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
