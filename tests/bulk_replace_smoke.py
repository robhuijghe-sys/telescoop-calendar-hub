"""Batch replacements preserve styling, reject stale previews and undo atomically."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db', CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json',
                  APP_SECRET='test-only', ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
                  CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from app.simple_calendar import app, rows_all
import app.main as core

today = datetime.now(core.TZ).date()
days = [(today + timedelta(days=i)).isoformat() for i in (-1, 0, 1, 2, 3)]


def token(response):
    assert response.status_code == 200, response.text
    return BeautifulSoup(response.text, 'html.parser').select_one('input[name=token]')['value']


def state():
    con = core.db()
    result = [[dict(r) for r in con.execute('SELECT * FROM ' + table + ' ORDER BY id')]
              for table in ('editor_lines', 'events')]
    con.close()
    return result


with TestClient(app) as c:
    for date in days[:4]:
        c.post('/kalender-toevoegen', data={'date': date, 'lines_html':
            '<span style="color:#5dade2">Stage <span>Fati</span><span>ma</span> – toezicht 10u40 - 10u55</span>'
            '<br><span style="color:#203555">Niet wijzigen <a href="https://example.org/agenda">agenda</a></span>'})
    c.post('/kalender-toevoegen', data={'date': days[4], 'lines_html': '<span style="color:#5dade2">Stage fatima – andere regel</span>'})
    c.post('/public/create', data={'date': days[1], 'title': 'Fatima bibliotheek', 'start_time': '09:00',
                                   'end_time': '10:00', 'location': 'Laken', 'description': 'Fatima neemt boeken mee'})
    params = dict(find='Fatima', replacement='Fatima Zahra', mode='text', scope='future')
    before = state()
    preview = c.post('/kalender-vervangen/voorbeeld', data=params)
    soup = BeautifulSoup(preview.text, 'html.parser')
    assert len(soup.select('.replace-result')) == 6
    assert state() == before  # Read-only preview, including structured events.
    assert soup.select_one('select[name=scope] option[selected]')['value'] == 'future'
    assert not c.post('/kalender-vervangen/voorbeeld', data=dict(params, find='no-match')).text.count('Alle 6 regels vervangen')
    assert c.post('/kalender-vervangen/toepassen', data={'token': 'tampered'}).status_code == 400
    expired = core.signer.dumps(dict(kind='replace-preview', created=0))
    assert c.post('/kalender-vervangen/toepassen', data={'token': expired}).status_code == 400
    # A newly matching record invalidates the full preview before any write.
    stale = token(preview)
    c.post('/kalender-toevoegen', data={'date': days[4], 'lines': 'Fatima nieuwe afspraak'})
    with_new = state()
    assert c.post('/kalender-vervangen/toepassen', data={'token': stale}).status_code == 409
    assert state() == with_new
    # A record outside the affected set does not cause a spurious conflict.
    fresh = token(c.post('/kalender-vervangen/voorbeeld', data=params))
    c.post('/kalender-toevoegen', data={'date': days[4], 'lines': 'Extra andere afspraak'})
    response = c.post('/kalender-vervangen/toepassen', data={'token': fresh})
    undo = token(response)
    assert '7 regels op 4 dagen' in response.text
    after = state()
    assert after[1][0]['visible_in_embed'] == 0
    assert after[1][0]['start_at'] == before[1][0]['start_at']
    assert after[1][0]['end_at'] == before[1][0]['end_at']
    assert after[1][0]['location'] == 'Laken'
    future = [r for r in rows_all() if r['date'] >= days[1]]
    assert sum('Fatima Zahra' in r['title'] for r in future) == 7
    assert 'Stage Fatima – toezicht' in next(r['title'] for r in rows_all() if r['date'] == days[0] and r['title'].startswith('Stage'))
    assert '<span style="color:#5dade2">' in after[0][2]['body_html']
    assert any('href="https://example.org/agenda"' in r['body_html'] for r in after[0])
    # Replay cannot accidentally replace the replacement itself.
    assert c.post('/kalender-vervangen/toepassen', data={'token': fresh}).status_code == 409
    assert state() == after
    result = c.post('/kalender-vervangen/ongedaan-maken', data={'token': undo})
    assert result.status_code == 200
    restored = state()
    assert restored[1][0]['visible_in_embed'] == 1
    assert restored[1][0]['title'] == 'Fatima bibliotheek'
    assert not any('Fatima Zahra' in r['title'] for r in rows_all())
    assert c.post('/kalender-vervangen/ongedaan-maken', data={'token': undo}).status_code == 409
    # Exact whole-line replacement only changes the chosen period and case.
    line_params = dict(find='Stage Fatima – toezicht 10u40 - 10u55', replacement='Stage Fatima – toezicht 10u45 - 11u00',
                       mode='line', scope='period', start=days[2], end=days[3], sensitive=1)
    exact = c.post('/kalender-vervangen/voorbeeld', data=line_params)
    assert len(BeautifulSoup(exact.text, 'html.parser').select('.replace-result')) == 2
    exact_apply = c.post('/kalender-vervangen/toepassen', data={'token': token(exact)})
    assert '2 regels op 2 dagen' in exact_apply.text
    assert not any('10u45' in r['title'] for r in rows_all() if r['date'] not in days[2:4])
    exact_undo = token(exact_apply)
    c.post('/kalender-toevoegen', data={'date': days[2], 'lines': 'Nieuwe collega-afspraak'})
    # Whole-day editing bumps changed record versions; undo must refuse all.
    edit = BeautifulSoup(c.get('/kalender-dag/' + days[2]).text, 'html.parser')
    c.post('/kalender-dag/' + days[2], data={'version': edit.select_one('input[name=version]')['value'],
        'body_html': edit.select_one('textarea[name=body_html]').get_text().replace('10u45', '10u46')})
    conflict_state = state()
    assert c.post('/kalender-vervangen/ongedaan-maken', data={'token': exact_undo}).status_code == 409
    assert state() == conflict_state
    all_days = c.post('/kalender-vervangen/voorbeeld', data=dict(params, scope='all', sensitive=1))
    assert any(days[0][8:] + '/' + days[0][5:7] + '/' + days[0][:4] in el.get_text()
               for el in BeautifulSoup(all_days.text, 'html.parser').select('.replace-date'))
    # Literal HTML is text, not markup, and replacements do not alter link URLs.
    literal = token(c.post('/kalender-vervangen/voorbeeld', data=dict(params, find='agenda', replacement='<script>bad</script>', scope='all')))
    c.post('/kalender-vervangen/toepassen', data={'token': literal})
    rich = ''.join(r['body_html'] for r in state()[0] if not r['deleted'])
    assert '<script>bad</script>' not in rich and '&lt;script&gt;bad&lt;/script&gt;' in rich
    assert 'href="https://example.org/agenda"' in rich
    assert c.post('/kalender-vervangen/voorbeeld', data=dict(params, scope='period', start=days[3], end=days[2])).status_code == 400
    assert c.post('/kalender-vervangen/voorbeeld', data=dict(params, find='')).status_code == 400
    assert c.post('/kalender-vervangen/voorbeeld', data=dict(params, replacement='bad\ntext')).status_code == 400
    assert c.post('/kalender-vervangen/voorbeeld', data=params, headers={'origin': 'https://wrong.example'}).status_code == 403
    assert c.get('/kalender-voorstellen').status_code == 404
    assert '/kalender-voorstellen' not in c.get('/').text
    assert c.get('/kalender-vervangen?q=Fatima').status_code == 200

print('TCH_BULK_REPLACE_SMOKE_TEST=PASS')
temp.cleanup()
