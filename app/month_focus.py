"""Edit the existing monthly calendar focus with a versioned save."""
import hashlib
import json
import re

from fastapi import Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.calendar_dynamic import MONTH_NAMES


def focus_state(con, month):
    year, number = map(int, month.split('-'))
    key = f'month_focus_{year}_{number:02d}'
    row = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    layout = json.loads(con.execute("SELECT value FROM settings WHERE key='editor_layout'").fetchone()[0])
    fallback = layout.get('focus',{}).get(month,'')
    value = row[0] if row else None
    version = hashlib.sha256(json.dumps([value,fallback],ensure_ascii=False).encode()).hexdigest()
    return value if value is not None else fallback, version, key


def register_month_focus(s):
    def valid_month(month):
        if not re.fullmatch(r'[1-9]\d{3}-(?:0[1-9]|1[0-2])',month):
            raise HTTPException(400,'Kies een geldige maand.')
        return tuple(map(int,month.split('-')))

    def form(month, focus, version, error=''):
        year, number = valid_month(month)
        message = '<p class="warn" role="alert">'+s.esc(error)+'</p>' if error else ''
        body = (f'<div class="card"><h2>Maandfocus: {MONTH_NAMES[number]} {year}</h2>'
                '<p>Deze tekst staat onder de maandtitel in de kalender.</p>'+message+
                f'<form method="post" action="/kalender-maandfocus/{month}">'
                f'<input type="hidden" name="version" value="{s.esc(version,quote=True)}">'
                '<label for="month-focus">Focus voor deze maand</label>'
                f'<input id="month-focus" name="focus" maxlength="1000" value="{s.esc(focus,quote=True)}">'
                '<p><button>Maandfocus opslaan</button> '
                '<a class="btn alt" href="/kalender-wijzigen">Annuleren</a></p></form></div>')
        return s.page('Maandfocus wijzigen',body)

    @s.app.get('/kalender-maandfocus/{month}')
    def edit_focus(month: str):
        valid_month(month)
        con = s.core.db()
        try:
            con.execute('BEGIN')
            focus,version,_ = focus_state(con,month)
        finally:
            con.close()
        return HTMLResponse(form(month,focus,version))

    @s.app.post('/kalender-maandfocus/{month}')
    def save_focus(month: str, version: str = Form(...), focus: str = Form('')):
        valid_month(month)
        focus = focus.strip()
        if len(focus)>1000 or '\n' in focus or '\r' in focus:
            return HTMLResponse(form(month,focus[:1000],version,'Gebruik één focusregel van maximaal 1.000 tekens.'),status_code=400)
        con = s.core.db()
        try:
            con.execute('BEGIN IMMEDIATE')
            before,current,key = focus_state(con,month)
            if current!=version:
                return HTMLResponse(form(month,focus,current,'De maandfocus is ondertussen gewijzigd. Controleer je tekst voordat je opslaat.'),status_code=409)
            if before!=focus:
                con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,focus))
                s.audit(con,'calendar.month_focus_changed',{'month':month,'before':before,'after':focus})
                con.commit()
        finally:
            con.close()
        return RedirectResponse('/kalender-wijzigen?focus_saved=1',303)
