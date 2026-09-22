from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as core
from app.public_calendar import app, public_page, _remove_route


def _normalize_words(text: str) -> list[str]:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]+", s)
    mapped = []
    for w in words:
        if w.startswith("afwezig"):
            w = "afwezig"
        elif w.startswith("vergader"):
            w = "vergadering"
        elif w.startswith("oudercontact"):
            w = "oudercontact"
        elif w.startswith("directie"):
            w = "directie"
        if w not in {"de", "het", "een", "op", "van", "om", "voor", "toe", "kalender", "agenda"}:
            mapped.append(w)
    return mapped


def _score(query: str, title: str, description: str = "") -> float:
    q = _normalize_words(query)
    c = _normalize_words(" ".join([title or "", description or ""]))
    if not q:
        return 0.0
    qs, cs = set(q), set(c)
    overlap = len(qs & cs) / max(1, len(qs))
    seq = SequenceMatcher(None, " ".join(q), " ".join(c)).ratio()
    return overlap * 0.72 + seq * 0.28


def _is_delete_prompt(prompt: str) -> bool:
    return bool(re.match(r"^\s*(?:verwijder|wis)\b", prompt or "", re.I)) or bool(
        re.match(r"^\s*haal\b.+\bweg\s*$", prompt or "", re.I)
    )


def _delete_payload(prompt: str):
    raw = (prompt or "").strip()
    if re.match(r"^\s*(?:verwijder|wis)\b", raw, re.I):
        remainder = re.sub(r"^\s*(?:verwijder|wis)\b\s*", "", raw, flags=re.I)
    else:
        remainder = re.sub(r"^\s*haal\b\s*", "", raw, flags=re.I)
        remainder = re.sub(r"\bweg\s*$", "", remainder, flags=re.I)
    parsed = core.parse_instruction("voeg toe " + remainder)
    return parsed, parsed.get("title", "")


def _local_day_bounds(date_s: str):
    local_start = datetime.fromisoformat(date_s + "T00:00:00").replace(tzinfo=core.TZ)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(core.timezone.utc).isoformat(), local_end.astimezone(core.timezone.utc).isoformat()


def _find_candidates(date_s: str, query: str):
    start_utc, end_utc = _local_day_bounds(date_s)
    con = core.db()
    rows = con.execute(
        "SELECT id,title,description,start_at,end_at,all_day,category FROM events "
        "WHERE visible_in_embed=1 AND start_at>=? AND start_at<? ORDER BY start_at,id",
        (start_utc, end_utc),
    ).fetchall()
    con.close()
    scored = []
    for row in rows:
        score = _score(query, row["title"], row["description"])
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    strong = [(s, r) for s, r in scored if s >= 0.28]
    return strong[:6] if strong else scored[:6]


def _public_form(message: str = ""):
    return f'''{message}<div class="card"><h2>Kalender aanpassen</h2>
      <p class="muted">Geen login nodig. Je kunt activiteiten toevoegen of verwijderen in gewone taal.</p>
      <form method="post" action="/public/interpret">
        <label>Wat wil je doen?</label>
        <textarea name="prompt" placeholder="Bijv. Voeg op 6 oktober om 15.30 teamvergadering toe&#10;of: Verwijder op 1 december afwezigheid directie" required></textarea>
        <p><button>Interpreteren en controleren</button></p>
      </form>
      <p class="muted">Verwijderen gebeurt nooit meteen: je krijgt eerst het gevonden item te zien en moet bevestigen.</p>
      <p class="muted">Beheerder? <a href="/login">Aanmelden voor beheer</a></p>
    </div>'''


# Replace only the public home and interpret routes. Creation remains handled by app.public_calendar.
_remove_route("/", "GET")
_remove_route("/public/interpret", "POST")


@app.get("/", response_class=HTMLResponse)
def public_home_add_delete(request: Request, added: int = 0, deleted: int = 0):
    if core.current_user(request):
        return RedirectResponse("/events", 303)
    msg = ""
    if added:
        msg = '<div class="ok">Kalenderitem toegevoegd. Het verschijnt meteen in de dynamische kalender.</div>'
    elif deleted:
        msg = '<div class="ok">Kalenderitem verwijderd. Het verdwijnt meteen uit de dynamische kalender.</div>'
    return HTMLResponse(public_page("Kalender aanpassen", _public_form(msg)))


@app.post("/public/interpret", response_class=HTMLResponse)
def public_interpret_add_delete(prompt: str = Form(...)):
    if not _is_delete_prompt(prompt):
        # Keep the existing add flow, reproduced here so one public endpoint handles both intents.
        from app.calendar_dynamic import CATEGORY_COLORS
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

    parsed, query = _delete_payload(prompt)
    date_s = parsed.get("date")
    if not date_s:
        body = '<div class="warn">Ik kan niet bepalen van welke datum je iets wilt verwijderen. Vermeld een datum, bijvoorbeeld: <em>Verwijder op 1 december afwezigheid directie</em>.</div><p><a class="btn" href="/">Terug</a></p>'
        return HTMLResponse(public_page("Datum nodig", body), status_code=422)

    candidates = _find_candidates(date_s, query)
    if not candidates:
        body = f'''<div class="card"><h2>Geen dynamisch item gevonden</h2>
          <p>Voor {core.esc(datetime.fromisoformat(date_s).strftime('%d/%m/%Y'))} vond ik geen via de Calendar Hub toegevoegd item dat overeenkomt met <strong>{core.esc(query)}</strong>.</p>
          <p class="muted">Bestaande basisinhoud uit de oorspronkelijke Smartschoolkalender wordt nog niet automatisch verwijderd.</p>
          <p><a class="btn" href="/">Terug</a></p></div>'''
        return HTMLResponse(public_page("Niets gevonden", body), status_code=404)

    choices = []
    for score, row in candidates:
        local = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ)
        time_label = "zonder uur" if row["all_day"] else local.strftime("%H:%M")
        choices.append(
            f'''<label style="display:block;border:1px solid #e5dfd8;border-radius:10px;padding:11px 12px;margin:8px 0;color:#2f2926">
              <input style="width:auto;margin-right:8px" type="radio" name="event_id" value="{row['id']}" required>
              <strong>{core.esc(row['title'])}</strong><br><span class="muted">{core.esc(time_label)}</span>
            </label>'''
        )
    body = f'''<div class="card"><h2>Controleer wat je wilt verwijderen</h2>
      <p>{core.esc(datetime.fromisoformat(date_s).strftime('%d/%m/%Y'))} · gezocht naar: <strong>{core.esc(query)}</strong></p>
      <form method="post" action="/public/delete">
        <input type="hidden" name="source_prompt" value="{core.esc(prompt)}">
        {''.join(choices)}
        <p><button style="background:#8a2f2f">Geselecteerd item verwijderen</button> <a class="btn alt" href="/">Annuleren</a></p>
      </form>
      <p class="muted">Het item wordt verborgen en blijft in het auditspoor bewaard.</p>
    </div>'''
    core.audit("public-link", "public.delete_interpreted", payload={"prompt": prompt, "date": date_s, "query": query, "candidate_ids": [r["id"] for _, r in candidates]})
    return HTMLResponse(public_page("Verwijderen controleren", body))


@app.post("/public/delete")
def public_delete(event_id: int = Form(...), source_prompt: str = Form("")):
    con = core.db()
    row = con.execute("SELECT id,title,visible_in_embed FROM events WHERE id=?", (event_id,)).fetchone()
    if not row or not row["visible_in_embed"]:
        con.close()
        body = '<div class="warn">Dit kalenderitem bestaat niet meer of is al verwijderd.</div><p><a class="btn" href="/">Terug</a></p>'
        return HTMLResponse(public_page("Niet gevonden", body), status_code=404)
    now = core.now_iso()
    con.execute("UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?", (now, event_id))
    con.commit(); con.close()
    core.audit("public-link", "public.calendar_item_removed", event_id, {"title": row["title"], "source_prompt": source_prompt})
    return RedirectResponse("/?deleted=1", 303)
