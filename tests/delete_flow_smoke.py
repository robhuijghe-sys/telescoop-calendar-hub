import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

tmpdb = os.path.join(tempfile.gettempdir(), "tch-delete-flow-smoke.db")
tmpsnap = os.path.join(tempfile.gettempdir(), "tch-delete-flow-snapshot.json")
for path in (tmpdb, tmpsnap):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

os.environ["DB_PATH"] = tmpdb
os.environ["APP_SECRET"] = "delete-flow-smoke-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "smoke@example.org"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "SmokeTest-Initial-Password-123!"
os.environ["COOKIE_SECURE"] = "false"
os.environ["CALENDAR_SNAPSHOT_PATH"] = tmpsnap

Path(tmpsnap).write_text(json.dumps({
    "version": 1,
    "focus": {},
    "entries": [{
        "date": "2026-12-02",
        "label": "woe 02/12",
        "html": '<span style="color:#c614a1">directie afwezig: SGE</span><br><span>andere afspraak blijft staan</span>'
    }]
}, ensure_ascii=False), encoding="utf-8")

from fastapi.testclient import TestClient
from app.public_calendar_snapshot import app
import app.main as core

with TestClient(app) as client:
    now = core.now_iso()
    con = core.db()
    cur = con.execute(
        "INSERT INTO events(title,description,start_at,end_at,all_day,location,audience,category,status,source_prompt,visible_in_embed,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "Directie afwezig",
            "",
            "2026-12-01T11:00:00+00:00",
            "2026-12-01T12:00:00+00:00",
            1,
            "",
            "[]",
            "waarschuwing",
            "published",
            "voeg toe 1 december directie afwezig",
            1,
            0,
            now,
            now,
        ),
    )
    event_id = cur.lastrowid
    con.commit(); con.close()

    r = client.get("/")
    assert r.status_code == 200
    assert "toevoegen of verwijderen" in r.text

    # Delete a dynamic Hub event.
    r = client.post("/public/interpret", data={"prompt": "verwijder op 1 december afwezigheid directie"})
    assert r.status_code == 200, r.text
    assert "Directie afwezig" in r.text
    assert "Geselecteerde regel verwijderen" in r.text
    assert f'value="event:{event_id}"' in r.text

    r = client.post(
        "/public/delete",
        data={"candidate": f"event:{event_id}", "date": "2026-12-01", "source_prompt": "verwijder op 1 december afwezigheid directie"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/?deleted=1"

    con = core.db()
    row = con.execute("SELECT visible_in_embed,status FROM events WHERE id=?", (event_id,)).fetchone()
    con.close()
    assert row["visible_in_embed"] == 0
    assert row["status"] == "deleted"

    # Delete one migrated/base-calendar line while preserving another line on the same date.
    r = client.post("/public/interpret", data={"prompt": "verwijder op 2 december directie afwezig"})
    assert r.status_code == 200, r.text
    assert "directie afwezig: SGE" in r.text
    m = re.search(r'name="candidate" value="(snapshot:[^"]+)"', r.text)
    assert m, r.text
    snapshot_candidate = m.group(1)

    r = client.post(
        "/public/delete",
        data={"candidate": snapshot_candidate, "date": "2026-12-02", "source_prompt": "verwijder op 2 december directie afwezig"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    snap = json.loads(Path(tmpsnap).read_text(encoding="utf-8"))
    html = snap["entries"][0]["html"]
    assert "directie afwezig" not in html
    assert "andere afspraak blijft staan" in html

    r = client.get("/?deleted=1")
    assert r.status_code == 200
    assert "Kalenderitem verwijderd" in r.text

print("TCH_DELETE_FLOW_SMOKE_TEST=PASS")
for path in (tmpdb, tmpsnap):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
