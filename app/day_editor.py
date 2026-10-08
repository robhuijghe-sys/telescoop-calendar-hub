"""One rich-text window per calendar day, with atomic, versioned saves."""
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlencode

from fastapi import Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from bs4 import BeautifulSoup

from app.day_order import ordered_fragments
from app.calendar_dynamic import _event_line


CSS = '''
.day-card{border:1px solid #cbd5e1;border-top:2px solid #203555;border-radius:8px;margin:18px 0;overflow:hidden}.day-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;background:#edf1f7;padding:6px 12px;border-bottom:1px solid #cbd5e1}.day-heading h3{margin:0;font-size:15px;font-weight:400;color:#203555}.day-heading .btn{padding:5px 10px;font-size:14px;line-height:1.3;margin:0;width:auto}.day-preview{line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;padding:14px}.day-preview,.day-preview *,.day-form .editor-visual,.day-form .editor-visual *{font-weight:400!important}.day-preview p,.day-preview div{margin:0}.day-preview a{color:inherit}
.day-dialog{border:1px solid #e5dfd8;border-radius:16px;padding:0;width:min(920px,calc(100% - 24px));max-height:90vh;max-height:90dvh;color:#2f2926}.day-dialog::backdrop{background:rgba(20,32,49,.55)}.day-dialog .day-form{padding:22px}.day-form .editor-visual,.day-form textarea{min-height:300px;max-height:50vh;overflow:auto;font-size:16px}.day-actions{display:flex;flex-wrap:wrap;gap:10px;position:sticky;bottom:0;background:white;padding:12px 0;margin:0}.day-error{background:#fff5d9;border:1px solid #efd28a;border-radius:8px;padding:12px}.day-form h2{margin:0 0 10px}label,.muted{font-size:14px}
@media(max-width:600px){.day-heading{gap:8px;padding:6px 10px}.day-heading .btn{width:auto}.day-dialog .day-form{padding:16px}.day-actions>*{width:100%}.day-form .editor-visual,.day-form textarea{min-height:230px}}
'''

SCRIPT = '''<script id="whole-day-windows">
document.addEventListener('click', event => {
  const opener = event.target.closest('[data-edit-day]');
  if (opener) {
    const dialog = document.getElementById(opener.dataset.editDay);
    if (!dialog || !dialog.showModal) return;
    event.preventDefault(); dialog.showModal();
    dialog.querySelector('.editor-visual:not([hidden]),textarea:not([hidden])')?.focus();
  }
  const closer = event.target.closest('[data-close-day]');
  if (closer) {
    const dialog = closer.closest('dialog');
    if (dialog && (!dialog.dataset.changed || confirm('Niet-opgeslagen wijzigingen verwerpen?'))) {
      event.preventDefault(); dialog.close();
    } else if (dialog) event.preventDefault();
  }
});
document.querySelectorAll('.day-dialog').forEach(dialog => {
  dialog.addEventListener('input', () => { dialog.dataset.changed = '1'; });
  dialog.querySelector('.editor-tools').addEventListener('click', e => {
    if (['color','bold','clear'].includes(e.target.closest('button')?.dataset.action)) dialog.dataset.changed = '1';
  });
  dialog.addEventListener('cancel', e => {
    if (dialog.dataset.changed && !confirm('Niet-opgeslagen wijzigingen verwerpen?')) e.preventDefault();
  });
});
</script>'''


def register_day_editor(s):
    def signature(fragment):
        # Browser serialization may reorder CSS or turn hex colors into rgb().
        soup = BeautifulSoup(fragment, 'html.parser')
        for tag in soup.find_all(style=True):
            style = re.sub(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)',
                           lambda m: '#%02x%02x%02x' % tuple(int(v) for v in m.groups())
                           if all(int(v) <= 255 for v in m.groups()) else m[0], tag['style'], flags=re.I)
            tag['style'] = ';'.join(sorted(k.strip().lower() + ':' + v.strip().lower()
                                         for part in style.split(';') if ':' in part
                                         for k, v in [part.split(':', 1)]))
        return str(soup)

    def records(con, date):
        basis = [dict(r) for r in con.execute(
            'SELECT * FROM editor_lines WHERE date_local=? AND deleted=0 ORDER BY id', (date,))]
        events = [dict(r) for r in con.execute(
            'SELECT * FROM events WHERE visible_in_embed=1 ORDER BY start_at,id')
            if s.datetime.fromisoformat(r['start_at']).astimezone(s.core.TZ).date().isoformat() == date]
        hidden = con.execute('SELECT hidden FROM editor_days WHERE date_local=?', (date,)).fetchone()
        state = {'basis': basis, 'events': events, 'hidden': hidden[0] if hidden else None}
        token = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        fragments = [s.without_bold(s.clean_html(r['body_html'])) for r in basis]
        fragments += [s.without_bold(s.clean_html(_event_line(r))) for r in events]
        rich = '<br/>'.join(ordered_fragments(fragments))
        return state, token, rich

    def label(date):
        day = s.datetime.fromisoformat(date)
        weekdays = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']
        return weekdays[day.weekday()] + ' ' + day.strftime('%d/%m/%Y')

    def form(date, token, rich, modal=False, error='', conflict=False):
        close = ' data-close-day' if modal else ''
        message = f'<p class="day-error" role="alert">{s.esc(error)}</p>' if error else ''
        fields = s.editor('body_html', rich, 'Alle activiteiten, vervangingen en agenda’s van deze dag',
                          required=True, limit=100000, field_id='day-' + date)
        action = (f'<a class="btn" href="/kalender-dag/{date}">Dag opnieuw openen</a>' if conflict else
                  '<button>Hele dag opslaan</button>')
        return (f'<form class="day-form" method="post" action="/kalender-dag/{date}">'
                f'<h2 id="day-title-{date}">{label(date)} bewerken</h2>'
                '<p class="muted">Bewerk alles samen. Je kunt regels samenvoegen, toevoegen of weghalen.</p>'
                + message + f'<input type="hidden" name="version" value="{s.esc(token, quote=True)}">'
                + fields + f'<p class="day-actions">{action} <a class="btn alt" href="/kalender-wijzigen"{close}>Annuleren</a></p></form>')

    def document(title, body):
        return s.page(title, body).replace('</style>', CSS + '</style>', 1)

    s.public._remove_route('/kalender-wijzigen', 'GET')

    @s.app.get('/kalender-wijzigen')
    def day_list(q: str = '', date: str = '', p: int = 1, saved: int = 0):
        def normalized(value):
            return ''.join(c for c in unicodedata.normalize('NFD', value.lower())
                           if not unicodedata.combining(c)).replace('afwezigheid', 'afwezig')
        today = s.datetime.now(s.core.TZ).date().isoformat()
        terms = normalized(q).split()
        grouped = {}
        for row in s.rows_all():
            if row['date'] >= today and (not date or row['date'] == date):
                grouped.setdefault(row['date'], []).append(row)
        days = []
        con = s.core.db()
        try:
            con.execute('BEGIN')
            for ds in sorted(grouped):
                _, token, rich = records(con, ds)
                search = normalized(ds + ' ' + ds[8:] + '/' + ds[5:7] + ' ' + s.plain(rich))
                if all(term in search for term in terms):
                    days.append((ds, token, rich, len(grouped[ds])))
        finally:
            con.close()
        p = min(max(1, p), max(1, (len(days) + 19) // 20))
        start = (p - 1) * 20
        body = '<p class="ok" role="status">Wijziging opgeslagen.</p>' if saved else ''
        body += (f'<div class="card"><h2>Kalender wijzigen</h2><form>'
                 f'<label>Zoeken op tekst of datum</label><input name="q" value="{s.esc(q, quote=True)}">'
                 f'<label>Datum (optioneel)</label><input type="date" name="date" value="{s.esc(date, quote=True)}">'
                 '<p><button>Zoeken</button> <a href="/kalender-wijzigen">Alles tonen</a></p></form>'
                 f'<p class="muted">{len(days)} {"dag" if len(days) == 1 else "dagen"} · {sum(d[3] for d in days)} kalenderregels</p>')
        dialogs = []
        for ds, token, rich, count in days[start:start + 20]:
            ident = 'day-window-' + ds
            body += (f'<section class="day-card"><div class="day-heading"><h3>{label(ds)}</h3>'
                     f'<a class="btn" href="/kalender-dag/{ds}" data-edit-day="{ident}">Bewerken</a></div>'
                     f'<div class="day-preview">{rich}</div></section>')
            dialogs.append(f'<dialog class="day-dialog" id="{ident}" aria-labelledby="day-title-{ds}">'
                           + form(ds, token, rich, modal=True) + '</dialog>')
        if not days:
            body += '<p>Geen dagen gevonden. Probeer een andere datum of zoektekst.</p>'
        for number, text in ((p - 1, 'Vorige'), (p + 1, 'Volgende')):
            if number > 0 and (number < p or start + 20 < len(days)):
                url = s.esc(urlencode({'q': q, 'date': date, 'p': number}), quote=True)
                body += f'<p><a href="/kalender-wijzigen?{url}">{text}</a></p>'
        body += ('</div><details class="card"><summary>Een volledige dag verwijderen</summary>'
                 '<p>Voorbije dagen verdwijnen automatisch na middernacht, volgens Belgische tijd.</p>'
                 '<form method="post" action="/kalender-dag-verwijderen" onsubmit="return confirm(\'Deze hele dag met ALLE activiteiten en vervangingen verwijderen?\')">'
                 '<label>Dag</label><input type="date" name="date" required><p><button class="danger">Hele dag verwijderen</button></p></form></details>')
        refresh = '''<script id="editor-day-refresh">
(() => {
 const renderedDay = %s;
 const formatter = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Brussels',year:'numeric',month:'2-digit',day:'2-digit'});
 function refreshDay() {
   if (document.querySelector('dialog[open]')) return;
   const parts = Object.fromEntries(formatter.formatToParts(new Date()).map(p => [p.type,p.value]));
   if (parts.year + '-' + parts.month + '-' + parts.day !== renderedDay) window.location.reload();
 }
 document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshDay(); });
 setInterval(refreshDay, 60000); refreshDay();
})();</script>''' % json.dumps(today)
        return HTMLResponse(document('Kalender wijzigen', body + ''.join(dialogs) + SCRIPT + refresh))

    @s.app.get('/kalender-dag/{date}')
    def edit_day(date: str):
        s.valid_date(date)
        con = s.core.db()
        try:
            con.execute('BEGIN')
            _, token, rich = records(con, date)
        finally:
            con.close()
        return HTMLResponse(document('Dag bewerken', '<div class="card">' + form(date, token, rich) + '</div>'))

    @s.app.post('/kalender-dag/{date}')
    def save_day(date: str, version: str = Form(...), body_html: str = Form('')):
        s.valid_date(date)
        rich = s.without_bold(s.clean_html(body_html))
        if len(body_html) > 100000 or len(rich) > 100000 or not s.plain(rich):
            return HTMLResponse(document('Dag bewerken', '<div class="card">' + form(
                date, version, rich[:100000], error='Vul kalendertekst in (maximaal 100.000 tekens). Gebruik “Hele dag verwijderen” om alles te wissen.') + '</div>'), status_code=400)
        con = s.core.db()
        try:
            con.execute('BEGIN IMMEDIATE')
            before, current, old_rich = records(con, date)
            if version != current:
                return HTMLResponse(document('Dag ondertussen gewijzigd', '<div class="card">' + form(
                    date, version, rich, error='Deze dag is ondertussen gewijzigd. Je tekst staat hieronder zodat je die kunt kopiëren. Open de dag opnieuw om de nieuwste versie te bewerken.', conflict=True) + '</div>'), status_code=409)
            # Opening and saving without changes preserves original structured events.
            fragments = s.split_lines(rich)
            if list(map(signature, fragments)) == list(map(signature, s.split_lines(old_rich))):
                return RedirectResponse('/kalender-wijzigen?' + urlencode({'date': date, 'saved': 1}), 303)
            con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE date_local=? AND deleted=0', (date,))
            for event in before['events']:
                # Keep unrelated structured events (hours, category, metadata)
                # intact when their full rendered text remains in the day.
                event_fragments = s.split_lines(s.without_bold(s.clean_html(_event_line(event))))
                event_signatures = list(map(signature, event_fragments))
                remaining = list(map(signature, fragments))
                match = next((i for i in range(len(remaining) - len(event_signatures) + 1)
                              if remaining[i:i + len(event_signatures)] == event_signatures), None)
                if match is not None:
                    del fragments[match:match + len(event_signatures)]
                    continue
                con.execute("UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?", (s.core.now_iso(), event['id']))
            con.execute('DELETE FROM editor_days WHERE date_local=?', (date,))
            for fragment in fragments:
                con.execute('INSERT INTO editor_lines(date_local,body_html,title,custom_format) VALUES(?,?,?,?)',
                            (date, fragment, s.plain(fragment), int(s.has_custom_color(fragment))))
            # Retain all original records, including event metadata, for recovery.
            s.audit(con, 'calendar.day_changed', {'date': date, 'before': before, 'body_html': rich})
            con.commit()
        finally:
            con.close()
        return RedirectResponse('/kalender-wijzigen?' + urlencode({'date': date, 'saved': 1}), 303)
