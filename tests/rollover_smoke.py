"""Check Belgian cutoff times in responses, caching and already-open calendars."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + '/calendar.db',
    CALENDAR_SNAPSHOT_PATH=temp.name + '/snapshot.json', APP_SECRET='test-only',
    ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
    CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import app.simple_calendar as editor

cases = []
# Each weekday, including the shorter Wednesday, in both summer and winter time.
for monday in ('2026-10-12', '2026-10-26'):
    for offset in range(7):
        day = datetime.fromisoformat(monday).replace(tzinfo=editor.core.TZ) + timedelta(days=offset)
        if offset < 5:
            cutoff = day.replace(hour=12 if offset == 2 else 15, minute=20 if offset == 2 else 15)
            cases.extend([(cutoff - timedelta(seconds=1), day.date()),
                          (cutoff, day.date() + timedelta(days=1))])
        else:
            cases.append((day.replace(hour=23, minute=59), day.date()))
# Date arithmetic must also work across a month/year and the daylight-saving weekend.
for instant, expected in [('2026-09-30T12:20:00+02:00', '2026-10-01'),
                          ('2026-12-31T15:15:00+01:00', '2027-01-01'),
                          ('2026-10-25T01:30:00+00:00', '2026-10-25')]:
    cases.append((datetime.fromisoformat(instant), datetime.fromisoformat(expected).date()))

for instant, expected in cases:
    assert editor.calendar_start_date(instant.astimezone(timezone.utc)) == expected, instant

class Clock(datetime):
    instant = datetime(2026, 10, 14, 12, 19, 59, tzinfo=editor.core.TZ)

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

editor.datetime = Clock
with TestClient(editor.app) as client:
    for day in ('2026-10-14', '2026-10-15', '2026-10-16'):
        response = client.post('/kalender-toevoegen', data={'date': day, 'lines': 'Les op ' + day}, follow_redirects=False)
        assert response.status_code == 303
    for day, hour, minute in [(14, 12, 20), (15, 15, 15)]:
        cutoff = datetime(2026, 10, day, hour, minute, tzinfo=editor.core.TZ)
        Clock.instant = cutoff - timedelta(seconds=1)
        before = client.get('/smartschool-calendar')
        assert f'data-calendar-date="2026-10-{day}"' in before.text
        assert client.get('/smartschool-calendar', headers={'If-None-Match': before.headers['etag']}).status_code == 304
        Clock.instant = cutoff
        after = client.get('/smartschool-calendar', headers={'If-None-Match': before.headers['etag']})
        assert after.status_code == 200  # The cache must expire at the cutoff, not midnight.
        assert f'data-calendar-date="2026-10-{day}"' not in after.text
        assert f'data-calendar-date="2026-10-{day+1}"' in after.text
        assert f'Les op 2026-10-{day}' in client.get('/kalender-dag/2026-10-' + str(day)).text
    assert len(editor.rows_all()) == 3  # Display changes never delete calendar records.

# Execute the actual inline script with a fake clock and DOM, including a tab
# that remains open and a suspended tab becoming visible at the cutoff.
javascript = BeautifulSoup(editor.ROLLOVER_SCRIPT, 'html.parser').script.string
node_test = r'''
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
for (const [instant, expected] of input.cases) {
  let now = Date.parse(instant);
  const RealDate = Date;
  class Clock extends RealDate {
    constructor(...args) { super(...(args.length ? args : [now])); }
    static now() { return now; }
  }
  let days, callback, visibility;
  const reset = () => { days = [expected, new RealDate(RealDate.parse(expected+'T00:00Z')-86400000).toISOString().slice(0,10)].map(date => ({dataset:{calendarDate:date}, remove(){this.removed=true;}})); };
  reset();
  const document = {
    querySelectorAll: selector => selector === '[data-calendar-date]' ? days.filter(d => !d.removed) : [],
    addEventListener: (event, handler) => { if (event === 'visibilitychange') visibility=handler; }
  };
  vm.runInNewContext(input.script, {Date:Clock, Intl, document, setTimeout:fn=>{callback=fn;}});
  const check = () => { if(days.filter(d=>!d.removed).map(d=>d.dataset.calendarDate).join()!==expected) throw new Error(instant); };
  check(); reset(); now-=60000; callback(); now+=60000; callback(); check();
  reset(); now-=60000; callback(); now+=60000; visibility(); check();
}
'''
subprocess.run(['node', '-e', node_test], input=json.dumps({'script': javascript,
    'cases': [(instant.isoformat(), expected.isoformat()) for instant, expected in cases]}), text=True, check=True)
print('TCH_ROLLOVER_SMOKE_TEST=PASS (27 time cases, response cache and open-tab script)')
