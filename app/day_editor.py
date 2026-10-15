"""One rich-text window per calendar day, with atomic, versioned saves."""
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlencode

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from bs4 import BeautifulSoup

from app.day_order import ordered_fragments
from app.calendar_dynamic import _event_line, MONTH_NAMES, MONTH_PALETTES
from app.day_cards import PANEL_LABELS, render_calendar, scoped_css
from app.section_editor import save_sections
from app.month_focus import focus_state
from app.rich_editor import bullet_lists


CSS = scoped_css('.calendar-preview') + scoped_css('.calendar-edit-panels') + """
main{max-width:1100px}.calendar-preview{padding:0;max-width:none}.calendar-preview .day-card{border:0;border-radius:0;overflow:visible}.calendar-preview .day-header{border-bottom:0}.calendar-preview .day-heading-actions{display:flex;align-items:center;gap:6px;flex-shrink:0}.day-heading-actions form{margin:0}.day-heading-actions .btn,.day-heading-actions button{padding:5px 10px;font-size:13px;line-height:1.15;margin:0;width:auto;white-space:nowrap}.calendar-preview .day-heading-actions .btn{background:white;color:#232563}.calendar-preview .day-heading-actions .danger{background:white;color:#E02020;border-color:#E02020}.editor-month-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-radius:10px;margin:24px 0 10px;color:white}.editor-month-heading h2{margin:0;color:white;font-size:22px;font-weight:700!important}.calendar-preview .editor-month-heading .btn{font-weight:400!important;background:white;color:#232563;font-size:13px;padding:6px 10px;white-space:nowrap}.editor-month-focus{margin:0 0 18px;padding:0 2px;font-size:13px;line-height:1.15}.editor-month-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px}
.day-dialog{border:1px solid #e5dfd8;border-radius:16px;padding:0;width:min(1000px,calc(100% - 24px));max-height:90vh;max-height:90dvh;color:#000}.day-dialog::backdrop{background:rgba(20,32,49,.55)}.day-dialog .day-form{padding:22px}.day-form .editor-visual,.day-form textarea{min-height:95px;max-height:50vh;overflow:auto;font-size:14px;line-height:1.15}.day-form .editor-visual,.day-form .editor-visual *{color:#000!important;font-weight:400!important;line-height:1.15}.day-form .editor-tools label,.day-form .editor-tools [data-action=color],.day-form .editor-tools [data-action=bold]{display:none}.day-actions{display:flex;flex-wrap:wrap;gap:10px;position:sticky;bottom:0;background:white;padding:12px 0;margin:0}.day-error{background:#fff5d9;border:1px solid #efd28a;border-radius:8px;padding:12px}.day-form h2{margin:0 0 10px;font-weight:700}label,.muted{font-size:14px}
@media(max-width:720px){.calendar-preview .day-header{flex-wrap:wrap}.editor-month-heading{flex-wrap:wrap}.editor-month-heading h2{font-size:20px}.day-dialog .day-form{padding:16px}.day-actions>*{width:100%}.day-form .editor-visual,.day-form textarea{min-height:95px}}
"""

CSS += """
.calendar-edit-panels{padding:0;max-width:none}.calendar-edit-panels .panel h3{margin-bottom:8px}.calendar-edit-panels .html-editor{margin:0}.calendar-edit-panels .editor-visual,.calendar-edit-panels textarea{min-height:95px;max-height:35vh}.calendar-edit-panels .editor-tools{padding:5px;gap:5px}.calendar-edit-panels .editor-tools button{font-size:12px;padding:4px 7px}.calendar-preview .panel h3{display:flex;justify-content:space-between;align-items:center;gap:8px}.calendar-preview .panel-edit{font-size:12px;line-height:1.15;padding:4px 7px;background:#fff;color:#232563;border:1px solid currentColor;white-space:nowrap;font-weight:400!important}
"""

CSS += '.day-form .editor-help{display:none}.day-form .html-editor>label{position:absolute;clip-path:inset(50%);width:1px;height:1px;overflow:hidden;white-space:nowrap}'

SCRIPT = '''<script id="whole-day-windows">
document.addEventListener('click', event => {
  const opener = event.target.closest('[data-edit-day]');
  if (opener) {
    const dialog = document.getElementById(opener.dataset.editDay);
    if (!dialog || !dialog.showModal) return;
    event.preventDefault(); dialog.showModal();
    const area = opener.dataset.editPanel ? dialog.querySelector('[data-editor-panel="' + opener.dataset.editPanel + '"]') : dialog;
    const field = area?.querySelector('.editor-visual:not([hidden]),textarea:not([hidden])');
    field?.focus(); field?.scrollIntoView({block:'nearest'});
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
  dialog.querySelectorAll('.editor-tools').forEach(tools => tools.addEventListener('click', e => {
    if (['color','bold','bullets','clear'].includes(e.target.closest('button')?.dataset.action)) dialog.dataset.changed = '1';
  }));
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

    # Use the same day version for edits and deletion from the overview.
    s.day_records = records

    def label(date):
        day = s.datetime.fromisoformat(date)
        weekdays = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']
        return weekdays[day.weekday()] + ' ' + day.strftime('%d/%m/%Y')

    def form(date, token, rich, modal=False, error='', conflict=False, sections=None):
        close = ' data-close-day' if modal else ''
        message = f'<p class="day-error" role="alert">{s.esc(error)}</p>' if error else ''
        sections=sections or {key:[] for key in PANEL_LABELS}
        placeholders={'absence':'DAG: naam afwezig','activities':'9u30: L3 - activiteit (plaats)','practical':'Afspraak of taak','meeting':'15u30: overleg\n* agendapunt','stage':'Naam, klasgroep en eventueel uren'}
        def field(key):
            value=bullet_lists([item['rich'] for item in sections.get(key,[])])
            return (f'<section class="panel {key}" id="panel-{date}-{key}" data-editor-panel="{key}"><h3>{PANEL_LABELS[key]}</h3>'
                    +s.editor('body_'+key,value,PANEL_LABELS[key],limit=100000,field_id=date+'-'+key,placeholder=placeholders[key])+'</section>')
        # Kept hidden for older clients that still submit the original whole-day field.
        fields=f'<textarea name="body_html" hidden>{s.esc(rich)}</textarea><input type="hidden" name="sections_present" value="1">'
        fields+='<div class="calendar-edit-panels">'+field('absence')+'<div class="day-columns"><div class="day-main">'
        fields+=''.join(field(key) for key in ('activities','practical','meeting'))
        fields+='</div><aside class="day-stages">'+field('stage')+'</aside></div></div>'
        action = (f'<a class="btn" href="/kalender-dag/{date}">Dag opnieuw openen</a>' if conflict else
                  '<button>Wijzigingen opslaan</button>')
        return (f'<form class="day-form" method="post" action="/kalender-dag/{date}">'
                f'<h2 id="day-title-{date}">{label(date)} bewerken</h2>'
                '<p class="muted">Bewerk de tekst in het juiste vak. Zet elke activiteit op een eigen regel. Voor een hele dag schrijf je DAG:. Je kunt een regel naar een ander vak verplaatsen door hem daar te plakken.</p>'
                + message + f'<input type="hidden" name="version" value="{s.esc(token, quote=True)}">'
                + fields + f'<p class="day-actions">{action} <a class="btn alt" href="/kalender-wijzigen"{close}>Annuleren</a></p></form>')

    def document(title, body):
        return s.page(title, body).replace('</style>', CSS + '</style>', 1)

    s.public._remove_route('/kalender-wijzigen', 'GET')

    @s.app.get('/kalender-wijzigen')
    def day_list(q: str = '', date: str = '', p: int = 1, saved: int = 0, deleted: int = 0, focus_saved: int = 0):
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
            p = min(max(1, p), max(1, (len(days) + 19) // 20))
            start = (p - 1) * 20
            visible = days[start:start + 20]
            data = render_calendar(s,hide_past=False,dates=[d[0] for d in visible],cards_only=True,connection=con,editor_data=True)
            cards,sections=data['cards'],data['sections']
            focuses = {d[0][:7]:focus_state(con,d[0][:7])[0] for d in visible}
        finally:
            con.close()
        body = '<p class="ok" role="status">Wijziging opgeslagen.</p>' if saved else ''
        if deleted:
            body += '<p class="ok" role="status">Dag gewist.</p>'
        if focus_saved:
            body += '<p class="ok" role="status">Maandfocus opgeslagen.</p>'
        body += (f'<div class="card"><h2>Kalender wijzigen</h2><form>'
                 f'<label>Zoeken op tekst of datum</label><input name="q" value="{s.esc(q, quote=True)}">'
                 f'<label>Datum (optioneel)</label><input type="date" name="date" value="{s.esc(date, quote=True)}">'
                 '<p><button>Zoeken</button> <a href="/kalender-wijzigen">Alles tonen</a></p></form>'
                 f'<p><a class="btn alt" href="/kalender-vervangen?{s.esc(urlencode({"q": q}), quote=True)}">Terugkerende tekst vervangen</a></p>'
                 f'<p class="muted">{len(days)} {"dag" if len(days) == 1 else "dagen"} · {sum(d[3] for d in days)} kalenderregels</p></div><div class="calendar-preview">')
        dialogs = []
        month = None
        for ds, token, rich, count in visible:
            if ds[:7]!=month:
                if month is not None:body+='</section>'
                month=ds[:7]
                year,number=map(int,month.split('-'))
                c1,c2=MONTH_PALETTES[number]
                body+=(f'<section class="editor-month" data-calendar-month="{month}">'
                       f'<div class="editor-month-heading" style="background:linear-gradient(135deg,{c1} 0%,{c2} 100%)">'
                       f'<h2>{MONTH_NAMES[number]} {year}</h2><a class="btn" href="/kalender-maandfocus/{month}">Maandfocus wijzigen</a></div>')
                if focuses[month]:body+=f'<div class="editor-month-focus"><span class="editor-month-dot" style="background:{c1}"></span>{s.esc(focuses[month])}</div>'
            ident = 'day-window-' + ds
            confirmation = 'Dag ' + label(ds) + ' wissen? Alle activiteiten, vervangingen en agenda’s van deze dag worden verwijderd.'
            confirm_script = s.esc('return confirm(' + json.dumps(confirmation, ensure_ascii=False) + ')', quote=True)
            card = BeautifulSoup(cards[ds],'html.parser')
            article = card.select_one('.calendar-day')
            article['class'].append('day-card')
            heading = card.select_one('.day-header')
            heading['class'].append('day-heading')
            badge=heading.select_one(':scope > span')
            if badge:badge.decompose()
            actions = BeautifulSoup(
                '<div class="day-heading-actions">'
                f'<a class="btn" href="/kalender-dag/{ds}" data-edit-day="{ident}">Bewerken</a>'
                f'<form method="post" action="/kalender-dag-verwijderen" onsubmit="{confirm_script}">'
                f'<input type="hidden" name="date" value="{ds}"><input type="hidden" name="version" value="{token}">'
                f'<button class="danger" aria-label="Dag {label(ds)} wissen">Dag wissen</button></form></div>','html.parser')
            heading.append(actions.div)
            card.select_one('.calendar-body')['class'].append('day-preview')
            for key in PANEL_LABELS:
                panel=card.select_one('.panel.'+key)
                if panel:
                    edit=card.new_tag('a',href='/kalender-dag/'+ds+'#panel-'+ds+'-'+key,attrs={'class':'btn panel-edit','data-edit-day':ident,'data-edit-panel':key})
                    edit.string='Wijzigen'
                    panel.h3.append(edit)
            body+=str(article)
            dialogs.append(f'<dialog class="day-dialog" id="{ident}" aria-labelledby="day-title-{ds}">'
                           + form(ds, token, rich, modal=True,sections=sections.get(ds)) + '</dialog>')
        if month is not None:body+='</section>'
        if not days:
            body += '<p>Geen dagen gevonden. Probeer een andere datum of zoektekst.</p>'
        for number, text in ((p - 1, 'Vorige'), (p + 1, 'Volgende')):
            if number > 0 and (number < p or start + 20 < len(days)):
                url = s.esc(urlencode({'q': q, 'date': date, 'p': number}), quote=True)
                body += f'<p><a href="/kalender-wijzigen?{url}">{text}</a></p>'
        body += '</div>'
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
            sections=render_calendar(s,hide_past=False,dates=[date],cards_only=True,connection=con,editor_data=True)['sections'].get(date)
        finally:
            con.close()
        return HTMLResponse(document('Dag bewerken', '<div class="card">' + form(date, token, rich,sections=sections) + '</div>'))

    @s.app.post('/kalender-dag/{date}')
    async def save_day(date: str, request: Request, version: str = Form(...), body_html: str = Form(''),sections_present: str = Form('')):
        s.valid_date(date)
        if sections_present=='1':
            posted=await request.form()
            values={key:posted.get('body_'+key) if 'body_'+key in posted else None for key in PANEL_LABELS}
            def error_page(date,token,values,error,status,conflict=False):
                sections={key:[{'rich':value[:100000]}] for key,value in values.items()}
                return HTMLResponse(document('Dag bewerken','<div class="card">'+form(date,token,'',error=error,conflict=conflict,sections=sections)+'</div>'),status_code=status)
            return save_sections(s,date,version,values,error_page,signature)
        rich = s.without_bold(s.clean_html(body_html))
        if len(body_html) > 100000 or len(rich) > 100000 or not s.plain(rich):
            return HTMLResponse(document('Dag bewerken', '<div class="card">' + form(
                date, version, rich[:100000], error='Vul kalendertekst in (maximaal 100.000 tekens). Gebruik “Dag wissen” in het overzicht om alles te wissen.') + '</div>'), status_code=400)
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
            from app.day_cards import retain_metadata
            original = list(before['basis'])
            for event in before['events']:
                original.append(dict(body_html=_event_line(event),activity_type=event['category'],whole_day=event['all_day']))
            metadata = retain_metadata(s,original,fragments)
            for fragment,(category,whole_day) in zip(fragments,metadata):
                con.execute('INSERT INTO editor_lines(date_local,body_html,title,custom_format,activity_type,whole_day) VALUES(?,?,?,?,?,?)',
                            (date, fragment, s.plain(fragment), int(s.has_custom_color(fragment)),category,whole_day))
            # Retain all original records, including event metadata, for recovery.
            s.audit(con, 'calendar.day_changed', {'date': date, 'before': before, 'body_html': rich})
            con.commit()
        finally:
            con.close()
        return RedirectResponse('/kalender-wijzigen?' + urlencode({'date': date, 'saved': 1}), 303)
