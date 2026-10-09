"""Whole-day saves preserve content and reject stale edits atomically."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db', CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json',
                  APP_SECRET='test-only', ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
                  CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))
from fastapi.testclient import TestClient
from app.simple_calendar import app, rows_all
import app.main as core

day = (datetime.now(core.TZ).date() + timedelta(days=1)).isoformat()
other = (datetime.now(core.TZ).date() + timedelta(days=2)).isoformat()


def edit(client):
    response = client.get('/kalender-dag/' + day)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, 'html.parser')
    return {'version': soup.select_one('input[name=version]')['value'],
            'body_html': soup.select_one('textarea[name=body_html]').get_text()}


with TestClient(app) as client:
    client.post('/kalender-toevoegen', data={'date': day, 'lines_html':
        '<span style="color:#8e44ad">15u30: teamvergadering</span><br>'
        '<span style="color:#8e44ad">* agenda: lezen <a href="https://example.org/agenda">document</a></span><br>'
        '<span style="color:#d01234;font-weight:700"><b>Eline</b> <strong>afwezig</strong></span>'})
    client.post('/public/create', data={'date': day, 'title': 'Bibliotheek', 'start_time': '09:00',
                                       'end_time': '10:00', 'location': 'Laken', 'description': 'Neem boeken mee'})
    client.post('/kalender-toevoegen', data={'date': other, 'lines': 'Andere dag'})
    listing = BeautifulSoup(client.get('/kalender-wijzigen').text, 'html.parser')
    assert len(listing.select('.day-card')) == 2
    assert len(listing.select('dialog')) == 2
    assert len(listing.select('[data-edit-day]')) == 2
    assert not listing.select('a[href^="/kalender-regel/"]')
    assert len(listing.select('dialog textarea')) == 2
    assert listing.select_one('[data-edit-day]').get_text() == 'Bewerken'
    delete_forms = listing.select('.day-heading-actions form')
    assert len(delete_forms) == 2
    assert all(f['action'] == '/kalender-dag-verwijderen' and f['method'] == 'post' for f in delete_forms)
    assert all('confirm(' in f['onsubmit'] and 'agenda’s' in f['onsubmit'] for f in delete_forms)
    assert all(f.select_one('button').get_text() == 'Dag wissen' for f in delete_forms)
    assert delete_forms[0].select_one('input[name=date]')['value'] == day
    assert delete_forms[0].select_one('input[name=version]')['value'] == edit(client)['version']
    for url in ('/', '/kalender-wijzigen', '/kalender-links', '/kalender-dag/' + day, '/login'):
        page = BeautifulSoup(client.get(url).text, 'html.parser')
        assert page.select_one('style#school-theme'), url
    assert not listing.select('.day-preview b,.day-preview strong')
    assert not any('font-weight:' in tag.get('style', '') for tag in listing.select('.day-preview [style]'))
    calendar = BeautifulSoup(client.get('/smartschool-calendar').text, 'html.parser')
    assert not calendar.select_one('style#school-theme')
    assert 'background:#fff5eb' in calendar.select_one('style').get_text()
    assert 'background:linear-gradient(135deg,' in calendar.select_one('.month-head')['style']
    assert not calendar.select('b,strong')
    assert not any('font-weight:' in tag.get('style', '') for tag in calendar.select('[style]'))
    assert '.wrap,.wrap *{font-weight:400!important}' in str(calendar)
    # Searching a single agenda phrase still opens all content on its day.
    search = BeautifulSoup(client.get('/kalender-wijzigen?q=boeken').text, 'html.parser')
    assert len(search.select('.day-card')) == 1
    assert 'Eline afwezig' in search.select_one('.day-preview').get_text()

    initial = edit(client)
    assert '9u00 - 10u00: Bibliotheek (Laken)' in initial['body_html']
    assert 'Neem boeken mee' in initial['body_html']
    before = rows_all()
    # Unmodified submits preserve IDs and original structured event metadata.
    assert client.post('/kalender-dag/' + day, data=initial, follow_redirects=False).status_code == 303
    assert rows_all() == before
    serialized = dict(initial, body_html=initial['body_html'].replace('#8e44ad', 'rgb(142, 68, 173)'))
    assert client.post('/kalender-dag/' + day, data=serialized, follow_redirects=False).status_code == 303
    assert rows_all() == before
    # Other-day changes do not block the save; changes on this day do.
    client.post('/kalender-toevoegen', data={'date': other, 'lines': 'Extra op andere dag'})
    changed = dict(initial, body_html=initial['body_html'].replace('agenda: lezen', 'agenda: woordenschat') + '<br>Nieuwe afspraak')
    result = client.post('/kalender-dag/' + day, data=changed, follow_redirects=False)
    assert result.status_code == 303
    current = rows_all()
    assert len([r for r in current if r['id'].startswith('event:')]) == 1
    assert any(r['title'] == 'Nieuwe afspraak' for r in current)
    rendered = BeautifulSoup(client.get('/smartschool-calendar').text, 'html.parser')
    for selector in ('.desktop-calendar .event-cell', '.mobile-calendar .mobile-events'):
        contents = rendered.select_one(selector)
        assert contents.get_text().count('Bibliotheek') == 1
        assert 'agenda: woordenschat' in contents.get_text()
        assert contents.select_one('a[href="https://example.org/agenda"]')
        assert 'agenda: lezen' not in contents.get_text()
        assert 'teamvergadering' in contents.select_one('.meeting-group').get_text()
    assert client.post('/kalender-dag/' + day, data=changed).status_code == 409
    assert rows_all() == current

    stale = edit(client)
    client.post('/kalender-toevoegen', data={'date': day, 'lines': 'Nieuw van collega'})
    before_conflict = rows_all()
    stale_delete = client.post('/kalender-dag-verwijderen', data={'date': day, 'version': stale['version']})
    assert stale_delete.status_code == 409 and 'Dag opnieuw bekijken' in stale_delete.text
    assert rows_all() == before_conflict
    stale['body_html'] += '<br>Mijn onopgeslagen tekst'
    conflict = client.post('/kalender-dag/' + day, data=stale)
    assert conflict.status_code == 409 and 'Mijn onopgeslagen tekst' in conflict.text
    assert 'Dag opnieuw openen' in conflict.text and rows_all() == before_conflict
    fresh = edit(client)
    assert client.post('/kalender-dag/' + day, data=dict(fresh, body_html='')).status_code == 400
    assert rows_all() == before_conflict
    # Editing a timed event in the full-day document does not duplicate it.
    fresh['body_html'] = fresh['body_html'].replace('Bibliotheek', 'Museum')
    fresh['body_html'] += '<br><span onclick="alert(1)">Veilig</span><script>alert(1)</script>'
    assert client.post('/kalender-dag/' + day, data=fresh).status_code == 200
    html = client.get('/smartschool-calendar').text
    assert 'Museum (Laken)' in html and '9u00 - 10u00:' in html
    assert 'Bibliotheek' not in html and 'onclick=' not in html and '<script>alert' not in html
    assert 'Neem boeken mee' in html and 'Andere dag' in html
    con = core.db()
    audit = json.loads(con.execute("SELECT payload FROM audit_log WHERE action='calendar.day_changed' ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert audit['before']['events'][0]['title'] == 'Bibliotheek'
    con.close()
    # Deletion in another window also invalidates an open day editor.
    client.post('/public/create', data={'date': day, 'title': 'Zwembad', 'start_time': '11:00'})
    stale = edit(client)
    untouched = [r for r in rows_all() if r['date'] == other]
    delete_data = {'date': day, 'version': stale['version']}
    response = client.post('/kalender-dag-verwijderen', data=delete_data, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/kalender-wijzigen?deleted=1'
    assert 'Dag gewist.' in client.get(response.headers['location']).text
    assert client.post('/kalender-dag-verwijderen', data=delete_data).status_code == 409
    assert client.post('/kalender-dag/' + day, data=stale).status_code == 409
    assert not [r for r in rows_all() if r['date'] == day]
    assert [r for r in rows_all() if r['date'] == other] == untouched
    calendar = BeautifulSoup(client.get('/smartschool-calendar').text, 'html.parser')
    assert not calendar.select('[data-calendar-date="' + day + '"]')
    assert len(calendar.select('[data-calendar-date="' + other + '"]')) == 2
    assert not BeautifulSoup(client.get('/kalender-wijzigen').text, 'html.parser').select('input[name=date][value="' + day + '"]')
    con = core.db()
    deleted = json.loads(con.execute("SELECT payload FROM audit_log WHERE action='calendar.day_deleted' ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert deleted['basis'] and deleted['events'][0]['title'] == 'Zwembad'
    con.close()
    assert client.get('/kalender-dag/2026-02-31').status_code == 400

print('TCH_DAY_EDITOR_SMOKE_TEST=PASS')
temp.cleanup()
