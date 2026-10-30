"""Christmas starts and stops at Brussels midnight; records remain unchanged."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.christmas_theme import christmas_active, christmas_document

original = '<html lang="nl"><head></head><body><div class="links"></div>Original calendar</body></html>'
for instant, active in [
    ('2026-12-09T22:59:59+00:00', False),
    ('2026-12-09T23:00:00+00:00', True),
    ('2026-12-10T12:00:00+00:00', True),
    ('2026-12-25T22:59:59+00:00', True),
    ('2026-12-25T23:00:00+00:00', False),
    ('2027-12-10T12:00:00+01:00', False),
]:
    clock = datetime.fromisoformat(instant)
    assert christmas_active(clock) is active, instant
    document = christmas_document(original, clock)
    assert ('id="christmas-hero"' in document) is active, instant
    if clock.year == 2027 or clock.day == 25 and not active:
        assert document == original

temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db',
    CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json', APP_SECRET='test-only',
    ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
    CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))

from fastapi.testclient import TestClient
import app.simple_calendar as editor

class Clock(datetime):
    instant = datetime.fromisoformat('2026-12-09T23:59:59+01:00')

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

editor.datetime = Clock
with TestClient(editor.app) as client:
    response = client.post('/kalender-toevoegen', data={
        'date': '2026-12-28', 'lines': '10u30: overleg met Rob, Kathy en Rudi'}, follow_redirects=False)
    assert response.status_code == 303
    stored = editor.rows_all()
    before = client.get('/smartschool-calendar')
    assert 'id="christmas-start-watch"' in before.text
    assert 'id="christmas-hero"' not in before.text
    Clock.instant = datetime.fromisoformat('2026-12-10T00:00:00+01:00')
    festive = client.get('/smartschool-calendar', headers={'If-None-Match': before.headers['etag']})
    assert festive.status_code == 200
    assert 'id="christmas-hero"' in festive.text
    assert 'class="christmas-rudolph"' in festive.text
    assert 'id="christmas-script"' in festive.text
    assert 'halloween-' not in festive.text
    assert client.get('/smartschool-calendar', headers={'If-None-Match': festive.headers['etag']}).status_code == 304
    for route in ('/', '/kalender-wijzigen', '/kalender-dag/2026-12-28'):
        assert 'christmas-' not in client.get(route).text
    assert client.get('/calendar-editor/christmas-school-2026.webp').status_code == 200
    Clock.instant = datetime.fromisoformat('2026-12-26T00:00:00+01:00')
    after = client.get('/smartschool-calendar', headers={'If-None-Match': festive.headers['etag']})
    assert after.status_code == 200
    assert 'christmas-' not in after.text
    assert 'overleg met Rob, Kathy en Rudi' in after.text
    assert editor.rows_all() == stored
print('CHRISTMAS_SMOKE=PASS (Brussels start/end, one-off dates, cache, editor isolation and stored records)')
