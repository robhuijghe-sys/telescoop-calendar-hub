import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db', CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json', APP_SECRET='test-only', ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false', CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {'2026-10': 'Focus lezen'}, 'entries': [{'date': '2026-10-01', 'label': 'do 01/10', 'html': '<span style="color:#c614a1">Bestaande <strong>afspraak</strong> <a href="/deeplink/123">document</a></span><br>Tweede afspraak'}]}))

from fastapi.testclient import TestClient
from app.simple_calendar import app, setup_editor, rows_all, split_lines
import app.main as core

with TestClient(app) as client:
    assert client.get('/').status_code == 200
    assert 'Meerdere regels toevoegen' in client.get('/').text
    assert '/login' not in client.get('/').text
    assert len(rows_all()) == 2
    assert Path(core.DB_PATH + '.before-public-editor.bak').exists()
    first = client.get('/smartschool-calendar')
    assert first.status_code == 200
    assert 'content="7200"' in first.text
    assert 'Aptos,Roboto' in first.text and '/calendar-fonts/roboto-latin-400.woff2' in first.text
    assert 'href="/" target="_blank" rel="noopener noreferrer">🔗 Kalender wijzigen</a>' in first.text and 'Focus lezen' in first.text
    assert 'https://telescoop-sgr8.smartschool.be/deeplink/123' in first.text
    assert client.get('/smartschool-calendar', headers={'If-None-Match': first.headers['etag']}).status_code == 304
    assert client.get('/calendar-fonts/roboto-latin-400.woff2').status_code == 200
    assert client.post('/kalender-toevoegen', data={'date': '2026-10-02', 'lines': 'Lien afwezig\nJorge neemt LO over\nVeronica begeleidt L1'}).status_code == 200
    assert len(rows_all()) == 5
    # Lost-response retry does not duplicate a batch.
    client.post('/kalender-toevoegen', data={'date': '2026-10-02', 'lines': 'Lien afwezig\nJorge neemt LO over\nVeronica begeleidt L1'})
    assert len(rows_all()) == 5
    assert client.post('/kalender-toevoegen', data={'date': '2026-10-02', 'lines': 'Valid\n' + 'x' * 1001}).status_code == 400
    assert len(rows_all()) == 5
    assert client.post('/kalender-toevoegen', data={'date': '2026-02-31', 'lines': 'Invalid'}).status_code == 400
    row = next(r for r in rows_all() if r['title'] == 'Jorge neemt LO over')
    assert client.post('/kalender-regel/' + row['id'], data={'version': row['version'], 'date': '2026-10-03', 'body_html': '<span onclick="alert(1)">Jorge neemt zwemmen over</span><script>alert(1)</script><a href="javascript:alert(1)">link</a>'}).status_code == 200
    assert client.post('/kalender-regel/' + row['id'], data={'version': row['version'], 'date': '2026-10-03', 'body_html': 'Stale'}).status_code == 409
    html = client.get('/smartschool-calendar').text
    assert 'onclick=' not in html and '<script>alert' not in html and 'javascript:' not in html
    assert 'Jorge neemt zwemmen over' in html
    row = next(r for r in rows_all() if r['title'] == 'Lien afwezig')
    assert client.post('/kalender-verwijderen/' + row['id'], data={'version': row['version']}).status_code == 200
    assert 'Lien afwezig' not in client.get('/smartschool-calendar').text
    assert 'Veronica begeleidt L1' in client.get('/smartschool-calendar').text
    setup_editor()
    assert len(rows_all()) == 4  # Restart neither reimports nor restores deleted rows.
    # Existing natural-language creation remains public and editable.
    assert client.post('/public/interpret', data={'prompt': 'Voeg op 6 oktober om 15.30 teamvergadering toe'}).status_code == 200
    assert client.post('/public/create', data={'title': 'Teamvergadering', 'date': '2026-10-06', 'start_time': '15:30', 'category': 'personeel'}).status_code == 200
    event = next(r for r in rows_all() if r['title'] == 'Teamvergadering')
    assert event['id'].startswith('event:')
    assert client.get('/kalender-regel/' + event['id']).status_code == 200
    assert client.post('/kalender-regel/' + event['id'], data={'version': event['version'], 'date': '2026-10-07', 'title': 'Nieuw overleg', 'start_time': '16:00', 'end_time': '17:00'}).status_code == 200
    event = next(r for r in rows_all() if r['title'] == 'Nieuw overleg')
    assert client.post('/kalender-verwijderen/' + event['id'], data={'version': event['version']}).status_code == 200
    assert 'Nieuw overleg' not in client.get('/smartschool-calendar').text
    assert client.post('/kalender-link/0', data={'description': 'Testlink', 'url': '/deeplink/456'}).status_code == 200
    con = core.db(); link = dict(con.execute("SELECT * FROM editor_links WHERE description='Testlink'").fetchone()); con.close()
    assert client.post('/kalender-link/' + str(link['id']), data={'description': 'Nieuwe link', 'url': 'https://example.org', 'version': 1}).status_code == 200
    assert client.post('/kalender-link/' + str(link['id']), data={'description': 'Old tab', 'url': 'https://example.org', 'version': 1}).status_code == 409
    assert 'Nieuwe link' in client.get('/smartschool-calendar').text
    assert client.post('/kalender-link/' + str(link['id']) + '/verwijderen', data={'version': 2}).status_code == 200
    assert 'Nieuwe link' not in client.get('/smartschool-calendar').text
    assert client.post('/kalender-link/0', data={'description': 'Unsafe', 'url': 'javascript:alert(1)'}).status_code == 400
    assert client.get('/smartschool-calendar', headers={'If-None-Match': first.headers['etag']}).status_code == 200
    assert client.post('/kalender-toevoegen', data={'date': '2026-10-02', 'lines': 'Cross site'}, headers={'Origin': 'https://unrelated.example'}).status_code == 403
    assert '<strong>' in split_lines('<span>Text <strong>bold</strong></span><br>next')[0]

    before_count = len(rows_all())
    assert 'placeholder="VM: K3: uitstap naar plantentuin"' in client.get('/').text
    assert client.post('/kalender-toevoegen', data={'date': '2026-10-08', 'structured': '1', 'lines': 'vm - k3 - uitstap naar plantentuin\n09:30: L2: bibliotheek'}).status_code == 200
    assert len(rows_all()) == before_count + 2
    assert any(r['title'] == 'VM: K3: uitstap naar plantentuin' for r in rows_all())
    assert any(r['title'] == '09:30: L2: bibliotheek' for r in rows_all())
    assert client.post('/kalender-toevoegen', data={'date': '2026-10-08', 'structured': '1', 'lines': 'NM: L1: klas\nOnvolledige regel'}).status_code == 400
    assert len(rows_all()) == before_count + 2

print('TCH_SIMPLE_EDITOR_SMOKE_TEST=PASS')
temp.cleanup()
