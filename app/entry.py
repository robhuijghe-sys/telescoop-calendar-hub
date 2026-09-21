import os

from fastapi import Request
from fastapi.responses import RedirectResponse

import app.main as core
from app.production import app


RESET_ADMIN_PASSWORD = os.getenv("ADMIN_RESET_PASSWORD", "")


@app.on_event("startup")
def one_time_admin_reset_and_selftest():
    """One-time recovery hook. The Railway variable is cleared after a verified boot."""
    if not RESET_ADMIN_PASSWORD:
        return
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
    password_ok = bool(check and check["active"] and check["role"] == "director" and core.verify_password(RESET_ADMIN_PASSWORD, check["password_hash"]))
    print(f"TCH_AUTH_SELFTEST admin={core.ADMIN_EMAIL} password_match={str(password_ok).lower()}", flush=True)
    if not password_ok:
        raise RuntimeError("Admin login self-test failed")


@app.middleware("http")
async def redirect_unauthenticated_browser(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path

    # A failed browser login should return to the form, never expose FastAPI JSON.
    if response.status_code == 401 and path == "/login" and request.method == "POST":
        return RedirectResponse(url="/login", status_code=303)

    public_or_api = (
        (path == "/login" and request.method == "GET")
        or path == "/health"
        or path == "/connector-openapi.json"
        or path.startswith("/api/")
        or path.startswith("/oauth/")
        or path.startswith("/embed")
    )
    if response.status_code == 401 and not public_or_api:
        return RedirectResponse(url="/login", status_code=303)
    return response
