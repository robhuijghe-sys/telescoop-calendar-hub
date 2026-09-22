import hashlib
import hmac
import html
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as core
from app.calendar_dynamic import app


_previous_page = core.page


def live_calendar_page(title: str, body: str, user=None):
    if user and user.get("role") == "director":
        body = (
            '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">'
            '<a class="btn alt" href="/password-resets">Wachtwoordresets</a>'
            '</div>' + body
        )
    rendered = _previous_page(title, body, user)
    rendered = rendered.replace(
        "Smartschool testmodus actief: publiceren schrijft nog niet naar Smartschool.",
        "Dynamische kalender actief: opgeslagen kalenderitems verschijnen automatisch in de Smartschoolweergave.",
    )
    return rendered


core.page = live_calendar_page


def _remove_route(path: str, method: str):
    keep = []
    for route in app.router.routes:
        if getattr(route, "path", None) != path:
            keep.append(route)
            continue
        methods = getattr(route, "methods", set()) or set()
        if method.upper() not in methods:
            keep.append(route)
    app.router.routes[:] = keep


# Replace only the GET login page. The existing, tested POST /login authentication stays intact.
_remove_route("/login", "GET")


@app.on_event("startup")
def password_reset_schema():
    con = core.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS password_reset_requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL UNIQUE,
          requested_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','link_created','completed'))
        );
        CREATE TABLE IF NOT EXISTS password_reset_tokens(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          token_hash TEXT UNIQUE NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        """
    )
    con.commit()
    con.close()


def _director(request: Request):
    user = core.require_user(request)
    if user["role"] != "director":
        raise HTTPException(403, "Alleen directie")
    return user


def _reset_token_row(token: str):
    if not token:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    con = core.db()
    row = con.execute(
        """SELECT t.*, u.email, u.active
           FROM password_reset_tokens t
           JOIN users u ON u.id=t.user_id
           WHERE t.token_hash=?""",
        (digest,),
    ).fetchone()
    con.close()
    if not row or row["used_at"] or not row["active"]:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        return None
    if datetime.now(timezone.utc) >= expires:
        return None
    return dict(row)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, reset: str = "", requested: str = ""):
    if core.current_user(request):
        return RedirectResponse("/", 303)
    notice = ""
    if reset == "1":
        notice = '<div class="card" style="max-width:460px;margin:0 auto 14px"><p style="margin:0">Je wachtwoord is gewijzigd. Je kunt nu aanmelden.</p></div>'
    elif requested == "1":
        notice = '<div class="card" style="max-width:460px;margin:0 auto 14px"><p style="margin:0">Je herstelverzoek is geregistreerd. De directie kan nu een eenmalige resetlink voor je aanmaken.</p></div>'
    body = f'''{notice}<div class="card" style="max-width:460px;margin:auto">
      <h2>Aanmelden</h2>
      <form method="post" action="/login">
        <label>E-mail</label><input name="email" type="email" autocomplete="username" required>
        <label>Wachtwoord</label><input name="password" type="password" autocomplete="current-password" required>
        <p><button>Aanmelden</button></p>
      </form>
      <p style="margin:14px 0 0"><a href="/forgot-password">Wachtwoord vergeten?</a></p>
    </div>'''
    return HTMLResponse(core.page("Aanmelden", body))


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page():
    body = '''<div class="card" style="max-width:520px;margin:auto">
      <h2>Wachtwoord vergeten?</h2>
      <p class="muted">Vul je e-mailadres in. Om accounts te beschermen tonen we niet of het adres in het systeem bestaat.</p>
      <form method="post" action="/forgot-password">
        <label>E-mail</label><input name="email" type="email" autocomplete="email" required>
        <p><button>Herstelverzoek indienen</button> <a class="btn alt" href="/login">Terug</a></p>
      </form>
    </div>'''
    return HTMLResponse(core.page("Wachtwoord vergeten", body))


@app.post("/forgot-password")
def forgot_password_request(email: str = Form(...)):
    email_normalized = email.strip().lower()
    con = core.db()
    user = con.execute(
        "SELECT id,email FROM users WHERE email=? AND active=1",
        (email_normalized,),
    ).fetchone()
    if user:
        con.execute(
            """INSERT INTO password_reset_requests(user_id,requested_at,status)
               VALUES(?,?, 'pending')
               ON CONFLICT(user_id) DO UPDATE SET requested_at=excluded.requested_at,status='pending'""",
            (user["id"], core.now_iso()),
        )
        con.commit()
    con.close()
    if user:
        core.audit(user["email"], "password_reset.requested")
    # Generic response prevents account enumeration.
    return RedirectResponse("/login?requested=1", 303)


@app.get("/password-resets", response_class=HTMLResponse)
def password_resets_page(request: Request):
    actor = _director(request)
    con = core.db()
    pending = con.execute(
        """SELECT r.id,r.requested_at,r.status,u.id AS user_id,u.email,u.full_name
           FROM password_reset_requests r JOIN users u ON u.id=r.user_id
           WHERE u.active=1 AND r.status IN ('pending','link_created')
           ORDER BY r.requested_at DESC"""
    ).fetchall()
    users = con.execute(
        "SELECT id,email,full_name,role FROM users WHERE active=1 ORDER BY full_name,email"
    ).fetchall()
    con.close()

    pending_rows = "".join(
        f'''<tr><td>{html.escape(r['full_name'] or '')}</td><td>{html.escape(r['email'])}</td>
        <td>{html.escape(r['requested_at'][:16].replace('T',' '))}</td><td>{html.escape(r['status'])}</td>
        <td><form method="post" action="/password-resets/{r['user_id']}/generate"><button>Maak resetlink</button></form></td></tr>'''
        for r in pending
    ) or '<tr><td colspan="5">Geen openstaande herstelverzoeken.</td></tr>'

    user_rows = "".join(
        f'''<tr><td>{html.escape(r['full_name'] or '')}</td><td>{html.escape(r['email'])}</td><td>{html.escape(r['role'])}</td>
        <td><form method="post" action="/password-resets/{r['id']}/generate"><button>Maak resetlink</button></form></td></tr>'''
        for r in users
    )
    body = f'''
    <div class="card"><h2>Openstaande herstelverzoeken</h2>
      <p class="muted">Resetlinks zijn 24 uur geldig en kunnen maar één keer gebruikt worden.</p>
      <table><tr><th>Naam</th><th>E-mail</th><th>Aangevraagd</th><th>Status</th><th></th></tr>{pending_rows}</table>
    </div>
    <div class="card"><h2>Handmatig resetlink maken</h2>
      <table><tr><th>Naam</th><th>E-mail</th><th>Rol</th><th></th></tr>{user_rows}</table>
    </div>'''
    return HTMLResponse(core.page("Wachtwoordresets", body, actor))


@app.post("/password-resets/{user_id}/generate", response_class=HTMLResponse)
def generate_password_reset_link(user_id: int, request: Request):
    actor = _director(request)
    con = core.db()
    user = con.execute("SELECT id,email,full_name,active FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not user["active"]:
        con.close()
        raise HTTPException(404, "Actieve gebruiker niet gevonden")

    # Invalidate any still-unused reset links for this user.
    con.execute(
        "UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
        (core.now_iso(), user_id),
    )
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    con.execute(
        """INSERT INTO password_reset_tokens(user_id,token_hash,expires_at,created_by,created_at)
           VALUES(?,?,?,?,?)""",
        (user_id, digest, expires, actor["id"], core.now_iso()),
    )
    con.execute(
        """INSERT INTO password_reset_requests(user_id,requested_at,status)
           VALUES(?,?, 'link_created')
           ON CONFLICT(user_id) DO UPDATE SET status='link_created'""",
        (user_id, core.now_iso()),
    )
    con.commit()
    con.close()

    core.audit(actor["email"], "password_reset.link_created", payload={"user": user["email"]})
    base = core.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    url = f"{base}/reset-password?token={raw}"
    body = f'''<div class="card" style="max-width:760px;margin:auto">
      <h2>Eenmalige resetlink</h2>
      <p>Voor: <strong>{html.escape(user['full_name'] or user['email'])}</strong></p>
      <p class="muted">De link is 24 uur geldig en vervalt onmiddellijk na gebruik. Deel hem alleen met deze gebruiker.</p>
      <textarea readonly style="min-height:100px">{html.escape(url)}</textarea>
      <p><a class="btn" href="{html.escape(url)}">Resetlink testen/openen</a> <a class="btn alt" href="/password-resets">Terug</a></p>
    </div>'''
    return HTMLResponse(core.page("Resetlink", body, actor))


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(token: str = ""):
    row = _reset_token_row(token)
    if not row:
        body = '''<div class="card" style="max-width:560px;margin:auto"><h2>Resetlink niet geldig</h2>
        <p>Deze link is ongeldig, verlopen of al gebruikt.</p><p><a class="btn" href="/forgot-password">Nieuw herstelverzoek</a></p></div>'''
        return HTMLResponse(core.page("Resetlink niet geldig", body), status_code=403)
    body = f'''<div class="card" style="max-width:560px;margin:auto">
      <h2>Nieuw wachtwoord instellen</h2>
      <p class="muted">Voor {html.escape(row['email'])}. Kies minimaal 12 tekens.</p>
      <form method="post" action="/reset-password">
        <input type="hidden" name="token" value="{html.escape(token)}">
        <label>Nieuw wachtwoord</label><input name="new_password" type="password" minlength="12" autocomplete="new-password" required>
        <label>Herhaal nieuw wachtwoord</label><input name="confirm_password" type="password" minlength="12" autocomplete="new-password" required>
        <p><button>Nieuw wachtwoord opslaan</button></p>
      </form>
    </div>'''
    return HTMLResponse(core.page("Nieuw wachtwoord", body))


@app.post("/reset-password")
def reset_password_save(
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    row = _reset_token_row(token)
    if not row:
        raise HTTPException(403, "Resetlink is ongeldig, verlopen of al gebruikt")
    if len(new_password) < 12:
        raise HTTPException(400, "Wachtwoord moet minimaal 12 tekens bevatten")
    if new_password != confirm_password:
        raise HTTPException(400, "Wachtwoorden komen niet overeen")

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    con = core.db()
    # Consume token and change password in the same transaction.
    current = con.execute(
        "SELECT id,user_id,used_at FROM password_reset_tokens WHERE token_hash=?",
        (digest,),
    ).fetchone()
    if not current or current["used_at"]:
        con.close()
        raise HTTPException(403, "Resetlink is niet meer geldig")
    now = core.now_iso()
    con.execute("UPDATE users SET password_hash=? WHERE id=?", (core.hash_password(new_password), row["user_id"]))
    con.execute("UPDATE password_reset_tokens SET used_at=? WHERE id=?", (now, current["id"]))
    con.execute("UPDATE password_reset_requests SET status='completed' WHERE user_id=?", (row["user_id"],))
    con.commit()
    con.close()
    core.audit(row["email"], "password_reset.completed")
    return RedirectResponse("/login?reset=1", 303)
