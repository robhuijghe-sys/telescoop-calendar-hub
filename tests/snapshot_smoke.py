import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

tmpdb = os.path.join(tempfile.gettempdir(), "tch-snapshot-smoke.db")
tmpsnap = os.path.join(tempfile.gettempdir(), "tch-calendar-snapshot.json")
for p in (tmpdb, tmpsnap):
    try: os.remove(p)
    except FileNotFoundError: pass

os.environ["DB_PATH"] = tmpdb
os.environ["CALENDAR_SNAPSHOT_PATH"] = tmpsnap
os.environ["APP_SECRET"] = "snapshot-smoke-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "smoke@example.org"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "SmokeTest-Initial-Password-123!"
os.environ["COOKIE_SECURE"] = "false"

# The renderer intentionally excludes earlier months. Keep this fixture in
# the current month so an October deployment can still validate the snapshot.
base_day = datetime.now(ZoneInfo('Europe/Brussels')).date().replace(day=1)
live_day = base_day.replace(day=2)
Path(tmpsnap).write_text(json.dumps({
    "focus": {base_day.strftime('%Y-%m'): "KS: HOEKENWERK ▪▪▪ LS: SPELLING"},
    "entries": [{
        "date": base_day.isoformat(),
        "label": base_day.strftime('%d/%m'),
        "html": "<span>BESTAANDE BASISAFSPRAAK</span>"
    }]
}, ensure_ascii=False), encoding="utf-8")

from fastapi.testclient import TestClient
from app.public_calendar_snapshot import app
import app.main as core

with TestClient(app) as client:
    con = core.db(); now = core.now_iso()
    con.execute("INSERT INTO events(title,description,start_at,end_at,all_day,location,audience,category,status,source_prompt,visible_in_embed,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Nieuwe teamvergadering", "", base_day.isoformat() + "T13:30:00+00:00", base_day.isoformat() + "T14:30:00+00:00", 0, "", "[]", "personeel", "published", "", 1, 0, now, now))
    con.execute("INSERT INTO events(title,description,start_at,end_at,all_day,location,audience,category,status,source_prompt,visible_in_embed,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Kerstmis", "", live_day.isoformat() + "T11:00:00+00:00", live_day.isoformat() + "T12:00:00+00:00", 1, "", "[]", "uitstap", "published", "", 1, 0, now, now))
    con.commit(); con.close()
    r = client.get("/smartschool-calendar")
    assert r.status_code == 200
    assert "BESTAANDE BASISAFSPRAAK" in r.text
    assert "Nieuwe teamvergadering" in r.text
    assert "KS: HOEKENWERK" in r.text
    assert 'http-equiv="refresh" content="30"' in r.text
    assert "@media(max-width:560px)" in r.text
    assert r.headers.get("cache-control", "").startswith("no-store")
    assert 'class="event-cell live-only"' in r.text
    assert ".event-cell.live-only{vertical-align:middle}" in r.text
    assert ">Kerstmis</span>" in r.text or "Kerstmis" in r.text

print("TCH_SNAPSHOT_SMOKE_TEST=PASS")
for p in (tmpdb, tmpsnap):
    try: os.remove(p)
    except FileNotFoundError: pass
