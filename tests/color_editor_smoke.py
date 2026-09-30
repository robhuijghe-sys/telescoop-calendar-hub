"""Exercise storage and rendered colors through the real public endpoints."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db', CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json', APP_SECRET='test-only', ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false', CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'entries': [{'date': '2026-10-01', 'html': '<span style="color:#5dade2">Bestaande afspraak</span>'}]}))

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from app.simple_calendar import app, rows_all, setup_editor, plain
from app.rich_editor import reshape_html
import app.main as core

def stored(query):
    con = core.db()
    row = dict(con.execute(query).fetchone())
    con.close()
    return row

with TestClient(app) as client:
    home = client.get('/').text
    assert 'Een activiteit in gewone taal' not in home and 'Meerdere regels toevoegen' not in home
    assert 'Toevoegen aan kalender' in home and 'name="lines_html"' in home
    assert client.get('/calendar-editor/editor.js').status_code == 200
    original = rows_all()[0]
    assert 'html-editor' in client.get('/kalender-regel/' + original['id']).text
    response = client.post('/kalender-toevoegen', follow_redirects=False, data={
        'date': '2026-10-02', 'structured': '1',
        'lines_html': '<div style="color:#812345">vm: k3: uitstap naar <b>Meise</b></div><div>09:30: L2: <span style="color:#186a3b">bibliotheek</span></div>'})
    assert response.status_code == 303, response.text
    row = stored("SELECT * FROM editor_lines WHERE title='VM, K3, Meise'")
    assert '#812345' in row['body_html'] and '<b>Meise</b>' in row['body_html']
    assert row['custom_format'] == 1
    row2 = stored("SELECT * FROM editor_lines WHERE title='09:30: L2: bibliotheek'")
    assert '#186a3b' in row2['body_html']
    count = len(rows_all())
    bad = client.post('/kalender-toevoegen', data={'date':'2026-10-02', 'structured':'1', 'lines_html':'<p>VM: L3: geldig</p><p>ongeldig</p>'})
    assert bad.status_code == 400 and len(rows_all()) == count
    response = client.post('/kalender-toevoegen', data={'date':'2026-10-02', 'structured':'1', 'lines_html':'VM: L3: leesles\nNM: L3: sport'}, follow_redirects=False)
    assert response.status_code == 303 and len(rows_all()) == count + 2
    updated = client.post('/kalender-regel/' + original['id'], data={'date':'2026-10-01','version':original['version'], 'body_html':'<span style="color:#912345">Jorge neemt LO over</span><img src=x onerror=alert(1)><script>alert(1)</script>'})
    assert updated.status_code == 200
    doc = BeautifulSoup(client.get('/smartschool-calendar').text, 'html.parser')
    for node in doc.select('[data-custom-format]'):
        assert not node.find_parent(class_='replacement-line')
    assert '#912345' in str(doc) and 'onerror=' not in str(doc)
    assert client.post('/kalender-regel/' + original['id'], data={'date':'2026-10-01','version':original['version'],'body_html':'verouderd'}).status_code == 409

    client.post('/public/create', data={'title':'Stage Imane','date':'2026-10-08','start_time':'08:30','end_time':'12:40','category':'stage'}, follow_redirects=False)
    event = next(r for r in rows_all() if r['title'] == 'Stage Imane')
    response = client.post('/kalender-regel/' + event['id'], data={'date':'2026-10-08', 'version':event['version'], 'title_html':'Stage <span style="color:#994422">Imane</span>', 'description_html':'<span style="color:#1122aa">K0K1</span><br>Mentor', 'start_time':'08:30','end_time':'12:40','category':'stage'})
    assert response.status_code == 200, response.text
    doc = BeautifulSoup(client.get('/smartschool-calendar').text, 'html.parser')
    stage = next(n for n in doc.select('[data-custom-format]') if 'Stage Imane' in n.get_text())
    assert stage.get_text() == 'Stage Imane van 8u30 tot 12u40'
    assert '#994422' in str(stage) and '#1122aa' in str(doc)
    page = client.get('/kalender-regel/' + event['id']).text
    assert 'name="title_html"' in page and 'name="description_html"' in page

    response = client.post('/kalender-link/0', data={'description_html':'<a href="https://elsewhere.test"><span style="color:#632a78">Documenten</span></a>','url':'https://example.org'})
    assert response.status_code == 200, response.text
    doc = BeautifulSoup(client.get('/smartschool-calendar').text, 'html.parser')
    link = doc.select_one('a[href="https://example.org"]')
    assert '#632a78' in str(link) and not link.find('a')
    labels = BeautifulSoup(client.get('/kalender-links').text, 'html.parser')
    ids = [n['id'] for n in labels.select('[id]')]
    assert len(ids) == len(set(ids))
    before = [(r['id'],r['title'],r['version']) for r in rows_all()]
    setup_editor()
    assert before == [(r['id'],r['title'],r['version']) for r in rows_all()]
    assert '#632a78' in client.get('/smartschool-calendar').text
    assert plain('Bo<span style="color:red">ek</span>') == 'Boek'
    assert plain(reshape_html('vm: <span>k3</span>: uitstap naar Meise', 'VM, K3, Meise')) == 'VM, K3, Meise'

print('TCH_COLOR_EDITOR_SMOKE_TEST=PASS')
