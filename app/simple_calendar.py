"""Public, login-free editor on the original Railway/SQLite calendar."""
import base64
import gzip
import hashlib
import html
import json
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag
from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.public_calendar_snapshot import app
import app.main as core
import app.calendar_snapshot as snapshot
import app.public_calendar as public
import app.delete_flow as deletion
from app.calendar_dynamic import CATEGORY_COLORS, _times_to_utc, infer_category

BUILD = 'railway-editor-20260926-v2'
REFRESH_SECONDS = 7200
esc = html.escape
original_snapshot = snapshot._load_snapshot
original_links = snapshot._top_links_html
original_page = public.public_page
original_interpret = deletion.public_interpret_add_delete
lock = threading.Lock()
cache = {}
FONT_CSS = '''@font-face{font-family:Roboto;font-style:normal;font-weight:400;font-display:swap;src:url(/calendar-fonts/roboto-latin-400.woff2)}@font-face{font-family:Roboto;font-style:normal;font-weight:700;font-display:swap;src:url(/calendar-fonts/roboto-latin-700.woff2)}html,body,input,textarea,select,button,.base-content,.base-content *{font-family:Aptos,Roboto,"Segoe UI",Arial,sans-serif!important}.quick{margin-bottom:7px!important}.quick a{overflow-wrap:anywhere}.editbox{border:1px solid #c9c2bd;border-radius:8px;padding:14px;min-height:100px;line-height:1.6}.row{display:flex;align-items:center;gap:10px;border-top:1px solid #eee;padding:12px 0}.row .text{flex:1;min-width:0;overflow-wrap:anywhere}.row form{margin:0}.danger{background:#8a2f2f}nav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}input:focus,textarea:focus,button:focus-visible,[contenteditable]:focus{outline:3px solid #b4c9e6;outline-offset:2px}@media(max-width:600px){.row{flex-wrap:wrap}.row .text{flex-basis:100%}}'''

MIDNIGHT_SCRIPT = """<script id="calendar-midnight">
(() => {
  const formatter = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Brussels',year:'numeric',month:'2-digit',day:'2-digit'});
  function prune() {
    const parts = Object.fromEntries(formatter.formatToParts(new Date()).map(p => [p.type,p.value]));
    const today = parts.year + '-' + parts.month + '-' + parts.day;
    document.querySelectorAll('[data-calendar-date]').forEach(el => { if(el.dataset.calendarDate < today) el.remove(); });
    document.querySelectorAll('.month-card').forEach(el => { if(!el.querySelector('[data-calendar-date]')) el.remove(); });
  }
  function tick() { prune(); setTimeout(tick,60000 - Date.now()%60000); }
  document.addEventListener('visibilitychange',prune);
  tick();
})();
</script>"""


def safe_url(value):
    value = str(value).strip()
    if value.startswith('/') and not value.startswith('//'):
        value = urljoin('https://telescoop-sgr8.smartschool.be', value)
    try:
        parts = urlsplit(value)
        if not parts.hostname:
            raise ValueError()
        _ = parts.port
    except ValueError:
        raise HTTPException(400, 'Vul een geldige http- of https-link in.')
    if len(value) > 4096 or parts.scheme not in ('http', 'https') or not parts.netloc or parts.username or parts.password or re.search(r'[\s\x00-\x1f]', value):
        raise HTTPException(400, 'Vul een geldige http- of https-link in.')
    return value


def clean_html(value):
    soup = BeautifulSoup(value, 'html.parser')
    for tag in list(soup.find_all(True)):
        if not tag.name:
            continue
        if tag.name in ('script', 'style', 'iframe', 'object', 'svg'):
            tag.decompose()
            continue
        if tag.name not in ('span', 'b', 'strong', 'i', 'em', 'u', 'a', 'br', 'p', 'div'):
            tag.unwrap()
            continue
        attrs = {}
        style = []
        for part in str(tag.get('style', '')).split(';'):
            key, sep, val = part.partition(':')
            if sep and key.strip().lower() in ('color', 'font-weight', 'font-style', 'text-decoration') and re.fullmatch(r'[\w\s#(),.%\-]+', val.strip()):
                style.append(key.strip().lower() + ':' + val.strip())
        if style:
            attrs['style'] = ';'.join(style)
        if tag.name == 'a':
            try:
                attrs.update(href=safe_url(tag.get('href', '')), target='_blank', rel='noopener noreferrer')
            except HTTPException:
                tag.unwrap()
                continue
        tag.attrs = attrs
    return str(soup)


def split_lines(value):
    soup = BeautifulSoup(clean_html(value), 'html.parser')
    lines, current = [], []

    def flush():
        if BeautifulSoup(''.join(current), 'html.parser').get_text(strip=True):
            lines.append(''.join(current))
        current.clear()

    def walk(node, parents):
        if isinstance(node, NavigableString):
            current.append(''.join(p[0] for p in parents) + esc(str(node)) + ''.join(p[1] for p in reversed(parents)))
        elif isinstance(node, Tag):
            if node.name == 'br':
                flush()
                return
            block = node.name in ('p', 'div')
            if block:
                flush()
            attrs = ''.join(' ' + k + '="' + esc(' '.join(v) if isinstance(v, list) else str(v), quote=True) + '"' for k, v in node.attrs.items())
            wrapper = (f'<{node.name}{attrs}>', f'</{node.name}>')
            for child in node.children:
                walk(child, parents + [wrapper])
            if block:
                flush()
    for node in soup.contents:
        walk(node, [])
    flush()
    return lines


def plain(value):
    return BeautifulSoup(value, 'html.parser').get_text(' ', strip=True)


@app.on_event('startup')
def setup_editor():
    # Keep the original JSON and events. A one-time SQLite copy is also kept on
    # the persistent volume before adding the new editor tables.
    con = core.db()
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='editor_lines'").fetchone():
        backup = sqlite3.connect(str(core.DB_PATH) + '.before-public-editor.bak')
        con.backup(backup)
        backup.close()
    con.executescript('''
      CREATE TABLE IF NOT EXISTS editor_lines(id INTEGER PRIMARY KEY AUTOINCREMENT,date_local TEXT NOT NULL,body_html TEXT NOT NULL,title TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
      CREATE INDEX IF NOT EXISTS editor_lines_visible ON editor_lines(deleted,date_local,id);
      CREATE TABLE IF NOT EXISTS editor_links(id INTEGER PRIMARY KEY AUTOINCREMENT,description TEXT NOT NULL,url TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS editor_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL DEFAULT 0);
      INSERT OR IGNORE INTO editor_state(id) VALUES(1);
      CREATE TABLE IF NOT EXISTS editor_days(date_local TEXT PRIMARY KEY,hidden INTEGER NOT NULL DEFAULT 1);
    ''')
    for table in ('events', 'editor_lines', 'editor_links', 'editor_days', 'settings'):
        for operation in ('INSERT', 'UPDATE', 'DELETE'):
            con.execute(f'CREATE TRIGGER IF NOT EXISTS editor_revision_{table}_{operation} AFTER {operation} ON {table} BEGIN UPDATE editor_state SET revision=revision+1 WHERE id=1; END')
    if not con.execute("SELECT 1 FROM settings WHERE key='editor_migrated'").fetchone():
        snap = original_snapshot()
        for entry in snap.get('entries', []):
            for fragment in split_lines(entry.get('html', '')):
                con.execute('INSERT INTO editor_lines(date_local,body_html,title) VALUES(?,?,?)', (entry['date'], fragment, plain(fragment)))
        layout = {**snap, 'entries': [{**e, 'html': ''} for e in snap.get('entries', [])]}
        con.execute("INSERT INTO settings(key,value) VALUES('editor_layout',?)", (json.dumps(layout, ensure_ascii=False),))
        seed = os.getenv('CALENDAR_LINKS_GZ_B64', '')
        links = json.loads(gzip.decompress(base64.b64decode(seed))) if seed else [dict(description=a.parent.get_text(' ', strip=True).replace('🔗 openen', '').strip(), url=a['href']) for a in BeautifulSoup(original_links(), 'html.parser').find_all('a', href=True)]
        for link in links:
            con.execute('INSERT INTO editor_links(description,url) VALUES(?,?)', (link['description'], safe_url(link['url'])))
        con.execute("INSERT INTO settings(key,value) VALUES('editor_migrated','1')")
    con.commit()
    con.close()
    from app.latest_source import apply_latest_source
    apply_latest_source(original_snapshot, split_lines, clean_html, plain, safe_url)


def edited_snapshot():
    con = core.db()
    layout = json.loads(con.execute("SELECT value FROM settings WHERE key='editor_layout'").fetchone()[0])
    entries = {e['date']: dict(e) for e in layout['entries']}
    for row in con.execute('SELECT date_local,body_html FROM editor_lines WHERE deleted=0 ORDER BY date_local,id'):
        day = entries.setdefault(row['date_local'], {'date': row['date_local'], 'html': ''})
        day['html'] += ('<br>' if day['html'] else '') + row['body_html']
    con.close()
    layout['entries'] = list(entries.values())
    # The old renderer requires a label for every base date.
    for entry in layout['entries']:
        if not entry.get('label'):
            d = datetime.fromisoformat(entry['date'])
            entry['label'] = snapshot.WEEKDAYS[d.weekday()] + ' ' + d.strftime('%d/%m')
    return layout


def links_html():
    con = core.db()
    links = [('/', 'Kalender wijzigen')] + [(r['url'], r['description']) for r in con.execute('SELECT url,description FROM editor_links WHERE deleted=0 ORDER BY id')]
    con.close()
    return ''.join(f'<p class="quick"><a href="{esc(url, quote=True)}" target="_blank" rel="noopener noreferrer">🔗 {esc(label)}</a></p>' for url, label in links)


snapshot._load_snapshot = edited_snapshot
snapshot._top_links_html = links_html


def page(title, body):
    nav = '<nav><a class="btn alt" href="/">Activiteiten toevoegen</a><a class="btn alt" href="/kalender-wijzigen">Kalender wijzigen</a><a class="btn alt" href="/kalender-links">Links wijzigen</a><a class="btn alt" href="/smartschool-calendar" target="_blank" rel="noopener">Bekijk kalender</a></nav>'
    return original_page(title, nav + body).replace('</style>', FONT_CSS + '</style>', 1)


public.public_page = page
deletion.public_page = page
app.mount('/calendar-fonts', StaticFiles(directory=Path(__file__).parent / 'static/fonts'), name='calendar-fonts')


@app.middleware('http')
async def editor_headers(request: Request, call_next):
    if request.method == 'POST' and request.url.path.startswith(('/kalender-', '/public/')):
        origin = request.headers.get('origin')
        if origin and origin not in (str(request.base_url).rstrip('/'), core.PUBLIC_BASE_URL):
            return Response('Open de kalender in een eigen tabblad.', status_code=403)
        if len(await request.body()) > 65536:
            return Response('Invoer te groot.', status_code=413)
    response = await call_next(request)
    if request.url.path.startswith('/calendar-fonts/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif request.url.path != '/smartschool-calendar':
        response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


for route, method in [('/', 'GET'), ('/smartschool-calendar', 'GET'), ('/public/interpret', 'POST'), ('/public/delete', 'POST'), ('/health', 'GET')]:
    public._remove_route(route, method)


@app.get('/health')
def health():
    con = core.db()
    con.execute('SELECT revision FROM editor_state WHERE id=1').fetchone()
    source = con.execute("SELECT value FROM settings WHERE key='editor_source_digest'").fetchone()
    con.close()
    return {'ok': True, 'version': BUILD, 'source_digest': source[0] if source else None}


@app.get('/smartschool-calendar')
def calendar(request: Request):
    con = core.db()
    revision = con.execute('SELECT revision FROM editor_state WHERE id=1').fetchone()[0]
    con.close()
    key = (revision, datetime.now(core.TZ).date().isoformat())
    with lock:
        if cache.get('key') != key:
            con = core.db()
            hidden = {r[0] for r in con.execute('SELECT date_local FROM editor_days WHERE hidden=1')}
            con.close()
            doc = snapshot.render_snapshot_calendar(hide_past=True, hidden_dates=hidden).replace('http-equiv="refresh" content="30"', f'http-equiv="refresh" content="{REFRESH_SECONDS}"')
            doc = doc.replace('</style>', FONT_CSS + '</style>', 1)
            doc = doc.replace('</body>', MIDNIGHT_SCRIPT + '</body>')
            cache.update(key=key, doc=doc, etag='"' + hashlib.sha256(doc.encode()).hexdigest() + '"')
        doc, etag = cache['doc'], cache['etag']
    headers = {'ETag': etag, 'Cache-Control': 'no-cache, must-revalidate', 'X-Calendar-Version': BUILD}
    if etag in request.headers.get('if-none-match', '').split(', '):
        return Response(status_code=304, headers=headers)
    return HTMLResponse(doc, headers=headers)


@app.get('/')
def home(saved: int = 0, added: int = 0):
    message = '<p class="ok">Opgeslagen. De kalender toont je wijziging bij de volgende opening; openstaande kalenders verversen binnen twee uur.</p>' if saved or added else ''
    body = '''<details class="card" open><summary>Een activiteit in gewone taal invoeren</summary><form method="post" action="/public/interpret"><label>Opdracht</label><textarea name="prompt" maxlength="2000" placeholder="Voeg op 6 oktober om 15.30 teamvergadering toe" required></textarea><p><button>Interpreteren en controleren</button></p></form></details><details class="card"><summary>Meerdere regels toevoegen</summary><p>Kies één datum. Gebruik voor elke regel: dagdeel of uur: klasgroep: locatie of activiteit. Bijvoorbeeld VM: K3: uitstap naar plantentuin. Meerdere regels worden samen opgeslagen en blijven apart aanpasbaar.</p><form method="post" action="/kalender-toevoegen"><input type="hidden" name="structured" value="1"><label>Datum</label><input type="date" name="date" required><label>Activiteiten en vervangingen</label><textarea name="lines" rows="9" maxlength="20000" placeholder="VM: K3: uitstap naar plantentuin" required></textarea><p><button>Alle regels toevoegen</button></p></form></details>'''
    return HTMLResponse(page('Activiteiten toevoegen', message + body))


def valid_date(value):
    try:
        if datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d') != value:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, 'Kies een geldige datum.')
    return value


def audit(con, action, data):
    con.execute('INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)', ('public-link', action, json.dumps(data, ensure_ascii=False), core.now_iso()))


@app.post('/kalender-toevoegen')
def add_lines(date: str = Form(...), lines: str = Form(...), structured: str = Form("0")):
    valid_date(date)
    rows = [line.strip() for line in lines.splitlines() if line.strip()]
    if not rows or len(rows) > 100 or any(len(line) > 1000 for line in rows):
        raise HTTPException(400, 'Gebruik 1 tot 100 regels, met maximaal 1000 tekens per regel.')
    if structured == '1':
        normalized = []
        for number, line in enumerate(rows, 1):
            parts = re.split(r':\s+|\s+-\s+', line, maxsplit=2)
            if len(parts) != 3 or not all(p.strip() for p in parts):
                raise HTTPException(400, f'Regel {number}: gebruik dagdeel of uur: klasgroep: locatie of activiteit. Bijvoorbeeld VM: K3: uitstap naar plantentuin. Er is niets opgeslagen.')
            moment, group, activity = [p.strip() for p in parts]
            if not re.fullmatch(r'(?:VM|NM|voormiddag|namiddag|hele dag|\d{1,2}(?:[u:.h]\d{0,2})?(?:\s*(?:-|tot)\s*\d{1,2}(?:[u:.h]\d{0,2})?)?|\d+(?:ste|de) uur)', moment, re.IGNORECASE):
                raise HTTPException(400, f'Regel {number}: begin met VM, NM, hele dag of een uur, bijvoorbeeld 09:30. Er is niets opgeslagen.')
            moment = {'voormiddag': 'VM', 'namiddag': 'NM', 'vm': 'VM', 'nm': 'NM'}.get(moment.lower(), moment)
            normalized.append(f'{moment}: {group.upper()}: {activity}')
        rows = normalized
    con = core.db()
    try:
        con.execute('BEGIN IMMEDIATE')
        con.execute('DELETE FROM editor_days WHERE date_local=?', (date,))
        added = 0
        for line in rows:
            if con.execute('SELECT id FROM editor_lines WHERE deleted=0 AND date_local=? AND title=?', (date, line)).fetchone():
                continue
            color = CATEGORY_COLORS[infer_category(line)][0]
            con.execute('INSERT INTO editor_lines(date_local,body_html,title) VALUES(?,?,?)', (date, f'<span style="color:{color}">{esc(line)}</span>', line))
            added += 1
        audit(con, 'calendar.bulk_added', {'date': date, 'count': added})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/?saved=1', 303)


@app.post('/kalender-dag-verwijderen')
def delete_day(date: str = Form(...)):
    valid_date(date)
    con = core.db()
    try:
        con.execute('BEGIN IMMEDIATE')
        basis = [dict(r) for r in con.execute('SELECT * FROM editor_lines WHERE date_local=? AND deleted=0', (date,))]
        events = [dict(r) for r in con.execute('SELECT * FROM events WHERE visible_in_embed=1') if datetime.fromisoformat(r['start_at']).astimezone(core.TZ).date().isoformat() == date]
        con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE date_local=? AND deleted=0', (date,))
        for event in events:
            con.execute("UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?", (core.now_iso(), event['id']))
        con.execute('INSERT INTO editor_days(date_local,hidden) VALUES(?,1) ON CONFLICT(date_local) DO UPDATE SET hidden=1', (date,))
        audit(con, 'calendar.day_deleted', {'date': date, 'basis': basis, 'events': events})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/kalender-wijzigen?saved=1', 303)


@app.post('/public/interpret')
def interpret(prompt: str = Form(...)):
    if len(prompt) > 2000:
        raise HTTPException(400, 'Schrijf een kortere opdracht.')
    if deletion._is_delete_prompt(prompt):
        from urllib.parse import urlencode
        parsed, query = deletion._delete_payload(prompt)
        return RedirectResponse('/kalender-wijzigen?' + urlencode({'q': query, 'date': parsed.get('date') or ''}), 303)
    return original_interpret(prompt)


@app.post('/public/delete')
def old_delete():
    return RedirectResponse('/kalender-wijzigen', 303)


def rows_all():
    con = core.db()
    rows = [dict(id='basis:' + str(r['id']), date=r['date_local'], title=r['title'], version=str(r['version'])) for r in con.execute('SELECT * FROM editor_lines WHERE deleted=0')]
    for row in con.execute('SELECT * FROM events WHERE visible_in_embed=1'):
        local = datetime.fromisoformat(row['start_at']).astimezone(core.TZ)
        rows.append(dict(id='event:' + str(row['id']), date=local.date().isoformat(), title=row['title'], version=row['updated_at']))
    con.close()
    return sorted(rows, key=lambda r: (r['date'], r['id']))


@app.get('/kalender-wijzigen')
def edit_list(q: str = '', date: str = '', p: int = 1, saved: int = 0):
    def normalized(s):
        return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if not unicodedata.combining(c)).replace('afwezigheid', 'afwezig')
    terms = normalized(q).split()
    rows = [r for r in rows_all() if (not date or r['date'] == date) and all(t in normalized(r['date'] + ' ' + r['date'][8:] + '/' + r['date'][5:7] + ' ' + r['title']) for t in terms)]
    start = max(0, p - 1) * 60
    body = '<p class="ok">Wijziging opgeslagen.</p>' if saved else ''
    body += '<div class="card"><h2>Een volledige dag verwijderen</h2><p>Voorbije dagen verdwijnen automatisch na middernacht, volgens Belgische tijd. Hieronder kun je ook zelf een dag met alle activiteiten en vervangingen verwijderen.</p><form method="post" action="/kalender-dag-verwijderen" onsubmit="return confirm(\'Deze hele dag met ALLE activiteiten en vervangingen verwijderen?\')"><label>Dag</label><input type="date" name="date" required><p><button class="danger">Hele dag verwijderen</button></p></form></div>'
    body += f'<div class="card"><h2>Kalender wijzigen</h2><form><label>Zoeken op tekst of datum</label><input name="q" value="{esc(q, quote=True)}"><label>Datum (optioneel)</label><input type="date" name="date" value="{esc(date, quote=True)}"><p><button>Zoeken</button> <a href="/kalender-wijzigen">Alles tonen</a></p></form><p>{len(rows)} kalenderregels</p>'
    for row in rows[start:start + 60]:
        body += f'<div class="row"><div class="text">{esc(row["date"])} · {esc(row["title"])}</div><a class="btn" href="/kalender-regel/{row["id"]}">Aanpassen</a><form method="post" action="/kalender-verwijderen/{row["id"]}" onsubmit="return confirm(\'Deze kalenderregel verwijderen?\')"><input type="hidden" name="version" value="{esc(row["version"], quote=True)}"><button class="danger">Verwijderen</button></form></div>'
    from urllib.parse import urlencode
    for number, label in ((p - 1, 'Vorige'), (p + 1, 'Volgende')):
        if number > 0 and (number < p or start + 60 < len(rows)):
            body += '<p><a href="/kalender-wijzigen?' + esc(urlencode(dict(q=q, date=date, p=number)), quote=True) + '">' + label + '</a></p>'
    return HTMLResponse(page('Kalender wijzigen', body + '</div>'))


def get_row(con, key):
    match = re.fullmatch(r'(basis|event):(\d+)', key)
    if not match:
        raise HTTPException(404, 'Kalenderregel niet gevonden.')
    kind, ident = match.groups()
    table, where = ('editor_lines', 'deleted=0') if kind == 'basis' else ('events', 'visible_in_embed=1')
    row = con.execute(f'SELECT * FROM {table} WHERE id=? AND {where}', (int(ident),)).fetchone()
    if not row:
        raise HTTPException(404, 'Deze kalenderregel is al verwijderd.')
    return kind, dict(row)


@app.get('/kalender-regel/{key}')
def edit_row(key: str):
    con = core.db()
    try:
        kind, row = get_row(con, key)
    finally:
        con.close()
    if kind == 'basis':
        date, version = row['date_local'], str(row['version'])
        fields = f'<label>Tekst en links van deze regel</label><div class="editbox" id="rich" contenteditable="true" role="textbox" aria-multiline="true">{row["body_html"]}</div><input type="hidden" name="body_html" id="bodyHtml"><p class="muted">Bestaande kleuren en links blijven behouden tijdens het aanpassen.</p>'
    else:
        local = datetime.fromisoformat(row['start_at']).astimezone(core.TZ)
        end = datetime.fromisoformat(row['end_at']).astimezone(core.TZ)
        date, version = local.date().isoformat(), row['updated_at']
        fields = f'<label>Tekst</label><input name="title" maxlength="500" value="{esc(row["title"], quote=True)}" required><label>Beginuur</label><input type="time" name="start_time" value="{local.strftime("%H:%M") if not row["all_day"] else ""}"><label>Einduur</label><input type="time" name="end_time" value="{end.strftime("%H:%M") if not row["all_day"] else ""}"><label>Extra regels</label><textarea name="description" maxlength="4000">{esc(row["description"])}</textarea><label>Locatie</label><input name="location" maxlength="500" value="{esc(row["location"], quote=True)}"><label>Kleur</label><select name="category">' + ''.join(f'<option value="{k}" {"selected" if k == row["category"] else ""}>{v[1]}</option>' for k, v in CATEGORY_COLORS.items()) + '</select>'
    body = f'<div class="card"><h2>Activiteit aanpassen</h2><form method="post" onsubmit="if(document.getElementById(\'rich\'))document.getElementById(\'bodyHtml\').value=document.getElementById(\'rich\').innerHTML"><input type="hidden" name="version" value="{esc(version, quote=True)}"><label>Datum</label><input type="date" name="date" value="{date}" required>{fields}<p><button>Wijzigingen opslaan</button> <a class="btn alt" href="/kalender-wijzigen">Annuleren</a></p></form></div>'
    return HTMLResponse(page('Activiteit aanpassen', body))


@app.post('/kalender-regel/{key}')
async def save_row(key: str, request: Request):
    form = await request.form()
    date = valid_date(str(form.get('date', '')))
    con = core.db()
    try:
        con.execute('BEGIN IMMEDIATE')
        kind, row = get_row(con, key)
        version = str(row['version'] if kind == 'basis' else row['updated_at'])
        if version != form.get('version'):
            raise HTTPException(409, 'Deze regel is ondertussen gewijzigd. Open hem opnieuw voordat je opslaat.')
        con.execute('DELETE FROM editor_days WHERE date_local=?', (date,))
        if kind == 'basis':
            rich = clean_html(str(form.get('body_html', '')))
            if not plain(rich) or len(rich) > 20000:
                raise HTTPException(400, 'Vul een geldige kalendertekst in.')
            con.execute('UPDATE editor_lines SET date_local=?,body_html=?,title=?,version=version+1 WHERE id=?', (date, rich, plain(rich), row['id']))
        else:
            title = str(form.get('title', '')).strip()
            if not title or len(title) > 500:
                raise HTTPException(400, 'Vul een titel in van maximaal 500 tekens.')
            try:
                start, end, untimed = _times_to_utc(date, str(form.get('start_time', '')), str(form.get('end_time', '')), False)
            except ValueError:
                raise HTTPException(400, 'Controleer het begin- en einduur.')
            con.execute('UPDATE events SET title=?,description=?,location=?,category=?,start_at=?,end_at=?,all_day=?,updated_at=? WHERE id=?', (title, str(form.get('description', ''))[:4000], str(form.get('location', ''))[:500], infer_category(title, str(form.get('category', 'auto'))), start, end, int(untimed), core.now_iso(), row['id']))
        audit(con, 'calendar.line_changed', {'key': key, 'before': row})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/kalender-wijzigen?saved=1', 303)


@app.post('/kalender-verwijderen/{key}')
def delete_row(key: str, version: str = Form(...)):
    con = core.db()
    try:
        con.execute('BEGIN IMMEDIATE')
        kind, row = get_row(con, key)
        if version != str(row['version'] if kind == 'basis' else row['updated_at']):
            raise HTTPException(409, 'Deze regel is ondertussen gewijzigd. Vernieuw eerst de lijst.')
        if kind == 'basis':
            con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?', (row['id'],))
        else:
            con.execute("UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?", (core.now_iso(), row['id']))
        audit(con, 'calendar.line_deleted', {'key': key, 'before': row})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/kalender-wijzigen?saved=1', 303)


@app.get('/kalender-links')
def link_page(saved: int = 0):
    con = core.db()
    rows = [dict(r) for r in con.execute('SELECT * FROM editor_links WHERE deleted=0 ORDER BY id')]
    con.close()
    body = '<p class="ok">Link opgeslagen.</p>' if saved else ''
    for row in [dict(id=0, description='', url='', version=0)] + rows:
        body += f'<div class="card"><h2>{"Link toevoegen" if not row["id"] else "🔗 " + esc(row["description"])}</h2><form method="post" action="/kalender-link/{row["id"]}"><input type="hidden" name="version" value="{row["version"]}"><label>Omschrijving</label><input name="description" value="{esc(row["description"], quote=True)}" maxlength="200" required><label>Link</label><input name="url" value="{esc(row["url"], quote=True)}" maxlength="4096" required><p><button>Opslaan</button></p></form>'
        if row['id']:
            body += f'<form method="post" action="/kalender-link/{row["id"]}/verwijderen" onsubmit="return confirm(\'Deze link verwijderen?\')"><input type="hidden" name="version" value="{row["version"]}"><button class="danger">Verwijderen</button></form>'
        body += '</div>'
    return HTMLResponse(page('Links wijzigen', body))


@app.post('/kalender-link/{ident}')
def save_link(ident: int, description: str = Form(...), url: str = Form(...), version: int = Form(0)):
    description, url = description.strip(), safe_url(url)
    if not description or len(description) > 200:
        raise HTTPException(400, 'Vul een omschrijving in van maximaal 200 tekens.')
    con = core.db()
    try:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT id FROM editor_links WHERE deleted=0 AND description=? AND url=? AND id!=?', (description, url, ident)).fetchone():
            raise HTTPException(409, 'Deze link bestaat al.')
        if ident:
            if not con.execute('UPDATE editor_links SET description=?,url=?,version=version+1 WHERE id=? AND version=? AND deleted=0', (description, url, ident, version)).rowcount:
                raise HTTPException(409, 'Deze link is ondertussen gewijzigd of verwijderd. Vernieuw de pagina.')
        else:
            con.execute('INSERT INTO editor_links(description,url) VALUES(?,?)', (description, url))
        audit(con, 'calendar.link_saved', {'id': ident, 'description': description, 'url': url})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/kalender-links?saved=1', 303)


@app.post('/kalender-link/{ident}/verwijderen')
def delete_link(ident: int, version: int = Form(...)):
    con = core.db()
    try:
        if not con.execute('UPDATE editor_links SET deleted=1,version=version+1 WHERE id=? AND version=? AND deleted=0', (ident, version)).rowcount:
            raise HTTPException(409, 'Deze link is ondertussen gewijzigd of verwijderd. Vernieuw de pagina.')
        audit(con, 'calendar.link_deleted', {'id': ident})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/kalender-links?saved=1', 303)
