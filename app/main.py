from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field

TZ = ZoneInfo("Europe/Brussels")
APP_SECRET = os.getenv("APP_SECRET", "change-me")
DB_PATH = os.getenv("DB_PATH", "/data/telescoop-calendar.db")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "rob.huijghe@detelescoop.be").lower()
ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
SS_PLATFORM = os.getenv("SMARTSCHOOL_PLATFORM_URL", "https://telescoop-sgr8.smartschool.be").rstrip("/")
SS_CONTACT = os.getenv("SMARTSCHOOL_CONTACT_EMAIL", "rob.huijghe@detelescoop.be")

app = FastAPI(title="Telescoop Calendar Hub", version="1.0.0")
signer = URLSafeSerializer(APP_SECRET, salt="tch-session")


def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 240_000)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except Exception:
        return False


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      full_name TEXT NOT NULL DEFAULT '',
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('director','secretary','care')),
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      start_at TEXT NOT NULL,
      end_at TEXT NOT NULL,
      all_day INTEGER NOT NULL DEFAULT 0,
      location TEXT NOT NULL DEFAULT '',
      audience TEXT NOT NULL DEFAULT '[]',
      category TEXT NOT NULL DEFAULT 'algemeen',
      status TEXT NOT NULL DEFAULT 'draft',
      source_prompt TEXT,
      smartschool_external_id TEXT,
      sync_error TEXT,
      visible_in_embed INTEGER NOT NULL DEFAULT 1,
      created_by INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      actor_email TEXT,
      action TEXT NOT NULL,
      event_id INTEGER,
      payload TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS api_keys(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      prefix TEXT NOT NULL,
      key_hash TEXT UNIQUE NOT NULL,
      revoked INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    """)
    defaults = {
      "smartschool_platform": SS_PLATFORM,
      "smartschool_contact": SS_CONTACT,
      "smartschool_dry_run": "1",
      "smartschool_client_id": "",
      "smartschool_client_secret": "",
      "smartschool_scopes": "userinfo",
      "planner_list": "", "planner_create": "", "planner_update": "", "planner_delete": "",
      "embed_token": secrets.token_urlsafe(24),
    }
    for k,v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k,v))
    if ADMIN_PASSWORD:
        row = con.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
        if not row:
            con.execute("INSERT INTO users(email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                        (ADMIN_EMAIL, "Rob Huijghe", hash_password(ADMIN_PASSWORD), "director", now_iso()))
    con.commit(); con.close()


@app.on_event("startup")
def startup():
    init_db()


def setting(key: str, default=""):
    con=db(); row=con.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone(); con.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    con=db(); con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value)); con.commit(); con.close()


def audit(email, action, event_id=None, payload=None):
    con=db(); con.execute("INSERT INTO audit_log(actor_email,action,event_id,payload,created_at) VALUES(?,?,?,?,?)",
                          (email, action, event_id, json.dumps(payload or {}, ensure_ascii=False), now_iso())); con.commit(); con.close()


def current_user(request: Request):
    raw=request.cookies.get("tch_session")
    if not raw: return None
    try: data=signer.loads(raw)
    except BadSignature: return None
    con=db(); row=con.execute("SELECT id,email,full_name,role,active FROM users WHERE id=?",(data.get("uid"),)).fetchone(); con.close()
    return dict(row) if row and row["active"] else None


def require_user(request: Request):
    u=current_user(request)
    if not u: raise HTTPException(401,"Aanmelden vereist")
    return u


def esc(v): return html.escape(str(v or ""))


def page(title: str, body: str, user=None):
    nav = ""
    if user:
        nav = f'''<nav><a href="/">Dashboard</a><a href="/events">Kalender</a><a href="/settings">Instellingen</a><a href="/audit">Audit</a><a href="/logout">Afmelden</a></nav>'''
    return f'''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Telescoop Calendar Hub</title><style>
    :root{{--bg:#f6f4ef;--card:#fff;--ink:#18263e;--muted:#687386;--accent:#e9a63a;--line:#d9dfe8}}*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--ink)}}header{{background:#203555;color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center}}header h1{{font-size:20px;margin:0}}nav{{display:flex;gap:14px;flex-wrap:wrap}}nav a{{color:#fff;text-decoration:none;font-size:14px}}main{{max-width:1050px;margin:28px auto;padding:0 18px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:18px;box-shadow:0 6px 22px rgba(30,45,70,.05)}}h2{{margin-top:0}}label{{display:block;font-size:13px;color:var(--muted);margin:10px 0 5px}}input,textarea,select{{width:100%;padding:10px 11px;border:1px solid var(--line);border-radius:9px;background:#fff}}textarea{{min-height:90px}}button,.btn{{display:inline-block;background:#203555;color:#fff;border:0;border-radius:9px;padding:10px 14px;text-decoration:none;cursor:pointer}}.btn.alt{{background:#edf1f7;color:#203555}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.muted{{color:var(--muted)}}.warn{{background:#fff5d9;border:1px solid #efd28a;padding:12px;border-radius:10px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}code{{background:#eef1f5;padding:2px 5px;border-radius:5px}}@media(max-width:700px){{header{{display:block}}nav{{margin-top:12px}}table{{font-size:13px}}}}
    </style></head><body><header><h1>Telescoop Calendar Hub</h1>{nav}</header><main>{body}</main></body></html>'''


MONTHS={"januari":1,"februari":2,"maart":3,"april":4,"mei":5,"juni":6,"juli":7,"augustus":8,"september":9,"oktober":10,"november":11,"december":12}

def parse_instruction(text: str):
    t=text.lower().strip(); now=datetime.now(TZ); missing=[]; assumptions=[]
    title=text.strip(); date_val=None; start=None; end=None; all_day=bool(re.search(r"\b(hele dag|ganse dag|volledige dag)\b",t))
    m=re.search(r"\b(\d{1,2})\s+(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)(?:\s+(\d{4}))?",t)
    if m:
        d=int(m.group(1)); mo=MONTHS[m.group(2)]; y=int(m.group(3) or now.year)
        if not m.group(3) and (mo,d)<(now.month,now.day): y+=1
        if not m.group(3): assumptions.append(f"Jaartal geïnterpreteerd als {y}")
        date_val=f"{y:04d}-{mo:02d}-{d:02d}"
    m2=re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",t)
    if not date_val and m2:
        d,mo=int(m2.group(1)),int(m2.group(2)); y=int(m2.group(3) or now.year)
        if y<100:y+=2000
        if not m2.group(3) and (mo,d)<(now.month,now.day): y+=1
        date_val=f"{y:04d}-{mo:02d}-{d:02d}"
    times=re.findall(r"\b(\d{1,2})(?:[:.]|u)(\d{2})?\b",t)
    if times:
        start=f"{int(times[0][0]):02d}:{int(times[0][1] or 0):02d}"
        if len(times)>1:end=f"{int(times[1][0]):02d}:{int(times[1][1] or 0):02d}"
    audiences=[]
    for prefix,a,b in re.findall(r"\b([lk])(\d)\s*(?:-|tot)\s*[lk]?(\d)\b",t):
        for n in range(int(a),int(b)+1): audiences.append(prefix.upper()+str(n))
    for prefix,n in re.findall(r"\b([lk])(\d)\b",t):
        x=prefix.upper()+n
        if x not in audiences: audiences.append(x)
    if "ouders" in t and "ouders" not in audiences: audiences.append("ouders")
    category="ouders" if "oudercontact" in t else "team" if "overleg" in t or "vergadering" in t else "uitstap" if "uitstap" in t or "zwem" in t else "algemeen"
    cleaned=re.sub(r"\b(voeg|toe|plan|zet|op|van|tot|om|in|de|het|een|kalender|agenda)\b"," ",text,flags=re.I)
    cleaned=re.sub(r"\d{1,2}(?:[:.]|u)\d{0,2}"," ",cleaned)
    cleaned=re.sub(r"\s+"," ",cleaned).strip(" ,.-")
    if cleaned:title=cleaned[0].upper()+cleaned[1:]
    if not date_val:missing.append("datum")
    if not all_day and not start:missing.append("starttijd")
    if not all_day and start and not end:missing.append("eindtijd")
    return {"title":title,"date":date_val,"start_time":start,"end_time":end,"all_day":all_day,"audience":audiences,"category":category,"missing":missing,"assumptions":assumptions}


def to_utc(date_s, time_s):
    local=datetime.fromisoformat(date_s+"T"+time_s).replace(tzinfo=TZ)
    return local.astimezone(timezone.utc).isoformat()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if current_user(request): return RedirectResponse("/",303)
    body='''<div class="card" style="max-width:460px;margin:auto"><h2>Aanmelden</h2><form method="post"><label>E-mail</label><input name="email" type="email" required><label>Wachtwoord</label><input name="password" type="password" required><p><button>Aanmelden</button></p></form></div>'''
    return HTMLResponse(page("Aanmelden",body))

@app.post("/login")
def login(email: str=Form(...), password: str=Form(...)):
    con=db(); row=con.execute("SELECT * FROM users WHERE email=? AND active=1",(email.lower(),)).fetchone(); con.close()
    if not row or not verify_password(password,row["password_hash"]): raise HTTPException(401,"Ongeldige aanmelding")
    resp=RedirectResponse("/",303); resp.set_cookie("tch_session",signer.dumps({"uid":row["id"]}),httponly=True,secure=COOKIE_SECURE,samesite="lax",max_age=60*60*12); return resp

@app.get("/logout")
def logout():
    r=RedirectResponse("/login",303); r.delete_cookie("tch_session"); return r

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    u=require_user(request)
    con=db(); upcoming=con.execute("SELECT * FROM events WHERE end_at>=? ORDER BY start_at LIMIT 12",(now_iso(),)).fetchall(); con.close()
    rows="".join(f"<tr><td>{esc(r['title'])}</td><td>{esc(datetime.fromisoformat(r['start_at']).astimezone(TZ).strftime('%d/%m/%Y %H:%M'))}</td><td>{esc(r['status'])}</td></tr>" for r in upcoming)
    dry=setting("smartschool_dry_run","1")=="1"
    banner='<div class="warn">Smartschool testmodus actief: publiceren schrijft nog niet naar Smartschool.</div>' if dry else ''
    body=f'''{banner}<div class="card"><h2>Activiteit toevoegen</h2><p class="muted">Schrijf in gewone taal. Je krijgt eerst een controleweergave.</p><form method="post" action="/interpret"><textarea name="prompt" placeholder="Voeg op 12 oktober van 13.30 tot 15.30 oudercontact L1-L3 toe" required></textarea><p><button>Interpreteren</button></p></form></div><div class="card"><h2>Komende activiteiten</h2><table><tr><th>Activiteit</th><th>Start</th><th>Status</th></tr>{rows or '<tr><td colspan=3>Nog geen activiteiten.</td></tr>'}</table></div>'''
    return HTMLResponse(page("Dashboard",body,u))

@app.post("/interpret", response_class=HTMLResponse)
def interpret_ui(request: Request, prompt: str=Form(...)):
    u=require_user(request); p=parse_instruction(prompt)
    warn=""
    if p["missing"]: warn=f'<div class="warn">Nog aan te vullen: {esc(", ".join(p["missing"]))}</div>'
    if p["assumptions"]: warn+=f'<div class="warn">Controleer: {esc("; ".join(p["assumptions"]))}</div>'
    body=f'''{warn}<div class="card"><h2>Controleer activiteit</h2><form method="post" action="/events/create"><input type="hidden" name="source_prompt" value="{esc(prompt)}"><label>Titel</label><input name="title" value="{esc(p['title'])}" required><div class="grid"><div><label>Datum</label><input name="date" type="date" value="{esc(p['date'])}" required></div><div><label>Start</label><input name="start_time" type="time" value="{esc(p['start_time'])}"></div><div><label>Einde</label><input name="end_time" type="time" value="{esc(p['end_time'])}"></div></div><label>Doelgroep (komma's)</label><input name="audience" value="{esc(', '.join(p['audience']))}"><label>Categorie</label><input name="category" value="{esc(p['category'])}"><label>Locatie</label><input name="location"><label>Beschrijving</label><textarea name="description"></textarea><p><button>Opslaan als concept</button> <a class="btn alt" href="/">Annuleren</a></p></form></div>'''
    audit(u["email"],"instruction.interpreted",payload={"prompt":prompt,"parsed":p})
    return HTMLResponse(page("Controle",body,u))

@app.post("/events/create")
def create_event(request: Request, title:str=Form(...), date:str=Form(...), start_time:str=Form(""), end_time:str=Form(""), audience:str=Form(""), category:str=Form("algemeen"), location:str=Form(""), description:str=Form(""), source_prompt:str=Form("")):
    u=require_user(request)
    if not start_time or not end_time: raise HTTPException(400,"Start- en eindtijd zijn verplicht")
    start_at=to_utc(date,start_time); end_at=to_utc(date,end_time)
    if end_at<=start_at: raise HTTPException(400,"Eindtijd moet na starttijd liggen")
    con=db(); dup=con.execute("SELECT id,title,start_at FROM events WHERE lower(title)=lower(?) AND abs(strftime('%s',start_at)-strftime('%s',?))<43200",(title,start_at)).fetchone()
    if dup: con.close(); raise HTTPException(409,f"Mogelijke dubbele activiteit: {dup['title']}")
    cur=con.execute("INSERT INTO events(title,description,start_at,end_at,location,audience,category,status,source_prompt,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(title,description,start_at,end_at,location,json.dumps([x.strip() for x in audience.split(',') if x.strip()]),category,"draft",source_prompt,u["id"],now_iso(),now_iso())); eid=cur.lastrowid; con.commit(); con.close(); audit(u["email"],"event.created",eid,{"title":title}); return RedirectResponse("/events",303)

@app.get("/events", response_class=HTMLResponse)
def events(request: Request):
    u=require_user(request); con=db(); rows=con.execute("SELECT * FROM events ORDER BY start_at DESC LIMIT 300").fetchall(); con.close()
    trs=[]
    for r in rows:
        start=datetime.fromisoformat(r["start_at"]).astimezone(TZ).strftime("%d/%m/%Y %H:%M")
        pub=""
        if u["role"] in ("director","secretary") and r["status"]!="published": pub=f'<form style="display:inline" method="post" action="/events/{r["id"]}/publish"><button>Publiceren</button></form>'
        trs.append(f"<tr><td>{esc(r['title'])}</td><td>{start}</td><td>{esc(r['category'])}</td><td>{esc(r['status'])}</td><td>{pub}</td></tr>")
    body=f'''<div class="card"><h2>Kalender</h2><table><tr><th>Activiteit</th><th>Start</th><th>Categorie</th><th>Status</th><th></th></tr>{''.join(trs) or '<tr><td colspan=5>Nog leeg.</td></tr>'}</table></div>'''
    return HTMLResponse(page("Kalender",body,u))

@app.post("/events/{event_id}/publish")
def publish_event(event_id:int, request: Request):
    u=require_user(request)
    if u["role"] not in ("director","secretary"): raise HTTPException(403,"Zorg kan niet publiceren")
    con=db(); r=con.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone()
    if not r: con.close(); raise HTTPException(404,"Niet gevonden")
    dry=setting("smartschool_dry_run","1")=="1"
    endpoints=all(setting(k) for k in ("planner_create","planner_update","planner_delete","planner_list"))
    if dry:
        con.close(); audit(u["email"],"smartschool.dry_run",event_id,{"title":r["title"]}); return RedirectResponse("/events",303)
    if not endpoints or not setting("smartschool_client_id"): con.close(); raise HTTPException(400,"Smartschool Planner API is nog niet volledig geconfigureerd")
    con.execute("UPDATE events SET status='failed',sync_error=? WHERE id=?",("Live Smartschool-call bewust geblokkeerd tot officiële Planner-specificatie is ingevuld",event_id)); con.commit(); con.close(); raise HTTPException(503,"Wacht op officiële Smartschool Planner-specificatie")

@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    u=require_user(request)
    if u["role"]!="director": raise HTTPException(403,"Alleen directie")
    keys=["smartschool_platform","smartschool_contact","smartschool_client_id","smartschool_scopes","planner_list","planner_create","planner_update","planner_delete"]
    fields="".join(f'<label>{esc(k)}</label><input name="{k}" value="{esc(setting(k))}">' for k in keys)
    checked="checked" if setting("smartschool_dry_run","1")=="1" else ""
    base=PUBLIC_BASE_URL or "https://JOUW-DOMEIN"
    embed=f'{base}/embed?token={setting("embed_token")}'
    body=f'''<div class="card"><h2>Smartschool</h2><form method="post">{fields}<label><input style="width:auto" type="checkbox" name="dry_run" value="1" {checked}> Testmodus</label><p><button>Opslaan</button></p></form></div><div class="card"><h2>Dynamische kalenderweergave</h2><p>Eenmalige URL voor Smartschool-HTML of als beveiligde link:</p><code>{esc(embed)}</code></div><div class="card"><h2>Smartschool-aanvraag</h2><p>Platform: <code>{esc(SS_PLATFORM)}</code><br>Contact: <code>{esc(SS_CONTACT)}</code></p><p>Vraag Smartschool om de Planner-scope en officiële list/create/update/delete endpoints. De app verzint deze bewust niet.</p></div><div class="card"><h2>ChatGPT connector</h2><form method="post" action="/api-keys"><label>Naam</label><input name="name" value="ChatGPT connector"><p><button>Nieuwe API-key</button></p></form></div>'''
    return HTMLResponse(page("Instellingen",body,u))

@app.post("/settings")
def settings_save(request: Request, smartschool_platform:str=Form(""), smartschool_contact:str=Form(""), smartschool_client_id:str=Form(""), smartschool_scopes:str=Form("userinfo"), planner_list:str=Form(""), planner_create:str=Form(""), planner_update:str=Form(""), planner_delete:str=Form(""), dry_run:str=Form("0")):
    u=require_user(request)
    if u["role"]!="director": raise HTTPException(403,"Alleen directie")
    vals=locals().copy()
    for k in ("smartschool_platform","smartschool_contact","smartschool_client_id","smartschool_scopes","planner_list","planner_create","planner_update","planner_delete"): set_setting(k,str(vals[k]))
    set_setting("smartschool_dry_run","1" if dry_run=="1" else "0"); audit(u["email"],"settings.updated"); return RedirectResponse("/settings",303)

@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request):
    u=require_user(request); con=db(); rows=con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 250").fetchall(); con.close()
    trs="".join(f"<tr><td>{esc(r['created_at'][:19])}</td><td>{esc(r['actor_email'])}</td><td>{esc(r['action'])}</td><td>{esc(r['event_id'])}</td></tr>" for r in rows)
    return HTMLResponse(page("Audit",f'<div class="card"><h2>Auditlog</h2><table><tr><th>Tijd</th><th>Gebruiker</th><th>Actie</th><th>Event</th></tr>{trs}</table></div>',u))

@app.get("/embed", response_class=HTMLResponse)
def embed(token:str):
    if not hmac.compare_digest(token,setting("embed_token")): raise HTTPException(403,"Ongeldige token")
    con=db(); rows=con.execute("SELECT * FROM events WHERE visible_in_embed=1 AND end_at>=? ORDER BY start_at LIMIT 120",(now_iso(),)).fetchall(); con.close()
    items="".join(f'<div class="card"><strong>{esc(r["title"])}</strong><div class="muted">{datetime.fromisoformat(r["start_at"]).astimezone(TZ).strftime("%d/%m/%Y · %H:%M")}</div><div>{esc(r["location"])}</div></div>' for r in rows)
    return HTMLResponse(page("Schoolkalender",items or '<div class="card">Geen komende activiteiten.</div>'))

class InterpretIn(BaseModel): text:str=Field(min_length=3,max_length=2000)
class EventIn(BaseModel):
    title:str; date:str; start_time:str; end_time:str; description:str=""; location:str=""; audience:list[str]=[]; category:str="algemeen"; source_prompt:str=""

def api_actor(authorization:Optional[str]=Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Bearer API-key vereist")
    raw=authorization[7:].strip(); digest=hashlib.sha256(raw.encode()).hexdigest(); con=db(); row=con.execute("SELECT k.*,u.email,u.role,u.active FROM api_keys k JOIN users u ON u.id=k.user_id WHERE k.key_hash=? AND k.revoked=0",(digest,)).fetchone(); con.close()
    if not row or not row["active"]: raise HTTPException(401,"Ongeldige API-key")
    return dict(row)

@app.post("/api/v1/interpret")
def api_interpret(body:InterpretIn, actor=Depends(api_actor)): return {"result":parse_instruction(body.text)}

@app.get("/api/v1/events")
def api_events(actor=Depends(api_actor)):
    con=db(); rows=[dict(r) for r in con.execute("SELECT * FROM events ORDER BY start_at DESC LIMIT 500")]; con.close(); return {"events":rows}

@app.post("/api/v1/events")
def api_create(body:EventIn, actor=Depends(api_actor)):
    start=to_utc(body.date,body.start_time); end=to_utc(body.date,body.end_time)
    if end<=start: raise HTTPException(400,"Eindtijd moet na starttijd liggen")
    con=db(); cur=con.execute("INSERT INTO events(title,description,start_at,end_at,location,audience,category,status,source_prompt,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(body.title,body.description,start,end,body.location,json.dumps(body.audience),body.category,"draft",body.source_prompt,actor["user_id"],now_iso(),now_iso())); eid=cur.lastrowid; con.commit(); con.close(); audit(actor["email"],"api.event.created",eid); return {"id":eid,"status":"draft"}

@app.post("/api-keys", response_class=HTMLResponse)
def create_api_key(request: Request, name:str=Form("ChatGPT connector")):
    u=require_user(request); raw="tch_"+secrets.token_urlsafe(32); digest=hashlib.sha256(raw.encode()).hexdigest(); con=db(); con.execute("INSERT INTO api_keys(user_id,name,prefix,key_hash,created_at) VALUES(?,?,?,?,?)",(u["id"],name,raw[:12],digest,now_iso())); con.commit(); con.close(); audit(u["email"],"api_key.created",payload={"prefix":raw[:12]}); return HTMLResponse(page("API-key",f'<div class="card"><h2>API-key aangemaakt</h2><p>Deze sleutel wordt maar één keer getoond.</p><code>{esc(raw)}</code><p><a class="btn" href="/settings">Terug</a></p></div>',u))

@app.get("/connector-openapi.json")
def connector_openapi(request:Request):
    origin=PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return {"openapi":"3.1.0","info":{"title":"Telescoop Calendar Hub API","version":"1.0.0"},"servers":[{"url":origin+"/api/v1"}],"components":{"securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer"}}},"security":[{"bearerAuth":[]}],"paths":{"/interpret":{"post":{"operationId":"interpretInstruction","summary":"Interpreteer een Nederlandse kalenderopdracht","requestBody":{"required":True,"content":{"application/json":{"schema":{"type":"object","required":["text"],"properties":{"text":{"type":"string"}}}}}},"responses":{"200":{"description":"OK"}}}},"/events":{"get":{"operationId":"listEvents","summary":"Lijst kalenderitems","responses":{"200":{"description":"OK"}}},"post":{"operationId":"createEvent","summary":"Maak een conceptactiviteit aan","responses":{"200":{"description":"Created"}}}}}}

@app.get("/health")
def health():
    try:
        con=db(); con.execute("SELECT 1"); con.close(); db_ok=True
    except Exception: db_ok=False
    return {"ok":db_ok,"db":db_ok,"smartschool":{"dry_run":setting("smartschool_dry_run","1")=="1","platform":setting("smartschool_platform"),"planner_endpoints_configured":all(setting(k) for k in ("planner_list","planner_create","planner_update","planner_delete"))}}
