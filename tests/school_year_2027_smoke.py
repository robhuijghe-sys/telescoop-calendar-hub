"""Check teaching-week intervals, draft visibility and the Brussels release day."""
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name + "/calendar.db", CALENDAR_SNAPSHOT_PATH=temp.name + "/snapshot.json",
                  APP_SECRET="test-only", ADMIN_RESET_PASSWORD="", ENABLE_ADMIN_RECOVERY_LOG="false",
                  CALENDAR_SOURCE_GZ_B64="", CALENDAR_LINKS_GZ_B64="", CALENDAR_SNAPSHOT_GZ_B64="",
                  CALENDAR_FORMAT_AUTOCHECK="0")
Path(os.environ["CALENDAR_SNAPSHOT_PATH"]).write_text(json.dumps({"focus": {}, "entries": [
    {"date": "2027-06-25", "html": "Bestaande afspraak van dit schooljaar"},
    {"date": "2027-12-03", "html": "Bestaande afspraak van volgend schooljaar"},
]}))

from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
import app.simple_calendar as editor
from app.school_year_2027 import (build_plan, meeting_dates, school_day, school_week,
                                  seed_school_year, planned_lines, MARKER, PUBLICATION_KEY)
from app.display_format import normalize_text

class Clock(datetime):
    instant = datetime(2027, 6, 23, 23, 59, 59, tzinfo=editor.core.TZ)

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

editor.datetime = Clock
plan = build_plan()
assert all(normalize_text(title) == title for _, title, _ in planned_lines(plan))
assert plan["meetings"] == ["2027-09-07", "2027-10-05", "2027-11-09", "2027-12-07",
    "2028-01-18", "2028-02-15", "2028-03-21", "2028-05-02", "2028-05-30", "2028-06-27"]
assert plan["cycles"] == [
    {"number": 1, "sessions": ["2027-11-12", "2027-11-19", "2027-11-26"],
     "collect": "2027-10-04", "deadline": "2027-10-08", "agenda": "2027-09-07"},
    {"number": 2, "sessions": ["2028-02-04", "2028-02-11", "2028-02-18"],
     "collect": "2027-12-20", "deadline": "2027-12-24", "agenda": "2027-12-07"},
]
for first, last in zip(meeting_dates(), meeting_dates()[1:]):
    assert first.weekday() == last.weekday() == 1
    tuesdays = [first + timedelta(weeks=i) for i in range(1, (last-first).days//7+1)]
    assert sum(school_week(day) for day in tuesdays) == 4
assert not school_day(date(2027, 11, 5)) and not school_day(date(2028, 2, 29))
assert school_week(date(2028, 4, 18))  # Paasmaandag does not erase the teaching week.

with TestClient(editor.app) as client:
    con = editor.core.db()
    before = [tuple(row) for row in con.execute("SELECT * FROM editor_lines ORDER BY id")]
    assert seed_school_year(con, editor.core)
    assert not seed_school_year(con, editor.core)
    assert [tuple(row) for row in con.execute("SELECT * FROM editor_lines WHERE id<=2 ORDER BY id")] == before
    count = con.execute("SELECT COUNT(*) FROM editor_lines").fetchone()[0]
    assert count == 38
    assert con.execute("SELECT value FROM settings WHERE key=?", (MARKER,)).fetchone()
    assert json.loads(con.execute("SELECT value FROM settings WHERE key=?", (PUBLICATION_KEY,)).fetchone()[0])["publish_on"] == "2027-06-24"
    con.close()

    # Draft remains editable while the ordinary public calendar hides all of it,
    # including pre-existing and newly created items inside the school-year range.
    preview = client.get("/kalender-schooljaar/2027-2028")
    assert preview.status_code == 200 and "Concept" in preview.text
    assert "12 november 2027" in preview.text and "24 juni 2027" in preview.text
    assert "Bestaande afspraak van volgend schooljaar" in preview.text
    assert client.get("/kalender-dag/2027-11-12").status_code == 200
    public = client.get("/smartschool-calendar")
    assert "Bestaande afspraak van dit schooljaar" in public.text
    assert "Bestaande afspraak van volgend schooljaar" not in public.text
    assert 'data-calendar-date="2027-11-12"' not in public.text
    assert client.get("/smartschool-calendar", headers={"If-None-Match": public.headers["etag"]}).status_code == 304

    # No deployment, database writes or warm-cache reset at publication time.
    Clock.instant = datetime(2027, 6, 24, 0, 0, 0, tzinfo=editor.core.TZ)
    published = client.get("/smartschool-calendar", headers={"If-None-Match": public.headers["etag"]})
    assert published.status_code == 200
    assert published.headers["etag"] != public.headers["etag"]
    assert 'data-calendar-date="2027-11-12"' in published.text
    assert 'data-calendar-date="2028-02-18"' in published.text
    assert "Bestaande afspraak van dit schooljaar" in published.text
    assert "Bestaande afspraak van volgend schooljaar" in published.text
    assert "Gepubliceerd in de schoolkalender" in client.get("/kalender-schooljaar/2027-2028").text
    soup = BeautifulSoup(published.text, "html.parser")
    agendas = soup.select('[data-calendar-date="2027-09-07"] .meeting li')
    assert any("Start onderzoek: vragen verzamelen" in li.get_text() for li in agendas)
    assert not soup.select('[data-calendar-date="2027-11-02"] .meeting')
    assert not soup.select('[data-calendar-date="2028-02-29"] .meeting')

    # Restart must preserve later edits/deletions and the already prepared plan.
    con = editor.core.db()
    assert con.execute("SELECT COUNT(*) FROM editor_lines").fetchone()[0] == count
    ident = con.execute("SELECT id FROM editor_lines WHERE date_local='2027-11-12'").fetchone()[0]
    con.execute("UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?", (ident,))
    con.commit()
    assert not seed_school_year(con, editor.core)
    assert con.execute("SELECT deleted FROM editor_lines WHERE id=?", (ident,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM editor_lines").fetchone()[0] == count
    con.close()

print("SCHOOL_YEAR_2027_SMOKE_TEST=PASS")
