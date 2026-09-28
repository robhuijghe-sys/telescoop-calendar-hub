"""Stage display regression: local hours, existing data and both calendar views."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(
    DB_PATH=temp.name + '/calendar.db',
    CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json', APP_SECRET='test-only',
    ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
    CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from app.simple_calendar import app
from app.calendar_dynamic import _event_line, infer_category
import app.main as core

with TestClient(app) as client:
    day = (datetime.now(core.TZ).date() + timedelta(days=1)).isoformat()
    for title, start, end, category in [
        ('Stage Imane K0K1', '08:30', '12:40', 'algemeen'),
        ('Oudercontact L1', '15:30', '17:00', 'ouders'),
    ]:
        assert client.post('/public/create', follow_redirects=False, data={
            'title': title, 'date': day, 'start_time': start, 'end_time': end,
            'category': category}).status_code == 303
    con = core.db()
    original = dict(con.execute("SELECT * FROM events WHERE title='Stage Imane K0K1'").fetchone())
    con.close()
    response = client.get('/smartschool-calendar')
    soup = BeautifulSoup(response.text, 'html.parser')
    expected = 'Stage Imane K0K1 van 8u30 tot 12u40'
    for selector in ('.desktop-calendar', '.mobile-calendar'):
        view = soup.select_one(selector)
        label = view.find('span', string=expected)
        assert label and label['style'] == 'color:#5dade2;font-weight:700'
        assert '15.30-17.00u: Oudercontact L1' in view.get_text()
        assert view.get_text().count(expected) == 1
        assert '08.30-12.40u: Stage' not in view.get_text()
    # Rendering is presentation only: titles, timestamps and class names stay stored.
    con = core.db()
    assert dict(con.execute('SELECT * FROM events WHERE id=?', (original['id'],)).fetchone()) == original
    con.close()
    for start, end in [('2027-01-07T07:30:00+00:00', '2027-01-07T11:40:00+00:00'),
                       ('2026-10-01T06:30:00+00:00', '2026-10-01T10:40:00+00:00')]:
        assert expected in _event_line({**original, 'start_at': start, 'end_at': end})
    # No duplicate hours when the title already contains a time range or a surname with 'van'.
    full = _event_line({**original, 'title': 'Stage Jan van Damme van 9u00 tot 13u00 (+ refter)'})
    assert 'Stage Jan van Damme van 8u30 tot 12u40 (+ refter)' in full
    assert '9u00' not in full
    assert 'Stage Noha' in _event_line({**original, 'title': 'Stage Noha', 'all_day': 1})
    assert ' van ' not in _event_line({**original, 'title': 'Stage Noha', 'all_day': 1})
    assert '&lt;script&gt;' in _event_line({**original, 'title': 'Stage <script>'})
    assert infer_category('Stage Fatima Zahra van 13u20 tot 17u00') == 'stage'
    # Plain-line additions get the same blue and bold style as timed stage events.
    assert client.post('/kalender-toevoegen', follow_redirects=False, data={
        'date': day, 'lines': 'Stage Fatima Zahra van 13u20 tot 17u00'}).status_code == 303
    updated = client.get('/smartschool-calendar')
    label = BeautifulSoup(updated.text, 'html.parser').find('span', string='Stage Fatima Zahra van 13u20 tot 17u00')
    assert label and label['style'] == 'color:#5dade2;font-weight:700'
    assert updated.headers['etag'] != response.headers['etag']

print('OK: stages blue/bold, local hours after name, both views, no data changes or duplicate hours')
