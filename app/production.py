from __future__ import annotations

import base64
import hashlib
import html
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as core

app = core.app
_original_page = core.page


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(core.APP_SECRET.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return "enc:" + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("enc:"):
        return value
    try:
        return _fernet().decrypt(value[4:].encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise HTTPException(500, "Geheim kon niet worden ontsleuteld. Controleer APP_SECRET.")


def enhanced_page(title: str, body: str, user=None):
    if user:
        links = ['<a class="btn alt" href="/account">Mijn account</a>']
        if user.get("role") == "director":
            links += [
                '<a class="btn alt" href="/users">Gebruikers</a>',
                '<a class="btn alt" href="/smartschool">Smartschool OAuth</a>',
            ]
        body = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">' + " ".join(links) + "</div>" + body
    return _original_page(title, body, user)


# Existing routes in app.main resolve `page` at request time, so this enhances all pages.
core.page = enhanced_page


@app.on_event("startup")
def production_extension_startup():
    con = core.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS oauth_states(
          state TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL,
          expires_at TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS smartschool_tokens(
          id INTEGER PRIMARY KEY CHECK(id = 1),
          access_token TEXT NOT NULL,
          refresh_token TEXT NOT NULL DEFAULT '',
          token_type TEXT NOT NULL DEFAULT 'Bearer',
          scope TEXT NOT NULL DEFAULT '',
          expires_at TEXT,
          connected_by INTEGER,
          connected_at TEXT NOT NULL
        );
        """
    )
    con.commit()
    con.close()


def director(request: Request):
    user = core.require_user(request)
    if user["role"] != "director":
        raise HTTPException(403, "Alleen directie")
    return user


def callback_url() -> str:
    if not core.PUBLIC_BASE_URL:
        raise HTTPException(500, "PUBLIC_BASE_URL is niet ingesteld")
    return core.PUBLIC_BASE_URL + "/oauth/smartschool/callback"


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request):
    user = core.require_user(request)
    body = f'''
    <div class="card">
      <h2>Mijn account</h2>
      <p><strong>{html.escape(user['full_name'] or user['email'])}</strong><br>
      <span class="muted">{html.escape(user['email'])} · {html.escape(user['role'])}</span></p>
    </div>
    <div class="card">
      <h2>Wachtwoord wijzigen</h2>
      <form method="post" action="/account/password">
        <label>Huidig wachtwoord</label><input type="password" name="current_password" required>
        <label>Nieuw wachtwoord</label><input type="password" name="new_password" minlength="12" required>
        <label>Herhaal nieuw wachtwoord</label><input type="password" name="confirm_password" minlength="12" required>
        <p class="muted">Gebruik minimaal 12 tekens en bij voorkeur een uniek wachtwoord.</p>
        <p><button>Wachtwoord wijzigen</button></p>
      </form>
    </div>'''
    return HTMLResponse(core.page("Mijn account", body, user))


@app.post("/account/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = core.require_user(request)
    if len(new_password) < 12:
        raise HTTPException(400, "Nieuw wachtwoord moet minimaal 12 tekens bevatten")
    if new_password != confirm_password:
        raise HTTPException(400, "Nieuwe wachtwoorden komen niet overeen")
    con = core.db()
    row = con.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
    if not row or not core.verify_password(current_password, row["password_hash"]):
        con.close()
        raise HTTPException(400, "Huidig wachtwoord is niet correct")
    con.execute("UPDATE users SET password_hash=? WHERE id=?", (core.hash_password(new_password), user["id"]))
    con.commit()
    con.close()
    core.audit(user["email"], "account.password_changed")
    return RedirectResponse("/account", 303)


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    user = director(request)
    con = core.db()
    rows = con.execute("SELECT id,email,full_name,role,active,created_at FROM users ORDER BY full_name,email").fetchall()
    con.close()
    trs = []
    for row in rows:
        status = "Actief" if row["active"] else "Geblokkeerd"
        toggle = "Blokkeren" if row["active"] else "Activeren"
        disabled = " disabled" if row["id"] == user["id"] else ""
        trs.append(
            f'''<tr><td>{html.escape(row['full_name'] or '')}</td><td>{html.escape(row['email'])}</td>
            <td>{html.escape(row['role'])}</td><td>{status}</td><td>
            <form method="post" action="/users/{row['id']}/toggle"><button{disabled}>{toggle}</button></form></td></tr>'''
        )
    body = f'''
    <div class="card"><h2>Gebruikers</h2>
      <table><tr><th>Naam</th><th>E-mail</th><th>Rol</th><th>Status</th><th></th></tr>{''.join(trs)}</table>
    </div>
    <div class="card"><h2>Gebruiker toevoegen</h2>
      <form method="post" action="/users/create">
        <label>Naam</label><input name="full_name" required>
        <label>E-mail</label><input name="email" type="email" required>
        <label>Rol</label><select name="role"><option value="secretary">Secretariaat</option><option value="care">Zorg</option><option value="director">Directie</option></select>
        <label>Tijdelijk wachtwoord</label><input name="password" type="password" minlength="12" required>
        <p><button>Gebruiker toevoegen</button></p>
      </form>
    </div>'''
    return HTMLResponse(core.page("Gebruikers", body, user))


@app.post("/users/create")
def create_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
):
    actor = director(request)
    if role not in ("director", "secretary", "care"):
        raise HTTPException(400, "Ongeldige rol")
    if len(password) < 12:
        raise HTTPException(400, "Tijdelijk wachtwoord moet minimaal 12 tekens bevatten")
    con = core.db()
    try:
        con.execute(
            "INSERT INTO users(email,full_name,password_hash,role,active,created_at) VALUES(?,?,?,?,1,?)",
            (email.strip().lower(), full_name.strip(), core.hash_password(password), role, core.now_iso()),
        )
        con.commit()
    except Exception as exc:
        con.close()
        raise HTTPException(400, f"Gebruiker kon niet worden aangemaakt: {exc}")
    con.close()
    core.audit(actor["email"], "user.created", payload={"email": email.strip().lower(), "role": role})
    return RedirectResponse("/users", 303)


@app.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, request: Request):
    actor = director(request)
    if user_id == actor["id"]:
        raise HTTPException(400, "Je kunt je eigen account niet blokkeren")
    con = core.db()
    row = con.execute("SELECT email,active FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Gebruiker niet gevonden")
    new_active = 0 if row["active"] else 1
    con.execute("UPDATE users SET active=? WHERE id=?", (new_active, user_id))
    con.commit()
    con.close()
    core.audit(actor["email"], "user.active_changed", payload={"email": row["email"], "active": bool(new_active)})
    return RedirectResponse("/users", 303)


def token_status():
    con = core.db()
    row = con.execute("SELECT * FROM smartschool_tokens WHERE id=1").fetchone()
    con.close()
    return dict(row) if row else None


@app.get("/smartschool", response_class=HTMLResponse)
def smartschool_page(request: Request):
    user = director(request)
    platform = core.setting("smartschool_platform", core.SS_PLATFORM).rstrip("/")
    contact = core.setting("smartschool_contact", core.SS_CONTACT)
    client_id = core.setting("smartschool_client_id")
    scopes = core.setting("smartschool_scopes", "userinfo")
    secret_present = bool(core.setting("smartschool_client_secret"))
    token = token_status()
    connected = bool(token)
    cb = callback_url()
    connect_button = '<a class="btn" href="/smartschool/connect">Verbinden met Smartschool</a>' if client_id and secret_present else '<span class="muted">Vul eerst client ID en client secret in.</span>'
    if connected:
        connect_button = '<span class="btn alt">Smartschool verbonden</span> <form style="display:inline" method="post" action="/smartschool/disconnect"><button>Lokale koppeling wissen</button></form>'
    request_text = f'''Naam school/organisatie: GO! BS De Telescoop\nVoornaam + naam: Rob Huijghe\nE-mail: {contact}\nSmartschoolplatform: {platform}\nRedirect URI: {cb}\nMeerdere platformen: nee\n\nDoel: een interne kalenderhub waarmee directie, secretariaat en zorg schoolactiviteiten beheren. We willen gemachtigde gebruikers via de officiële Smartschool OAuth/API-koppeling activiteiten laten toevoegen, wijzigen en verwijderen in Planner. Gelieve naast de OAuth-client de nodige Planner-scope(s) en technische specificatie voor list/create/update/delete te bezorgen. De toepassing wordt uitsluitend gebruikt voor ons eigen Smartschoolplatform.'''
    body = f'''
    <div class="card"><h2>Smartschool OAuth</h2>
      <p>Platform: <code>{html.escape(platform)}</code><br>Definitieve redirect URI: <code>{html.escape(cb)}</code></p>
      <p>{connect_button}</p>
      <form method="post" action="/smartschool/settings">
        <label>OAuth client ID</label><input name="client_id" value="{html.escape(client_id)}">
        <label>OAuth client secret</label><input name="client_secret" type="password" placeholder="{'opgeslagen — leeg laten om te behouden' if secret_present else 'nog niet ingevuld'}">
        <label>Scopes (spatiegescheiden)</label><input name="scopes" value="{html.escape(scopes)}">
        <div class="grid">
          <div><label>Planner list endpoint</label><input name="planner_list" value="{html.escape(core.setting('planner_list'))}"></div>
          <div><label>Planner create endpoint</label><input name="planner_create" value="{html.escape(core.setting('planner_create'))}"></div>
          <div><label>Planner update endpoint</label><input name="planner_update" value="{html.escape(core.setting('planner_update'))}"></div>
          <div><label>Planner delete endpoint</label><input name="planner_delete" value="{html.escape(core.setting('planner_delete'))}"></div>
        </div>
        <label><input style="width:auto" type="checkbox" name="dry_run" value="1" {'checked' if core.setting('smartschool_dry_run','1')=='1' else ''}> Smartschool testmodus</label>
        <p><button>OAuth/API-instellingen opslaan</button></p>
      </form>
    </div>
    <div class="card"><h2>Gegevens voor Smartschool-aanvraag</h2><textarea readonly style="min-height:260px">{html.escape(request_text)}</textarea></div>'''
    return HTMLResponse(core.page("Smartschool OAuth", body, user))


@app.post("/smartschool/settings")
def smartschool_settings(
    request: Request,
    client_id: str = Form(""),
    client_secret: str = Form(""),
    scopes: str = Form("userinfo"),
    planner_list: str = Form(""),
    planner_create: str = Form(""),
    planner_update: str = Form(""),
    planner_delete: str = Form(""),
    dry_run: str = Form("0"),
):
    user = director(request)
    core.set_setting("smartschool_client_id", client_id.strip())
    if client_secret:
        core.set_setting("smartschool_client_secret", encrypt_secret(client_secret.strip()))
    core.set_setting("smartschool_scopes", scopes.strip() or "userinfo")
    core.set_setting("planner_list", planner_list.strip())
    core.set_setting("planner_create", planner_create.strip())
    core.set_setting("planner_update", planner_update.strip())
    core.set_setting("planner_delete", planner_delete.strip())
    core.set_setting("smartschool_dry_run", "1" if dry_run == "1" else "0")
    core.audit(user["email"], "smartschool.settings_updated", payload={"client_id_set": bool(client_id), "secret_changed": bool(client_secret), "scopes": scopes})
    return RedirectResponse("/smartschool", 303)


@app.get("/smartschool/connect")
def smartschool_connect(request: Request):
    user = director(request)
    platform = core.setting("smartschool_platform", core.SS_PLATFORM).rstrip("/")
    client_id = core.setting("smartschool_client_id")
    client_secret = decrypt_secret(core.setting("smartschool_client_secret"))
    scopes = core.setting("smartschool_scopes", "userinfo")
    if not client_id or not client_secret:
        raise HTTPException(400, "Client ID en client secret zijn nog niet ingevuld")
    state = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    con = core.db()
    con.execute("DELETE FROM oauth_states WHERE expires_at < ?", (core.now_iso(),))
    con.execute("INSERT INTO oauth_states(state,user_id,expires_at,created_at) VALUES(?,?,?,?)", (state, user["id"], expires, core.now_iso()))
    con.commit()
    con.close()
    params = {
        "client_id": client_id,
        "redirect_uri": callback_url(),
        "response_type": "code",
        "scope": scopes,
        "state": state,
    }
    core.audit(user["email"], "smartschool.oauth_started", payload={"scopes": scopes})
    return RedirectResponse(platform + "/OAuth?" + urlencode(params), 302)


@app.get("/oauth/smartschool/callback")
async def smartschool_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"Smartschool OAuth-fout: {error}")
    if not code or not state:
        raise HTTPException(400, "Code of state ontbreekt")
    con = core.db()
    st = con.execute("SELECT * FROM oauth_states WHERE state=?", (state,)).fetchone()
    if not st or st["expires_at"] < core.now_iso():
        con.close()
        raise HTTPException(400, "Ongeldige of verlopen OAuth-state")
    con.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    con.commit()
    user = con.execute("SELECT id,email FROM users WHERE id=?", (st["user_id"],)).fetchone()
    con.close()
    platform = core.setting("smartschool_platform", core.SS_PLATFORM).rstrip("/")
    client_id = core.setting("smartschool_client_id")
    client_secret = decrypt_secret(core.setting("smartschool_client_secret"))
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": callback_url(),
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(platform + "/OAuth/index/token", data=data, headers={"Accept": "application/json"})
    if response.status_code >= 400:
        raise HTTPException(502, f"Smartschool token-uitwisseling mislukt ({response.status_code})")
    payload = response.json()
    access_token = payload.get("access_token", "")
    if not access_token:
        raise HTTPException(502, "Smartschool gaf geen access_token terug")
    refresh_token = payload.get("refresh_token", "")
    expires_in = int(payload.get("expires_in") or 3600)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    con = core.db()
    con.execute(
        "INSERT INTO smartschool_tokens(id,access_token,refresh_token,token_type,scope,expires_at,connected_by,connected_at) VALUES(1,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET access_token=excluded.access_token,refresh_token=excluded.refresh_token,token_type=excluded.token_type,scope=excluded.scope,expires_at=excluded.expires_at,connected_by=excluded.connected_by,connected_at=excluded.connected_at",
        (
            encrypt_secret(access_token),
            encrypt_secret(refresh_token),
            payload.get("token_type", "Bearer"),
            payload.get("scope", core.setting("smartschool_scopes", "userinfo")),
            expires_at,
            st["user_id"],
            core.now_iso(),
        ),
    )
    con.commit()
    con.close()
    core.audit(user["email"] if user else None, "smartschool.connected", payload={"scope": payload.get("scope")})
    return RedirectResponse("/smartschool", 303)


@app.post("/smartschool/disconnect")
def smartschool_disconnect(request: Request):
    user = director(request)
    con = core.db()
    con.execute("DELETE FROM smartschool_tokens WHERE id=1")
    con.commit()
    con.close()
    core.audit(user["email"], "smartschool.disconnected_local")
    return RedirectResponse("/smartschool", 303)
