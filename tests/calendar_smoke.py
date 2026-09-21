import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

tmpdb = os.path.join(tempfile.gettempdir(), "tch-calendar-smoke.db")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass

os.environ["DB_PATH"] = tmpdb
os.environ["APP_SECRET"] = "calendar-smoke-secret"
os.environ["PUBLIC_BASE_URL"] = "https://calendar.example.test"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "smoke@example.org"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "SmokeTest-Initial-Password-123!"
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_RESET_PASSWORD"] = ""
os.environ["ENABLE_ADMIN_RECOVERY_LOG"] = "false"

from fastapi.testclient import TestClient
from app.calendar_dynamic import app
import app.main as core


def check(condition, message):
    if not condition:
        raise AssertionError(message)


with TestClient(app) as client:
    # Login still works through the extension layer.
    r = client.post(
        "/login",
        data={"email": "smoke@example.org", "password": "SmokeTest-Initial-Password-123!"},
        follow_redirects=False,
    )
    check(r.status_code == 303, "login must work")

    # Untimed parent item: must be accepted and auto-classified green.
    r = client.post(
        "/events/create",
        data={
            "title": "Oudercontact L1",
            "date": "2026-10-12",
            "start_time": "",
            "end_time": "",
            "all_day": "1",
            "category": "auto",
            "location": "",
            "description": "",
            "source_prompt": "Voeg oudercontact L1 toe op 12 oktober",
        },
        follow_redirects=False,
    )
    check(r.status_code == 303, "untimed parent item must save")

    # Personnel item: auto-classified pink.
    r = client.post(
        "/events/create",
        data={
            "title": "Zorgoverleg GR3",
            "date": "2026-10-13",
            "start_time": "08:45",
            "end_time": "09:35",
            "category": "auto",
            "description": "",
            "location": "",
            "source_prompt": "zorgoverleg GR3",
        },
        follow_redirects=False,
    )
    check(r.status_code == 303, "personnel item must save")

    # Warning/absence: auto-classified red.
    r = client.post(
        "/events/create",
        data={
            "title": "ZoCo afwezig",
            "date": "2026-10-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "category": "auto",
            "description": "",
            "location": "",
            "source_prompt": "ZoCo afwezig",
        },
        follow_redirects=False,
    )
    check(r.status_code == 303, "warning item must save")

    r = client.get("/calendar-preview")
    check(r.status_code == 200, "preview must render")
    text = r.text
    check("#99CA3B" in text and "Oudercontact L1" in text, "parent item must render green")
    check("#C614A1" in text and "Zorgoverleg GR3" in text, "personnel item must render pink")
    check("#D32F2F" in text and "ZoCo afwezig" in text, "warning item must render red")
    check("@media (max-width:560px)" in text, "mobile breakpoint must exist")
    check("mobile-calendar" in text and "desktop-calendar" in text, "desktop and mobile renderers must exist")
    check("Schoolorganisatie" in text and "Poetsrooster" in text, "current top links must be preserved")

    token = core.setting("embed_token")
    r = client.get(f"/embed?token={token}")
    check(r.status_code == 200, "tokenized Smartschool embed must render")
    check("no-store" in r.headers.get("cache-control", ""), "embed must not be cached")

    r = client.get("/embed?token=wrong")
    check(r.status_code == 403, "invalid embed token must fail")

    r = client.get("/calendar-settings")
    check(r.status_code == 200 and "iframe" in r.text.lower(), "settings must expose one-time embed code")

print("TCH_CALENDAR_SMOKE_TEST=PASS")
try:
    os.remove(tmpdb)
except FileNotFoundError:
    pass
