"""Previewed, atomic replacements in visible calendar text."""
import hashlib
import json
import re
import time

from fastapi import Form, HTTPException
from fastapi.responses import HTMLResponse
from itsdangerous import BadSignature

from app.calendar_dynamic import _event_line
from app.rich_editor import reshape_html


CSS = '''
.replace-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px}.replace-fields label{display:block;margin-top:0}.replace-fields input,.replace-fields select{box-sizing:border-box;width:100%}.replace-check{display:flex;align-items:center;gap:8px;margin:16px 0}.replace-check input{width:auto;margin:0}.replace-summary{padding:14px;background:var(--soft);border:1px solid var(--line);border-radius:8px}.replace-result{border:1px solid var(--line);border-radius:8px;margin:16px 0;overflow:hidden}.replace-date{background:var(--soft);padding:8px 12px;color:var(--school-navy)}.replace-comparison{display:grid;grid-template-columns:1fr 1fr}.replace-comparison>div{padding:12px;min-width:0;overflow-wrap:anywhere;white-space:pre-wrap;line-height:1.6}.replace-comparison>div+div{border-left:1px solid var(--line);background:#fbfdf7}.replace-caption{display:block;color:var(--muted);font-size:13px;margin-bottom:6px}.replace-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.replace-actions button{width:auto}.replace-note{color:var(--muted);font-size:14px}@media(max-width:650px){.replace-fields,.replace-comparison{grid-template-columns:1fr}.replace-comparison>div+div{border-left:0;border-top:1px solid var(--line)}}
'''


def register_bulk_replace(s):
    def document(title, body, status=200):
        return HTMLResponse(s.page(title, body).replace('</style>', CSS + '</style>', 1), status_code=status)

    def parameters(find, replacement, mode, scope, start, end, sensitive):
        if (not find.strip() or not replacement.strip() or len(find) > 1000 or len(replacement) > 1000
                or '\n' in find or '\r' in find or '\n' in replacement or '\r' in replacement):
            raise HTTPException(400, 'Vul twee teksten in van maximaal 1.000 tekens, elk op één regel.')
        if mode not in ('text', 'line') or scope not in ('future', 'all', 'period'):
            raise HTTPException(400, 'Kies een geldige zoekwijze en periode.')
        if scope == 'future':
            start, end = s.datetime.now(s.core.TZ).date().isoformat(), ''
        elif scope == 'all':
            start, end = '', ''
        else:
            if not start or not end:
                raise HTTPException(400, 'Vul voor een gekozen periode een begin- en einddatum in.')
            s.valid_date(start)
            s.valid_date(end)
            if start > end:
                raise HTTPException(400, 'De einddatum moet op of na de begindatum liggen.')
        return dict(find=find, replacement=replacement, mode=mode, scope=scope,
                    start=start, end=end, sensitive=bool(sensitive))

    def plan(con, params):
        pattern = re.compile(re.escape(params['find']), 0 if params['sensitive'] else re.I)
        hidden = {r[0] for r in con.execute('SELECT date_local FROM editor_days WHERE hidden=1')}
        records = [('basis', dict(r), r['date_local'], r['body_html']) for r in con.execute(
            'SELECT * FROM editor_lines WHERE deleted=0 ORDER BY date_local,id')]
        records += [('event', dict(r), s.datetime.fromisoformat(r['start_at']).astimezone(s.core.TZ).date().isoformat(), _event_line(r))
                    for r in con.execute('SELECT * FROM events WHERE visible_in_embed=1 ORDER BY start_at,id')]
        changes = []
        for kind, row, date, markup in records:
            if date in hidden or (params['start'] and date < params['start']) or (params['end'] and date > params['end']):
                continue
            fragments, matches = [], []
            for fragment in s.split_lines(s.without_bold(s.clean_html(markup))):
                text = s.plain(fragment)
                found = bool(pattern.fullmatch(text)) if params['mode'] == 'line' else bool(pattern.search(text))
                new = (params['replacement'] if params['mode'] == 'line' else
                       pattern.sub(lambda _: params['replacement'], text)) if found else text
                if new != text:
                    if not new.strip():
                        raise HTTPException(400, 'Deze vervanging zou een lege regel maken. Vul een nieuwe regel in.')
                    rich = s.clean_html(reshape_html(fragment, new))
                    matches.append(dict(before=fragment, after=rich))
                    fragments.append(rich)
                else:
                    fragments.append(fragment)
            if matches:
                rich = '<br/>'.join(fragments)
                if len(rich) > 100000:
                    raise HTTPException(400, 'Een aangepaste kalenderregel wordt te lang. Gebruik een kortere vervanging.')
                changes.append(dict(kind=kind, before=row, date=date, after=rich, matches=matches))
        return sorted(changes, key=lambda c: (c['date'], c['kind'], c['before']['id']))

    def digest(changes):
        return hashlib.sha256(json.dumps(changes, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def read_token(token, kind):
        try:
            payload = s.core.signer.loads(token)
            if payload['kind'] != kind or not 0 <= time.time() - payload['created'] < 3600:
                raise ValueError()
            return payload
        except (BadSignature, ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Dit voorbeeld is verlopen of ongeldig. Zoek opnieuw en bekijk het nieuwe voorbeeld.')

    def search_form(params=None):
        p = params or dict(find='', replacement='', mode='text', scope='future', start='', end='', sensitive=False)
        value = lambda key: s.esc(str(p[key]), quote=True)
        option = lambda key, val, label: f'<option value="{val}" {"selected" if p[key] == val else ""}>{label}</option>'
        return ('<div class="card"><h2>Zoeken en vervangen</h2>'
                '<p>Verander terugkerende tekst op alle gevonden dagen in één keer. Bekijk eerst wat er wijzigt.</p>'
                '<form method="post" action="/kalender-vervangen/voorbeeld"><div class="replace-fields">'
                f'<div><label for="replace-find">Zoek deze tekst</label><input id="replace-find" name="find" maxlength="1000" value="{value("find")}" required></div>'
                f'<div><label for="replace-new">Vervang door</label><input id="replace-new" name="replacement" maxlength="1000" value="{value("replacement")}" required></div>'
                '<div><label for="replace-mode">Zoekwijze</label><select id="replace-mode" name="mode">'
                + option('mode', 'text', 'Een stukje tekst in een regel') + option('mode', 'line', 'Alleen de volledige regel') + '</select></div>'
                '<div><label for="replace-scope">Welke dagen?</label><select id="replace-scope" name="scope">'
                + option('scope', 'future', 'Vandaag en alle volgende dagen') + option('scope', 'all', 'De hele kalender, ook voorbije dagen')
                + option('scope', 'period', 'Een gekozen periode') + '</select></div></div>'
                f'<div class="replace-fields" id="replace-period"><div><label for="replace-start">Van (alleen bij gekozen periode)</label><input id="replace-start" type="date" name="start" value="{value("start")}"></div>'
                f'<div><label for="replace-end">Tot en met</label><input id="replace-end" type="date" name="end" value="{value("end")}"></div></div>'
                f'<label class="replace-check"><input type="checkbox" name="sensitive" value="1" {"checked" if p["sensitive"] else ""}>Hoofdletters moeten overeenkomen</label>'
                '<p class="replace-note">Tekstkleuren en links blijven behouden. Alleen de tekst van kalenderregels wordt doorzocht.</p>'
                '<p><button>Zoeken en voorbeeld bekijken</button></p></form></div>'
                '<script>(()=>{const scope=document.getElementById("replace-scope"),period=document.getElementById("replace-period");'
                'function show(){period.hidden=scope.value!=="period";period.querySelectorAll("input").forEach(i=>i.required=!period.hidden)}'
                'scope.addEventListener("change",show);show()})()</script>')

    @s.app.get('/kalender-vervangen')
    def search_page(q: str = ''):
        p = dict(find=q[:1000], replacement='', mode='text', scope='future', start='', end='', sensitive=False)
        return document('Zoeken en vervangen', search_form(p))

    @s.app.post('/kalender-vervangen/voorbeeld')
    def preview(find: str = Form(...), replacement: str = Form(...), mode: str = Form('text'),
                scope: str = Form('future'), start: str = Form(''), end: str = Form(''), sensitive: int = Form(0)):
        params = parameters(find, replacement, mode, scope, start, end, sensitive)
        con = s.core.db()
        try:
            con.execute('BEGIN')
            changes = plan(con, params)
        finally:
            con.close()
        body = search_form(params)
        if not changes:
            return document('Geen wijzigingen gevonden', body + '<div class="card" role="status"><h2>Geen wijzigingen gevonden</h2>'
                            '<p>Er zijn geen regels die met deze zoektekst en periode veranderen. Controleer de tekst of kies een andere periode.</p></div>')
        count = sum(len(c['matches']) for c in changes)
        days = len({c['date'] for c in changes})
        token = s.core.signer.dumps(dict(kind='replace-preview', created=time.time(), params=params, digest=digest(changes)))
        body += f'<div class="card"><h2>Controleer de vervanging</h2><p class="replace-summary" role="status">{count} {"regel" if count == 1 else "regels"} op {days} {"dag" if days == 1 else "dagen"} worden aangepast. Er is nog niets opgeslagen.</p>'
        for change in changes:
            for match in change['matches']:
                date = s.datetime.fromisoformat(change['date']).strftime('%d/%m/%Y')
                body += (f'<section class="replace-result"><div class="replace-date">{date}</div><div class="replace-comparison">'
                         '<div><span class="replace-caption">Huidige tekst</span>' + match['before'] + '</div>'
                         '<div><span class="replace-caption">Nieuwe tekst</span>' + match['after'] + '</div></div></section>')
        body += ('<form class="replace-actions" method="post" action="/kalender-vervangen/toepassen">'
                 f'<input type="hidden" name="token" value="{s.esc(token, quote=True)}">'
                 f'<button>Alle {count} {"regel" if count == 1 else "regels"} vervangen</button>'
                 '<a class="btn alt" href="/kalender-wijzigen">Annuleren</a></form></div>')
        return document('Vervanging controleren', body)

    @s.app.post('/kalender-vervangen/toepassen')
    def apply(token: str = Form(...)):
        payload = read_token(token, 'replace-preview')
        con = s.core.db()
        try:
            con.execute('BEGIN IMMEDIATE')
            changes = plan(con, payload['params'])
            if not changes or digest(changes) != payload['digest']:
                return document('Kalender ondertussen gewijzigd', '<div class="card"><h2>Kalender ondertussen gewijzigd</h2>'
                    '<p role="alert">De gevonden regels zijn ondertussen gewijzigd, verwijderd of aangevuld. Er is niets vervangen. Bekijk eerst een nieuw voorbeeld.</p>'
                    '<p><a class="btn" href="/kalender-vervangen">Opnieuw zoeken</a></p></div>', 409)
            saved = []
            for change in changes:
                row, rich = change['before'], change['after']
                if change['kind'] == 'basis':
                    con.execute('UPDATE editor_lines SET body_html=?,title=?,version=version+1 WHERE id=?', (rich, s.plain(rich), row['id']))
                    after = [dict(con.execute('SELECT * FROM editor_lines WHERE id=?', (row['id'],)).fetchone())]
                else:
                    # Same semantics as whole-day editing: retain the original
                    # structured event and metadata, replace its visible text.
                    con.execute("UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?", (s.core.now_iso(), row['id']))
                    after = []
                    for fragment in s.split_lines(rich):
                        cursor = con.execute('INSERT INTO editor_lines(date_local,body_html,title,custom_format,activity_type,whole_day) VALUES(?,?,?,?,?,?)',
                            (change['date'], fragment, s.plain(fragment), int(s.has_custom_color(fragment)),row['category'],row['all_day']))
                        after.append(dict(con.execute('SELECT * FROM editor_lines WHERE id=?', (cursor.lastrowid,)).fetchone()))
                saved.append(dict(kind=change['kind'], before=row, after=after,
                    event_after=dict(con.execute('SELECT * FROM events WHERE id=?', (row['id'],)).fetchone()) if change['kind'] == 'event' else None))
            count = sum(len(c['matches']) for c in changes)
            days = len({c['date'] for c in changes})
            s.audit(con, 'calendar.text_replaced', dict(params=payload['params'], count=count, days=days, records=saved))
            audit_id = con.execute('SELECT last_insert_rowid()').fetchone()[0]
            con.commit()
        finally:
            con.close()
        undo = s.core.signer.dumps(dict(kind='replace-undo', created=time.time(), audit_id=audit_id))
        return document('Vervanging opgeslagen', f'<div class="card"><h2>Vervanging opgeslagen</h2>'
            f'<p class="ok" role="status">{count} {"regel" if count == 1 else "regels"} op {days} {"dag" if days == 1 else "dagen"} aangepast.</p>'
            '<p>De wijzigingen zijn zichtbaar zodra je de kalender opnieuw opent.</p>'
            '<p><a class="btn" href="/kalender-wijzigen">Naar kalender wijzigen</a> <a class="btn alt" href="/kalender-vervangen">Nog een tekst vervangen</a></p>'
            '<form method="post" action="/kalender-vervangen/ongedaan-maken">'
            f'<input type="hidden" name="token" value="{s.esc(undo, quote=True)}"><button class="alt">Deze vervanging ongedaan maken</button></form></div>')

    @s.app.post('/kalender-vervangen/ongedaan-maken')
    def undo(token: str = Form(...)):
        payload = read_token(token, 'replace-undo')
        con = s.core.db()
        try:
            con.execute('BEGIN IMMEDIATE')
            audit = con.execute("SELECT payload FROM audit_log WHERE id=? AND action='calendar.text_replaced'", (payload['audit_id'],)).fetchone()
            if not audit:
                raise HTTPException(400, 'Deze vervanging werd niet gevonden.')
            saved = json.loads(audit[0])['records']
            for change in saved:
                for row in change['after']:
                    current = con.execute('SELECT * FROM editor_lines WHERE id=?', (row['id'],)).fetchone()
                    if not current or dict(current) != row:
                        raise HTTPException(409, 'Een betrokken regel is ondertussen gewijzigd. Er is niets ongedaan gemaakt; controleer de actuele kalender.')
                if change['event_after']:
                    current = con.execute('SELECT * FROM events WHERE id=?', (change['before']['id'],)).fetchone()
                    if not current or dict(current) != change['event_after']:
                        raise HTTPException(409, 'Een betrokken activiteit is ondertussen gewijzigd. Er is niets ongedaan gemaakt.')
            for change in saved:
                before = change['before']
                if change['kind'] == 'basis':
                    con.execute('UPDATE editor_lines SET body_html=?,title=?,custom_format=?,version=version+1 WHERE id=?',
                        (before['body_html'], before['title'], before['custom_format'], before['id']))
                else:
                    for row in change['after']:
                        con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?', (row['id'],))
                    con.execute('UPDATE events SET visible_in_embed=?,status=?,updated_at=? WHERE id=?',
                        (before['visible_in_embed'], before['status'], s.core.now_iso(), before['id']))
            s.audit(con, 'calendar.text_replacement_undone', dict(audit_id=payload['audit_id']))
            con.commit()
        finally:
            con.close()
        return document('Vervanging ongedaan gemaakt', '<div class="card"><h2>Vervanging ongedaan gemaakt</h2>'
            '<p class="ok" role="status">Alle betrokken regels zijn hersteld.</p><p><a class="btn" href="/kalender-wijzigen">Naar kalender wijzigen</a></p></div>')
