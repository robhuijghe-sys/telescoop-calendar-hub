import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

tmpdb = os.path.join(tempfile.gettempdir(), "tch-public-post-smoke.db")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass

os.environ["DB_PATH"] = tmpdb
os.environ["APP_SECRET"] = "public-post-smoke-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "smoke@example.org"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "SmokeTest-Initial-Password-123!"
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_RESET_PASSWORD"] = ""
os.environ["ENABLE_ADMIN_RECOVERY_LOG"] = "false"

from fastapi.testclient import TestClient
from app.public_calendar import app
import app.main as core

with TestClient(app) as client:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "Geen login nodig" in r.text
    assert "Kalenderitem toevoegen" in r.text

    r = client.get("/smartschool-calendar", follow_redirects=False)
    assert r.status_code == 200
    assert '<meta http-equiv="refresh" content="30">' in r.text
    assert "@media (max-width:560px)" in r.text
    assert r.headers.get("cache-control", "").startswith("no-store")

    r = client.post(
        "/public/interpret",
        data={"prompt": "Voeg op 12 oktober 2026 om 15.30 teamvergadering toe"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Controleer kalenderitem" in r.text
    assert 'value="personeel" selected' in r.text

    r = client.post(
        "/public/create",
        data={
            "title": "Teamvergadering",
            "date": "2026-10-12",
            "start_time": "15:30",
            "end_time": "16:30",
            "all_day": "0",
            "category": "auto",
            "location": "lerarenkamer",
            "description": "",
            "source_prompt": "Voeg op 12 oktober 2026 om 15.30 teamvergadering toe",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers.get("location") == "/?added=1"

    con = core.db()
    row = con.execute("SELECT * FROM events WHERE title='Teamvergadering'").fetchone()
    con.close()
    assert row is not None
    assert row["status"] == "published"
    assert row["visible_in_embed"] == 1
    assert row["category"] == "personeel"

    r = client.get("/smartschool-calendar", follow_redirects=False)
    assert r.status_code == 200
    assert "Teamvergadering" in r.text
    assert "#C614A1" in r.text

    r = client.get("/?added=1")
    assert r.status_code == 200
    assert "Kalenderitem toegevoegd" in r.text

print("TCH_PUBLIC_POST_SMOKE_TEST=PASS")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass
