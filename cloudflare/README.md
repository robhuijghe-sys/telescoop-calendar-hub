# De Telescoop: gratis kalenderbasis

Een zelfstandige Cloudflare Worker met D1. Dit is de technische basis voor de kalender in het bestaande Smartschool-nieuwsbericht. De aangeleverde HTML is verwerkt in een gecontroleerde import; deze branch is nog geen vervanging voor de live Railway-kalender.

## Gedrag

- `/smartschool-calendar` is de vaste, in een iframe bruikbare leesweergave. De HTML laadt zichzelf na 1800 seconden opnieuw. Bezoekers hoeven daarvoor niet opnieuw aan te melden.
- `/beheer#sleutel=<lange-sleutel>` toont invoer in gewone Nederlandse taal, een controleformulier en een doorzoekbare lijst met een verwijderknop. Het fragment wordt uit de adresbalk verwijderd en de sleutel blijft enkel voor die browsersessie bewaard.
- `POST /api/manage/items` maakt een item aan. Een datum met dezelfde titel kan niet opnieuw worden toegevoegd. Een afspraak mag zonder uur worden ingevoerd.
- `DELETE /api/manage/items/:id` markeert precies één item als verwijderd. Een bevestiging in het beheerscherm gaat eraan vooraf. Een trigger schrijft dezelfde wijziging in het auditlog; een verwijderd item blijft in de database bewaard.
- Nieuw en geïmporteerd materiaal komt als afzonderlijke regels in `calendar_items`. Daardoor kan ook een oorspronkelijke kalenderregel gericht worden verwijderd. De import behoudt de tekstkleuren, nadruk, kalenderlinks, maandkleuren, seizoenen en focusregels.
- De datum- en kleurinterpretatie is lokaal en regelgebaseerd. Er is geen betaalde AI-API.

## Beveiliging en toegang

De leesweergave heeft, net als de huidige werkende route, geen inlogscherm. Iedereen met de publieke URL kan de getoonde gegevens bekijken. Plaats er daarom geen gegevens die uitsluitend binnen Smartschool zichtbaar mogen zijn. Een Smartschool-iframe geeft op zichzelf geen toegangscontrole aan de externe pagina.

De beheersleutel heeft minimaal 32 willekeurige tekens; gebruik bij voorkeur 32 random bytes als 64 hextekens. Alleen de SHA-256-hash staat als Cloudflare-secret `EDITOR_TOKEN_SHA256`. Het beheer werkt zonder gebruikerslogin maar de gedeelde sleutel geeft zowel toevoeg- als verwijderrecht. Wie individuele rechten en namen in het auditlog wil, kan later meerdere editor-sleutels krijgen. Geef de beheerlink nooit mee in de publieke kalenderpagina.

De code bevat geen kalenderinhoud of sleutels. De bron en gegenereerde import blijven buiten de publieke repository. De database wordt bij ingebruikname gevuld.

## Voorbereiding van een eigen gratis Cloudflare-account

1. Maak een D1-database `telescoop-kalender` en vervang `REPLACE_WITH_D1_DATABASE_ID` in `wrangler.jsonc` door het echte database-ID.
2. Voer `schema.sql` uit tegen die database (`npx wrangler d1 execute telescoop-kalender --remote --file=./schema.sql`).
3. Maak lokaal een lange willekeurige sleutel. Zet uitsluitend de SHA-256-hash als secret met `npx wrangler secret put EDITOR_TOKEN_SHA256`. Bewaar de oorspronkelijke sleutel veilig voor de persoonlijke beheerlink.
4. Publiceer met `npx wrangler deploy` vanuit deze map. De inbegrepen `*.workers.dev`-naam vereist geen apart domein. Bewaar de bestaande Railway-versie tijdens de controle.
5. Controleer de beheerpagina en de iframe-weergave met echte kalendergegevens. Wijzig de iframe-URL in Smartschool één keer, pas nadat ook de actuele HTML en de Railway-toevoegingen zijn overgezet en vergeleken.

Voor deze branch zijn stap 1–5 nog niet uitgevoerd: er is geen Cloudflare-account of D1-database verbonden. Een gratis account kan op de huidige voorwaarden tegen limieten aanlopen; gebruik geen betaald abonnement of automatische upgrade. De code draait zonder periodieke achtergrondprocessen. Bij een toekomstige migratie kan de database met Wrangler worden geëxporteerd; op het gratis D1-abonnement is herstel naar een moment binnen zeven dagen beschikbaar. Houd daarnaast zelf een export bij.

## Links beheren

Het beheer bevat Omschrijving en Link. Toevoegen, aanpassen van beide velden en bevestigd verwijderen gebruiken dezelfde beheersleutel. Onder het logo krijgen alle verwijzingen dezelfde opmaak met 🔗. Relatieve Smartschool-paden worden volledige Smartschool-adressen. Alleen HTTP(S) is toegestaan. De wijzigingen worden in dezelfde databasebewerking gelogd. Verwijderen bewaart het record, maar verbergt de link direct bij de volgende paginalaad; een open kalender ververst binnen 30 minuten.

## Import van de aangeleverde HTML

Vanuit deze map, na `npm ci`:

```sh
node scripts/import-html.mjs /pad/naar/bron.html 2026 private-import
npx wrangler d1 execute telescoop-kalender --remote --file=./schema.sql
npx wrangler d1 execute telescoop-kalender --remote --file=./private-import/import.sql
```

Geef het startjaar expliciet op. De importer controleert dat de weekdagen kloppen en dat alle zichtbare kalendertekst behouden blijft. Scripts, event handlers en onveilige linkprotocollen worden niet overgenomen. Lege dagen blijven aanwezig. Herhaalimport doet niets zodra een importbatch bestaat en herstelt dus geen verwijderingen of gewijzigde links. Een andere bronsnapshot achteraf vraagt een afzonderlijke, gecontroleerde migratie.

De ontvangen bron levert 152 kalenderdagen, 401 afzonderlijke regels en 7 links op. Bij Zorgoverleg verwijzen het icoon en de tekst naar twee verschillende bestemmingen; beide blijven behouden als document- en Smartschool-link. De SQL en het controlerapport staan lokaal in de uitgesloten map `private-import/` en zijn reproduceerbaar vanuit de oorspronkelijke bijlage. Publiceer deze schoolgegevens niet in GitHub.

Bij omschakeling blijven nodig: wijzigingen sinds deze bronsnapshot uit Railway vergelijken/overzetten, import in de echte D1-database, visuele vergelijking op desktop en mobiel, en controle van de definitieve Cloudflare-URL in het Smartschool-iframe. Pas daarna de iframe-URL wijzigen. De bestaande Railway-kalender blijft tot dan actief.

D1-file-import gebruikt geen expliciete BEGIN/COMMIT-statements, conform https://developers.cloudflare.com/d1/best-practices/import-export-data/.

## Lokaal controleren

Voer eerst `npm ci` uit (Node 24 of nieuwer). `npm test` controleert toevoegen, datumverwerking, dubbelingen, leesweergave, rechten, soft delete en audit. De beheerschermtest voert de werkelijke JavaScript-code uit in een nagebootste browser-DOM (Linkedom), gekoppeld aan de API en SQLite. Dit is geen visuele test in Smartschool. `npm run check` controleert de JavaScript-syntaxis. De kalender zelf heeft geen externe JavaScript-afhankelijkheden nodig.

## Controle van 26 september 2026

Tijdens een tweede beoordeling zijn hersteld:

- zoeken om te verwijderen combineert datum en losse zoekwoorden; “haal … weg” wordt herkend;
- titelwoorden zoals “van” in “De Klas van Morgen” blijven behouden;
- ongeldige uren, bijvoorbeeld 15.99, worden niet stilzwijgend als 15:00 geïnterpreteerd;
- bij verwijderen wordt een voorbije datum zonder jaartal niet automatisch naar volgend jaar verschoven;
- lange lijsten zijn gepagineerd in het beheer en via “Toon meer” volledig bereikbaar; de leesweergave wordt niet na 2000 items afgebroken;
- netwerkfouten krijgen een zichtbare melding; knoppen zijn tijdens een aanvraag geblokkeerd;
- invoer wordt op type, toegestane categorie en maximale hoeveelheid bytes gecontroleerd;
- de gezondheidscontrole controleert de echte database en het aanwezige schema.

Twaalf gerichte tests slagen, inclusief het beheerschermpad toevoegen → zoeken → verwijderen annuleren → verwijderen bevestigen en een lijst met 2005 items. De Worker is met Wrangler 4.141.0 succesvol gebundeld via `deploy --dry-run`, zonder publicatie. De online Cloudflare- en Smartschool-controle moet nog plaatsvinden na aansluiting van het account en de database-import.
