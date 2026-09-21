import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature

import app.main as core
from app.production import app


RESET_ADMIN_PASSWORD = os.getenv("ADMIN_RESET_PASSWORD", "")
ENABLE_ADMIN_RECOVERY_LOG = os.getenv("ENABLE_ADMIN_RECOVERY_LOG", "false").lower() == "true"


def _session_payload(request: Request):
    raw = request.cookies.get("tch_session")
    if not raw:
        return None
    try:
        return core.signer.loads(raw)
    except BadSignature:
        return None


@app.on_event("startup")
def recovery_startup_and_selftest():
    # Controlled one-time password recovery hook. The secret itself never enters GitHub.
    if RESET_ADMIN_PASSWORD:
        con = core.db()
        row = con.execute("SELECT id FROM users WHERE email=?", (core.ADMIN_EMAIL,)).fetchone()
        if row:
            con.execute(
                "UPDATE users SET password_hash=?, active=1, role='director' WHERE email=?",
                (core.hash_password(RESET_ADMIN_PASSWORD), core.ADMIN_EMAIL),
            )
        else:
            con.execute(
                "INSERT INTO users(email,full_name,password_hash,role,active,created_at) VALUES(?,?,?,?,1,?)",
                (core.ADMIN_EMAIL, "Rob Huijghe", core.hash_password(RESET_ADMIN_PASSWORD), "director", core.now_iso()),
            )
        con.commit()
        check = con.execute("SELECT password_hash,active,role FROM users WHERE email=?", (core.ADMIN_EMAIL,)).fetchone()
        con.close()
        password_ok = bool(
            check and check["active"] and check["role"] == "director"
            and core.verify_password(RESET_ADMIN_PASSWORD, check["password_hash"])
        )
        print(f"TCH_AUTH_SELFTEST admin={core.ADMIN_EMAIL} password_match={str(password_ok).lower()}", flush=True)
        if not password_ok:
            raise RuntimeError("Admin login self-test failed")

    # Owner-only emergency recovery. The plaintext token is printed once to private Railway logs,
    # stored only as a hash, expires quickly and is deleted as soon as it is used.
    if ENABLE_ADMIN_RECOVERY_LOG:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        core.set_setting("admin_recovery_token_hash", digest)
        core.set_setting("admin_recovery_expires_at", expires)
        base = core.PUBLIC_BASE_URL or "https://telescoop-calendar-hub-production.up.railway.app"
        print(f"TCH_ADMIN_RECOVERY_URL={base}/recover?token={token}", flush=True)


@app.get("/recover")
def recover_admin(token: str):
    expected = core.setting("admin_recovery_token_hash")
    expires_raw = core.setting("admin_recovery_expires_at")
    if not expected or not expires_raw:
        raise HTTPException(403, "Herstellink is niet actief")
    try:
        expires = datetime.fromisoformat(expires_raw)
    except ValueError:
        raise HTTPException(403, "Herstellink is ongeldig")
    if datetime.now(timezone.utc) >= expires:
        core.set_setting("admin_recovery_token_hash", "")
        core.set_setting("admin_recovery_expires_at", "")
        raise HTTPException(403, "Herstellink is verlopen")
    actual = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise HTTPException(403, "Herstellink is ongeldig")

    con = core.db()
    row = con.execute("SELECT id FROM users WHERE email=? AND active=1", (core.ADMIN_EMAIL,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(500, "Beheerdersaccount ontbreekt")

    # One use only.
    core.set_setting("admin_recovery_token_hash", "")
    core.set_setting("admin_recovery_expires_at", "")
    core.audit(core.ADMIN_EMAIL, "account.recovery_link_used")
    response = RedirectResponse("/account/recovery", 303)
    response.set_cookie(
        "tch_session",
        core.signer.dumps({"uid": row["id"], "recovery": True}),
        httponly=True,
        secure=core.COOKIE_SECURE,
        samesite="lax",
        max_age=20 * 60,
    )
    return response


@app.get("/account/recovery", response_class=HTMLResponse)
def recovery_password_page(request: Request):
    user = core.require_user(request)
    payload = _session_payload(request)
    if not payload or not payload.get("recovery"):
        raise HTTPException(403, "Geen actieve herstelprocedure")
    body = '''<div class="card" style="max-width:560px;margin:auto">
      <h2>Nieuw wachtwoord instellen</h2>
      <p class="muted">De herstellink is al verbruikt. Kies nu een nieuw, uniek wachtwoord van minimaal 12 tekens.</p>
      <form method="post" action="/account/recovery">
        <label>Nieuw wachtwoord</label><input type="password" name="new_password" minlength="12" required>
        <label>Herhaal nieuw wachtwoord</label><input type="password" name="confirm_password" minlength="12" required>
        <p><button>Nieuw wachtwoord opslaan</button></p>
      </form>
    </div>'''
    return HTMLResponse(core.page("Account herstellen", body, user))


@app.post("/account/recovery")
def recovery_password_save(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = core.require_user(request)
    payload = _session_payload(request)
    if not payload or not payload.get("recovery"):
        raise HTTPException(403, "Geen actieve herstelprocedure")
    if len(new_password) < 12:
        raise HTTPException(400, "Nieuw wachtwoord moet minimaal 12 tekens bevatten")
    if new_password != confirm_password:
        raise HTTPException(400, "Nieuwe wachtwoorden komen niet overeen")
    con = core.db()
    con.execute("UPDATE users SET password_hash=? WHERE id=?", (core.hash_password(new_password), user["id"]))
    con.commit()
    con.close()
    core.audit(user["email"], "account.password_recovered")
    response = RedirectResponse("/", 303)
    response.set_cookie(
        "tch_session",
        core.signer.dumps({"uid": user["id"]}),
        httponly=True,
        secure=core.COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@app.middleware("http")
async def redirect_unauthenticated_browser(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path

    if response.status_code == 401 and path == "/login" and request.method == "POST":
        return RedirectResponse(url="/login", status_code=303)

    public_or_api = (
        (path == "/login" and request.method == "GET")
        or path == "/recover"
        or path == "/health"
        or path == "/connector-openapi.json"
        or path.startswith("/api/")
        or path.startswith("/oauth/")
        or path.startswith("/embed")
    )
    if response.status_code == 401 and not public_or_api:
        return RedirectResponse(url="/login", status_code=303)
    return response
