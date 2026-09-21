import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

tmpdb = os.path.join(tempfile.gettempdir(), "tch-live-ui-smoke.db")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass

os.environ["DB_PATH"] = tmpdb
os.environ["APP_SECRET"] = "live-ui-smoke-secret"
os.environ["PUBLIC_BASE_URL"] = "https://calendar.example.test"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "smoke@example.org"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "SmokeTest-Initial-Password-123!"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SMARTSCHOOL_DRY_RUN"] = "true"
os.environ["ADMIN_RESET_PASSWORD"] = ""
os.environ["ENABLE_ADMIN_RECOVERY_LOG"] = "false"

from fastapi.testclient import TestClient
from app.calendar_live import app


with TestClient(app) as client:
    r = client.post(
        "/login",
        data={"email": "smoke@example.org", "password": "SmokeTest-Initial-Password-123!"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.get("/")
    assert r.status_code == 200
    assert "Dynamische kalender actief" in r.text
    assert "Smartschool testmodus actief" not in r.text
    assert "Smartschool kalender" in r.text

print("TCH_LIVE_UI_SMOKE_TEST=PASS")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass
