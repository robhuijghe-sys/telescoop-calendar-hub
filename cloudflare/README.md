# De Telescoop: gratis kalenderbasis

Een zelfstandige Cloudflare Worker met D1. Dit is de technische basis voor de kalender in het bestaande Smartschool-nieuwsbericht. De actuele HTML van Rob wordt in de laatste bouwstap verwerkt; deze branch is nog geen vervanging voor de live Railway-kalender.

## Gedrag

- `/smartschool-calendar` is de vaste, in een iframe bruikbare leesweergave. De HTML laadt zichzelf na 1800 seconden opnieuw. Bezoekers hoeven daarvoor niet opnieuw aan te melden.
- `/beheer#sleutel=<lange-sleutel>` toont invoer in gewone Nederlandse taal, een controleformulier en een doorzoekbare lijst met een verwijderknop. Het fragment wordt uit de adresbalk verwijderd en de sleutel blijft enkel voor die browsersessie bewaard.
- `POST /api/manage/items` maakt een item aan. Een datum met dezelfde titel kan niet opnieuw worden toegevoegd. Een afspraak mag zonder uur worden ingevoerd.
- `DELETE /api/manage/items/:id` markeert precies één item als verwijderd. Een bevestiging in het beheerscherm gaat eraan vooraf. Een trigger schrijft dezelfde wijziging in het auditlog; een verwijderd item blijft in de database bewaard.
- Nieuw en geïmporteerd materiaal komt als afzonderlijke regels in `calendar_items`. Daardoor kan ook een oorspronkelijke kalenderregel gericht worden verwijderd. De migratie van de nog aan te leveren HTML moet die regels en hun opmaak eerst afzonderlijk identificeren.
- De datum- en kleurinterpretatie is lokaal en regelgebaseerd. Er is geen betaalde AI-API.

## Beveiliging en toegang

De leesweergave heeft, net als de huidige werkende route, geen inlogscherm. Iedereen met de publieke URL kan de getoonde gegevens bekijken. Plaats er daarom geen gegevens die uitsluitend binnen Smartschool zichtbaar mogen zijn. Een Smartschool-iframe geeft op zichzelf geen toegangscontrole aan de externe pagina.

De beheersleutel heeft minimaal 32 willekeurige tekens; gebruik bij voorkeur 32 random bytes als 64 hextekens. Alleen de SHA-256-hash staat als Cloudflare-secret `EDITOR_TOKEN_SHA256`. Het beheer werkt zonder gebruikerslogin maar de gedeelde sleutel geeft zowel toevoeg- als verwijderrecht. Wie individuele rechten en namen in het auditlog wil, kan later meerdere editor-sleutels krijgen. Geef de beheerlink nooit mee in de publieke kalenderpagina.

De code bevat geen kalenderinhoud of sleutels. De database en de uiteindelijke HTML worden pas na controle van de aangeleverde bron overgezet.

## Voorbereiding van een eigen gratis Cloudflare-account

1. Maak een D1-database `telescoop-kalender` en vervang `REPLACE_WITH_D1_DATABASE_ID` in `wrangler.jsonc` door het echte database-ID.
2. Voer `schema.sql` uit tegen die database (`npx wrangler d1 execute telescoop-kalender --remote --file=./schema.sql`).
3. Maak lokaal een lange willekeurige sleutel. Zet uitsluitend de SHA-256-hash als secret met `npx wrangler secret put EDITOR_TOKEN_SHA256`. Bewaar de oorspronkelijke sleutel veilig voor de persoonlijke beheerlink.
4. Publiceer met `npx wrangler deploy` vanuit deze map. De inbegrepen `*.workers.dev`-naam vereist geen apart domein. Bewaar de bestaande Railway-versie tijdens de controle.
5. Controleer de beheerpagina en de iframe-weergave met echte kalendergegevens. Wijzig de iframe-URL in Smartschool één keer, pas nadat ook de actuele HTML en de Railway-toevoegingen zijn overgezet en vergeleken.

Voor deze branch zijn stap 1–5 nog niet uitgevoerd: er is geen Cloudflare-account of D1-database verbonden. Een gratis account kan op de huidige voorwaarden tegen limieten aanlopen; gebruik geen betaald abonnement of automatische upgrade. De code draait zonder periodieke achtergrondprocessen. Bij een toekomstige migratie kan de database met Wrangler worden geëxporteerd; op het gratis D1-abonnement is herstel naar een moment binnen zeven dagen beschikbaar. Houd daarnaast zelf een export bij.

## Aansluiting van de laatste HTML

De uiteindelijke HTML is de gezaghebbende bron voor de volledige oorspronkelijke kalender. Bij ontvangst:

1. Identificeer per datum de afzonderlijk verwijderbare inhoudsregels en hun kleur/opmaak. Controleer bijzondere blokken, links, badges en maandkoppen afzonderlijk.
2. Zet iedere inhoudsregel met een eigen `id`, datum en `source='legacy'` om; geef de huidige HTML-opmaak aan een gecontroleerde renderer in plaats van onbetrouwbare invoer als HTML uit te voeren.
3. Exporteer op de omschakeldag de nadien toegevoegde, zichtbare items én verwijderingen uit de Railway SQLite-database en het snapshotbestand. Vergelijk aantallen, datums en zichtbare regels vóór en na import. Voer de import idempotent uit.
4. Vervang de tijdelijke `renderCalendar` in `src/pages.mjs` door de gevalideerde oorspronkelijke opmaak, maar behoud de vaste route, 30 minuten verversing, D1-opslag en verwijdering per ID.
5. Test de definitieve Cloudflare-URL als iframe in het bestaande Smartschool-nieuwsbericht en publiceer de nieuwe link pas na een visuele vergelijking op desktop en mobiel.

## Lokaal controleren

`npm test` controleert toevoegen, datumverwerking, dubbelingen, leesweergave, rechten, soft delete en audit. `npm run check` controleert de JavaScript-syntaxis. Deze controles gebruiken Node en een SQLite-database in het geheugen en vereisen geen betalende dienst.
