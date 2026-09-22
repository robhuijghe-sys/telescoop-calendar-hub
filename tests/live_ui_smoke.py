import os
import re
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
    # Login page exposes password recovery.
    r = client.get("/login")
    assert r.status_code == 200
    assert "Wachtwoord vergeten?" in r.text

    # Recovery request is generic and does not disclose account existence.
    r = client.post(
        "/forgot-password",
        data={"email": "smoke@example.org"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login?requested=1"

    # Existing login still works.
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
    assert "Wachtwoordresets" in r.text

    # Director sees the pending request and can create a one-time reset link.
    r = client.get("/password-resets")
    assert r.status_code == 200
    assert "smoke@example.org" in r.text
    assert "pending" in r.text

    r = client.post("/password-resets/1/generate")
    assert r.status_code == 200
    match = re.search(r"/reset-password\?token=([A-Za-z0-9_-]+)", r.text)
    assert match, r.text
    token = match.group(1)

    # Log out and use the reset link as an unauthenticated user.
    client.get("/logout", follow_redirects=False)
    r = client.get(f"/reset-password?token={token}")
    assert r.status_code == 200
    assert "Nieuw wachtwoord instellen" in r.text

    new_password = "SmokeTest-New-Password-456!"
    r = client.post(
        "/reset-password",
        data={"token": token, "new_password": new_password, "confirm_password": new_password},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login?reset=1"

    # New password works.
    r = client.post(
        "/login",
        data={"email": "smoke@example.org", "password": new_password},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Token is truly one-use only.
    client.get("/logout", follow_redirects=False)
    r = client.get(f"/reset-password?token={token}")
    assert r.status_code == 403
    assert "ongeldig, verlopen of al gebruikt" in r.text

print("TCH_LIVE_UI_SMOKE_TEST=PASS")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass
