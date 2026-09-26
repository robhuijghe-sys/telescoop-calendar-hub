from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as core
from app.calendar_dynamic import CATEGORY_COLORS, _smartschool_document, _times_to_utc, infer_category
from app.calendar_live import app


def _remove_route(path: str, method: Optional[str] = None):
    keep = []
    for route in app.router.routes:
        if getattr(route, "path", None) != path:
            keep.append(route)
            continue
        methods = getattr(route, "methods", set()) or set()
        if method and method.upper() not in methods:
            keep.append(route)
    app.router.routes[:] = keep


# The calendar posting screen is intentionally public. Management routes remain authenticated.
_remove_route("/", "GET")


def public_page(title: str, body: str):
    return f'''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{core.esc(title)} · Telescoop Calendar Hub</title>
    <style>
    :root{{--bg:#f7f5f1;--card:#fff;--ink:#2f2926;--muted:#726761;--line:#e5dfd8;--accent:#203555}}
    *{{box-sizing:border-box}}body{{margin:0;font-family:Inter,Aptos,'Segoe UI',Calibri,Arial,sans-serif;background:var(--bg);color:var(--ink)}}
    header{{background:#203555;color:#fff;padding:16px 18px}}header h1{{font-size:18px;margin:0}}main{{max-width:760px;margin:22px auto;padding:0 14px}}
    .card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:16px;box-shadow:0 7px 22px rgba(40,33,28,.05)}}
    h2{{font-size:20px;margin:0 0 8px}}p{{line-height:1.55}}label{{display:block;font-size:13px;color:var(--muted);margin:10px 0 5px}}
    input,textarea,select{{width:100%;padding:11px 12px;border:1px solid #d9d2ca;border-radius:9px;background:#fff;font:inherit}}textarea{{min-height:110px}}
    button,.btn{{display:inline-block;background:#203555;color:#fff;border:0;border-radius:9px;padding:10px 14px;text-decoration:none;cursor:pointer;font:inherit}}
    .btn.alt{{background:#edf1f7;color:#203555}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.muted{{color:var(--muted);font-size:13px}}
    .ok{{background:#eef7df;border:1px solid #cfe3a5;padding:12px;border-radius:10px}}.warn{{background:#fff5d9;border:1px solid #efd28a;padding:12px;border-radius:10px;margin-bottom:10px}}
    @media(max-width:560px){{main{{margin:12px auto;padding:0 10px}}.card{{border-radius:12px;padding:14px}}.grid{{grid-template-columns:1fr}}button,.btn{{width:100%;text-align:center;margin:3px 0}}}}
    </style></head><body><header><h1>Telescoop Calendar Hub</h1></header><main>{body}</main></body></html>'''


def _public_form(added: bool = False):
    msg = '<div class="ok">Kalenderitem toegevoegd. Het verschijnt meteen in de dynamische kalender.</div>' if added else ""
    return f'''{msg}<div class="card"><h2>Kalenderitem toevoegen</h2>
      <p class="muted">Geen login nodig. Schrijf in gewone taal; datum, uur en kleur worden automatisch geïnterpreteerd.</p>
      <form method="post" action="/public/interpret">
        <label>Wat wil je toevoegen?</label>
        <textarea name="prompt" placeholder="Bijv. Voeg op 6 oktober om 15.30 teamvergadering toe" required></textarea>
        <p><button>Interpreteren en controleren</button></p>
      </form>
      <p class="muted">Beheerder? <a href="/login">Aanmelden voor beheer</a></p>
    </div>'''


@app.get("/", response_class=HTMLResponse)
def public_home(request: Request, added: int = 0):
    if core.current_user(request):
        return RedirectResponse("/events", 303)
    return HTMLResponse(public_page("Kalenderitem toevoegen", _public_form(bool(added))))


@app.get("/smartschool-calendar", response_class=HTMLResponse)
def public_smartschool_calendar():
    # Stable public URL intended to be embedded once in the Smartschool news message.
    # The external document refreshes itself every 30 seconds, so the Smartschool HTML never needs to change.
    doc = _smartschool_document().replace(
        "<head>",
        '<head><meta http-equiv="refresh" content="30">',
        1,
    )
    return HTMLResponse(
        doc,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/public/interpret", response_class=HTMLResponse)
def public_interpret(prompt: str = Form(...)):
    p = core.parse_instruction(prompt)
    warn = ""
    if p.get("missing"):
        warn = f'<div class="warn">Nog aan te vullen: {core.esc(", ".join(p["missing"]))}</div>'
    if p.get("assumptions"):
        warn += f'<div class="warn">Controleer: {core.esc("; ".join(p["assumptions"]))}</div>'
    cat = p.get("category", "algemeen")
    options = "".join(
        f'<option value="{key}" {"selected" if key == cat else ""}>{label}</option>'
        for key, (_, label) in CATEGORY_COLORS.items()
    )
    checked = "checked" if p.get("all_day") else ""
    body = f'''{warn}<div class="card"><h2>Controleer kalenderitem</h2>
      <form method="post" action="/public/create">
        <input type="hidden" name="source_prompt" value="{core.esc(prompt)}">
        <label>Tekst in kalender</label><input name="title" value="{core.esc(p.get('title'))}" required>
        <div class="grid"><div><label>Datum</label><input name="date" type="date" value="{core.esc(p.get('date'))}" required></div>
        <div><label>Start (optioneel)</label><input name="start_time" type="time" value="{core.esc(p.get('start_time'))}"></div>
        <div><label>Einde (optioneel)</label><input name="end_time" type="time" value="{core.esc(p.get('end_time'))}"></div></div>
        <label style="display:flex;align-items:center;gap:8px"><input style="width:auto" type="checkbox" name="all_day" value="1" {checked}> Item zonder uur / hele dag</label>
        <label>Kleurcategorie <span class="muted">(automatisch gekozen, maar aanpasbaar)</span></label><select name="category">{options}</select>
        <label>Locatie (optioneel)</label><input name="location">
        <label>Extra regel(s) (optioneel)</label><textarea name="description"></textarea>
        <p><button>Toevoegen aan kalender</button> <a class="btn alt" href="/">Annuleren</a></p>
      </form></div>'''
    core.audit("public-link", "public.instruction_interpreted", payload={"prompt": prompt, "parsed": p})
    return HTMLResponse(public_page("Controle", body))


@app.post("/public/create")
def public_create(
    title: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(""),
    end_time: str = Form(""),
    all_day: str = Form("0"),
    category: str = Form("auto"),
    location: str = Form(""),
    description: str = Form(""),
    source_prompt: str = Form(""),
):
    resolved_category = infer_category(" ".join([title, description, source_prompt]), category)
    start, end, untimed = _times_to_utc(date, start_time, end_time, all_day == "1")
    con = core.db()
    duplicate = con.execute(
        "SELECT id,title FROM events WHERE visible_in_embed=1 AND lower(title)=lower(?) AND date(start_at)=date(?)",
        (title.strip(), start),
    ).fetchone()
    if duplicate:
        con.close()
        body = f'''<div class="card"><h2>Mogelijk dubbel item</h2><p>Er bestaat die dag al een item met de titel <strong>{core.esc(duplicate['title'])}</strong>.</p><p><a class="btn" href="/">Terug</a></p></div>'''
        return HTMLResponse(public_page("Dubbel item", body), status_code=409)
    now = core.now_iso()
    cur = con.execute(
        "INSERT INTO events(title,description,start_at,end_at,all_day,location,audience,category,status,source_prompt,visible_in_embed,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title.strip(), description.strip(), start, end, 1 if untimed else 0, location.strip(), "[]", resolved_category, "published", source_prompt, 1, 0, now, now),
    )
    eid = cur.lastrowid
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='editor_days'").fetchone():
        con.execute('DELETE FROM editor_days WHERE date_local=?', (date,))
    con.commit(); con.close()
    core.audit("public-link", "public.calendar_item_added", eid, {"title": title, "category": resolved_category})
    return RedirectResponse("/?added=1", 303)
