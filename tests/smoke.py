import hashlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# Ensure repository root is importable when this file is executed directly.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Isolated build-time test environment: never touches the Railway volume.
tmpdb = os.path.join(tempfile.gettempdir(), "tch-smoke.db")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass

os.environ["DB_PATH"] = tmpdb
os.environ["APP_SECRET"] = "smoke-test-secret-not-for-production"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "smoke@example.org"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "SmokeTest-Initial-Password-123!"
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_RESET_PASSWORD"] = ""
os.environ["ENABLE_ADMIN_RECOVERY_LOG"] = "false"

from fastapi.testclient import TestClient
from app.entry import app, RECOVERY_LINK_HOURS
import app.main as core


def check(condition, message):
    if not condition:
        raise AssertionError(message)


check(RECOVERY_LINK_HOURS == 24, "production recovery link validity must remain 24 hours")

with TestClient(app) as client:
    r = client.get("/", follow_redirects=False)
    check(r.status_code == 303 and r.headers.get("location") == "/login", "anonymous root must redirect to login")

    r = client.get("/login")
    check(r.status_code == 200 and "Aanmelden" in r.text, "login page must render")

    r = client.post(
        "/login",
        data={"email": "smoke@example.org", "password": "wrong-password"},
        follow_redirects=False,
    )
    check(r.status_code == 303 and r.headers.get("location") == "/login", "invalid login must return to form")

    r = client.post(
        "/login",
        data={"email": "smoke@example.org", "password": "SmokeTest-Initial-Password-123!"},
        follow_redirects=False,
    )
    check(r.status_code == 303 and r.headers.get("location") == "/", "valid login must redirect to dashboard")

    r = client.get("/")
    check(r.status_code == 200 and "Telescoop Calendar Hub" in r.text, "authenticated dashboard must render")

    r = client.get("/health")
    check(r.status_code == 200 and r.json().get("ok") is True, "healthcheck must be green")

    # Inactive recovery links must produce a normal HTML page, never FastAPI JSON.
    client.cookies.clear()
    r = client.get("/recover?token=inactive-token", follow_redirects=False)
    check(r.status_code == 403, "inactive recovery link must be rejected")
    check("Herstellink niet actief" in r.text and '"detail"' not in r.text, "inactive recovery link must render friendly HTML")

    # Expired recovery links must also render friendly HTML and clear themselves.
    expired_token = "build-time-expired-recovery-token"
    core.set_setting("admin_recovery_token_hash", hashlib.sha256(expired_token.encode()).hexdigest())
    core.set_setting(
        "admin_recovery_expires_at",
        (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    r = client.get(f"/recover?token={expired_token}", follow_redirects=False)
    check(r.status_code == 403, "expired recovery link must be rejected")
    check("Herstellink verlopen" in r.text and '"detail"' not in r.text, "expired recovery link must render friendly HTML")
    check(core.setting("admin_recovery_token_hash") == "", "expired recovery token must be cleared")

    # Exercise the complete one-time recovery flow.
    recovery_token = "build-time-smoke-recovery-token"
    core.set_setting("admin_recovery_token_hash", hashlib.sha256(recovery_token.encode()).hexdigest())
    core.set_setting(
        "admin_recovery_expires_at",
        (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    )
    client.cookies.clear()

    r = client.get(f"/recover?token={recovery_token}", follow_redirects=False)
    check(r.status_code == 303 and r.headers.get("location") == "/account/recovery", "recovery link must create recovery session")

    r = client.get("/account/recovery")
    check(r.status_code == 200 and "Nieuw wachtwoord instellen" in r.text, "recovery password page must render")

    new_password = "SmokeTest-New-Password-456!"
    r = client.post(
        "/account/recovery",
        data={"new_password": new_password, "confirm_password": new_password},
        follow_redirects=False,
    )
    check(r.status_code == 303 and r.headers.get("location") == "/", "password recovery must return to dashboard")

    # Token must be single-use and reuse must stay friendly HTML.
    client.cookies.clear()
    r = client.get(f"/recover?token={recovery_token}", follow_redirects=False)
    check(r.status_code == 403, "recovery token must be single-use")
    check("Herstellink niet actief" in r.text and '"detail"' not in r.text, "used recovery link must render friendly HTML")

    r = client.post(
        "/login",
        data={"email": "smoke@example.org", "password": new_password},
        follow_redirects=False,
    )
    check(r.status_code == 303 and r.headers.get("location") == "/", "new password must work after recovery")

print("TCH_SMOKE_TEST=PASS")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass
