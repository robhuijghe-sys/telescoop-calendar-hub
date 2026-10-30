"""The costume expires at Belgian midnight without editing calendar records."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.halloween_theme import halloween_active, halloween_document

for instant, active in [
    ('2026-10-29T22:59:59+00:00', False),
    ('2026-10-29T23:00:00+00:00', True),
    ('2026-10-30T12:00:00+00:00', True),
    ('2026-10-31T22:59:59+00:00', True),
    ('2026-10-31T23:00:00+00:00', False),
    ('2027-10-30T12:00:00+01:00', False),
]:
    clock = datetime.fromisoformat(instant)
    assert halloween_active(clock) is active, instant
    if not active:
        original = '<html lang="nl"><head></head><body>Original calendar</body></html>'
        assert halloween_document(original, clock) == original

temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db',
    CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json', APP_SECRET='test-only',
    ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
    CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))

from fastapi.testclient import TestClient
import app.simple_calendar as editor

class Clock(datetime):
    instant = datetime.fromisoformat('2026-10-31T23:59:59+01:00')

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

editor.datetime = Clock
with TestClient(editor.app) as client:
    response = client.post('/kalender-toevoegen', data={
        'date': '2026-11-02', 'lines': '10u30: overleg met Rob, Kathy en Rudi'}, follow_redirects=False)
    assert response.status_code == 303
    stored = editor.rows_all()
    before = client.get('/smartschool-calendar')
    assert 'id="halloween-hero"' in before.text
    assert 'class="halloween-cat"' in before.text
    assert 'id="halloween-script"' in before.text
    assert client.get('/smartschool-calendar', headers={'If-None-Match': before.headers['etag']}).status_code == 304
    # Both public editing pages remain clean, even during Halloween.
    for route in ('/', '/kalender-wijzigen', '/kalender-dag/2026-11-02'):
        assert 'halloween-' not in client.get(route).text
    assert client.get('/calendar-editor/halloween-school-2026.webp').status_code == 200
    Clock.instant = datetime.fromisoformat('2026-11-01T00:00:00+01:00')
    after = client.get('/smartschool-calendar', headers={'If-None-Match': before.headers['etag']})
    assert after.status_code == 200
    assert 'halloween-' not in after.text
    assert 'overleg met Rob, Kathy en Rudi' in after.text
    assert editor.rows_all() == stored
print('HALLOWEEN_SMOKE=PASS (Brussels boundaries, one-off dates, cache, editor isolation and stored records)')
