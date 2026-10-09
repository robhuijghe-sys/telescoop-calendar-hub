"""Verify migration, all write paths, repeated checks and preservation of notes/links."""
import os, sys, json, tempfile
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name+'/calendar.db', CALENDAR_SNAPSHOT_PATH=temp.name+'/snapshot.json',
                  APP_SECRET='format-test-only', ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
                  CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'entries': [
    {'date':'2026-10-15', 'html':'<span style="color:#123456">L5: CLB bezoek om 11:23 op school <a href="https://example.org/info">info</a></span>'},
    {'date':'2026-10-16', 'html':'Stage Tasnim K0K1 + refter – toezicht 10u40 - 10u55'},
]}))
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
from app.simple_calendar import app, rows_all
from app.display_format import normalize_text
from app.rich_editor import compact_lines, fragment_text
import app.main as core

# Literal newlines and HTML breaks can coexist, including across styled spans.
for rich in ['Vervanging Ananda\n<br/>1ste lesuur: L3 - MUVO',
             '<span style="color:red">Hanne afwezig\n</span><br/>Vervanging',
             '<p>Voorleesmoment</p>\n<br/><p>11u45: einde lessen</p>',
             'Teamvergadering<br/>* actuakring\n<br/>\n<br/>* taalonderwijs']:
    compact = compact_lines(rich)
    assert '\n\n' not in fragment_text(compact), compact
    assert not BeautifulSoup(compact, 'html.parser').find(['p','div'])
    assert compact_lines(compact) == compact
    assert fragment_text(compact).splitlines() == [x for x in fragment_text(rich).splitlines() if x.strip()]


with TestClient(app) as client:
    # Startup migrates existing free-text rows including stages without guessing their hours.
    rows = rows_all()
    assert rows[0]['title'] == '11u23: L5 - CLB bezoek info (op school)'
    assert rows[1]['title'] == 'Stage Tasnim K0K1 + refter – toezicht 10u40 - 10u55'
    assert Path(core.DB_PATH+'.before-format.bak').exists()
    con=core.db(); rich=con.execute('SELECT body_html FROM editor_lines ORDER BY id').fetchone()[0];con.close()
    assert '#123456' in rich and BeautifulSoup(rich,'html.parser').find('a')['href']=='https://example.org/info'
    assert 'info' in BeautifulSoup(rich,'html.parser').find('a').get_text()
    day=(datetime.now(core.TZ).date()+timedelta(days=1)).isoformat()
    # A plain form and an HTML form accept varied notation and preserve meaning.
    response=client.post('/kalender-toevoegen', data={'date':day,'lines':'11:11–11:12, L5, CLB op school'},follow_redirects=False)
    assert response.status_code==303
    assert any(r['title']=='11u11 - 11u12: L5 - CLB (op school)' for r in rows_all())
    response=client.post('/kalender-toevoegen',data={'date':day,'lines_html':'<span style="color:#654321">Stage Imane K0K1 van 8u30 tot 12u40 – toezicht 10u40 - 10u55</span>'},follow_redirects=False)
    assert response.status_code==303
    assert any(r['title']=='Stage Imane K0K1 van 8u30 tot 12u40 – toezicht 10u40 - 10u55' for r in rows_all())
    # A point-time outing, not only ranges and VM/NM, is valid.
    assert client.post('/kalender-toevoegen',data={'date':day,'category':'uitstap','structured':'1','lines':'9u30: K3 - Uitstap (Meise)'},follow_redirects=False).status_code==303
    # Structured event hours and location have priority over older hours in the title.
    assert client.post('/public/create',data={'date':day,'title':'CLB L5 om 10:00','start_time':'11:11','end_time':'11:12','location':'op school'},follow_redirects=False).status_code==303
    row=next(r for r in rows_all() if r['id'].startswith('event:'))
    con=core.db(); stored=dict(con.execute('SELECT * FROM events').fetchone());con.close()
    html=client.get('/smartschool-calendar').text
    soup=BeautifulSoup(html,'html.parser')
    for selector in ('.desktop-calendar','.mobile-calendar'):
        assert '11u11 - 11u12: L5 - CLB (op school)' in soup.select_one(selector).get_text()
        assert '10u00: L5 - CLB' not in soup.select_one(selector).get_text()
    assert not soup.select('.event-cell p,.mobile-events p')
    # Edits normalize regardless of whether text is entered via HTML or a single-line editor.
    response=client.post('/kalender-regel/'+row['id'], data={'date':day,'version':row['version'],'title_html':'<span style="color:#123456">L5: CLB om 11h11</span>','start_time':'11:11','end_time':'11:12','location':'op school'},follow_redirects=False)
    assert response.status_code==303,(response.status_code,response.text)
    assert client.post('/kalender-toevoegen',data={'date':day,'lines_html':'<p>Regel een</p><p>Regel twee</p>'},follow_redirects=False).status_code==303
    con=core.db()
    assert all(not BeautifulSoup(r[0], 'html.parser').find(['p','div']) for r in con.execute('SELECT body_html FROM editor_lines WHERE deleted=0'))
    con.close()
    # Cleanup also enforces the latest calendar-wide content/color/order rules.
    assert client.post('/kalender-toevoegen',data={'date':day,'lines_html':
        '<p>instapdag</p><p>instappers:</p><p>Ida Smet, Ines Delgrange Pierre</p>'
        '<p><span style="color:#8e44ad">15u30: Zorgoverleg</span></p>'
        '<p><span style="color:#8e44ad">16u00: Teamvergadering</span></p>'
        '<p><span style="color:#8e44ad">Vakgroep WO: 15u00</span></p>'
        '<p>3 weken LIST</p><p>Eline afwezig</p>'},follow_redirects=False).status_code==303
    rendered=BeautifulSoup(client.get('/smartschool-calendar').text,'html.parser')
    from app.rich_editor import fragment_text
    for selector in ('.desktop-calendar tr[data-calendar-date="'+day+'"] .event-cell',
                     '.mobile-calendar .mobile-day[data-calendar-date="'+day+'"] .mobile-events'):
        cell=rendered.select_one(selector)
        label=fragment_text(str(cell))
        assert label.startswith('Eline afwezig'),label
        assert 'instapdag' not in label.casefold()
        assert 'Ida Smet, Ines Delgrange Pierre' in label
        assert cell.select_one('.overleg-group') and 'Zorgoverleg' in cell.select_one('.overleg-group').get_text()
        assert len(cell.select('.meeting-group'))==2
        assert 'Stage' in cell.find_all(recursive=False)[-1].get_text()
        assert not cell.find('p') and not __import__('re').search(r'\n\s*\n',label)
    con=core.db()
    zorg=con.execute("SELECT body_html FROM editor_lines WHERE title LIKE '%Zorgoverleg%' AND deleted=0").fetchone()[0]
    team=con.execute("SELECT body_html FROM editor_lines WHERE title LIKE '%Teamvergadering%' AND deleted=0").fetchone()[0]
    assert '#000000' in zorg and '#8e44ad' not in zorg
    assert '#D31996' in team and '#8e44ad' not in team
    con.close()
    before=rows_all()
    result=client.post('/kalender-opmaak-controleren').json()
    assert result['checked']==len(before) and result['changed']==0 and result['timezone']=='Europe/Brussels'
    assert client.post('/kalender-opmaak-controleren').json()['changed']==0
    assert rows_all()==before
    con=core.db(); current=dict(con.execute('SELECT * FROM events').fetchone());con.close()
    assert current['id']==stored['id'] and current['start_at']==stored['start_at'] and current['end_at']==stored['end_at']
    assert client.get('/health').json()['format_check']['reason']=='scheduled'
    assert client.post('/kalender-opmaak-controleren',headers={'Origin':'https://unrelated.example'}).status_code==403

# Durations, deadlines and extra notes retain their role, even with repeated checks.
for original in ['Koloniekwekers: L5 en L6 — 2 uur in totaal.',
                 'Elektriciteit: L1, L2 en L3 — 1 uur per leerjaar, 3 uur in totaal.',
                 '🧊 IJskast leegmaken tegen 13u20',
                 'L2 & L4: CLB bezoek op school (vaccinatie)',
                 'Proclamatie K3 15u45 en L6 18u00.']:
    normalized=normalize_text(original)
    assert normalize_text(normalized)==normalized,(original,normalized,normalize_text(normalized))
assert '2 uur in totaal' in normalize_text('Koloniekwekers: L5 en L6 — 2 uur in totaal.')
assert normalize_text('🧊 IJskast leegmaken tegen 13u20')=='🧊 IJskast leegmaken tegen 13u20'
assert normalize_text('Proclamatie K3 15u45 en L6 18u00.')=='15u45: K3 - Proclamatie\n18u00: L6 - Proclamatie'
print('TCH_DISPLAY_FORMAT_SMOKE_TEST=PASS')
