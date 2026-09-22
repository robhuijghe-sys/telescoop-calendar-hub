from __future__ import annotations

import base64
import json
import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from bs4 import BeautifulSoup, NavigableString, Tag
from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as core
from app.calendar_snapshot import SNAPSHOT_PATH
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


def _dynamic_candidates(date_s: str, query: str):
    start_utc, end_utc = _local_day_bounds(date_s)
    con = core.db()
    rows = con.execute(
        "SELECT id,title,description,start_at,end_at,all_day,category FROM events "
        "WHERE visible_in_embed=1 AND start_at>=? AND start_at<? ORDER BY start_at,id",
        (start_utc, end_utc),
    ).fetchall()
    con.close()
    out = []
    for row in rows:
        local = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ)
        time_label = "zonder uur" if row["all_day"] else local.strftime("%H:%M")
        out.append({
            "score": _score(query, row["title"], row["description"]),
            "kind": "event",
            "value": f"event:{row['id']}",
            "title": row["title"],
            "meta": f"Toegevoegd via Calendar Hub · {time_label}",
        })
    return out


def _read_snapshot():
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _snapshot_candidates(date_s: str, query: str):
    data = _read_snapshot()
    if not data:
        return []
    entry = next((e for e in data.get("entries", []) if e.get("date") == date_s), None)
    if not entry or not entry.get("html"):
        return []
    soup = BeautifulSoup(entry["html"], "html.parser")
    seen = set()
    out = []
    for node in soup.find_all(string=True):
        text = " ".join(str(node).split())
        if not text or text in seen:
            continue
        seen.add(text)
        encoded = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
        out.append({
            "score": _score(query, text),
            "kind": "snapshot",
            "value": f"snapshot:{encoded}",
            "title": text,
            "meta": "Bestaande kalenderinhoud",
        })
    return out


def _find_candidates(date_s: str, query: str):
    candidates = _dynamic_candidates(date_s, query) + _snapshot_candidates(date_s, query)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    strong = [c for c in candidates if c["score"] >= 0.28]
    return (strong if strong else candidates)[:8]


def _clean_empty_container(tag):
    current = tag
    while isinstance(current, Tag) and current.name not in {"html", "body", "[document]"}:
        if current.get_text(strip=True) or current.find(["img", "a"]):
            break
        parent = current.parent
        prev = current.previous_sibling
        nxt = current.next_sibling
        current.extract()
        if isinstance(nxt, Tag) and nxt.name == "br":
            nxt.extract()
        elif isinstance(prev, Tag) and prev.name == "br":
            prev.extract()
        current = parent


def _remove_snapshot_text(date_s: str, target_text: str) -> bool:
    data = _read_snapshot()
    if not data:
        return False
    entry = next((e for e in data.get("entries", []) if e.get("date") == date_s), None)
    if not entry:
        return False
    soup = BeautifulSoup(entry.get("html", ""), "html.parser")
    target_norm = " ".join(target_text.split())
    match = None
    for node in soup.find_all(string=True):
        if " ".join(str(node).split()) == target_norm:
            match = node
            break
    if match is None:
        return False

    parent = match.parent
    prev = match.previous_sibling
    nxt = match.next_sibling
    match.extract()
    if isinstance(nxt, Tag) and nxt.name == "br":
        nxt.extract()
    elif isinstance(prev, Tag) and prev.name == "br":
        prev.extract()
    _clean_empty_container(parent)

    entry["html"] = str(soup).strip()
    tmp = SNAPSHOT_PATH.with_suffix(SNAPSHOT_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(SNAPSHOT_PATH)
    return True


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
        body = f'''<div class="card"><h2>Niets gevonden</h2>
          <p>Voor {core.esc(datetime.fromisoformat(date_s).strftime('%d/%m/%Y'))} vond ik geen kalenderregel die overeenkomt met <strong>{core.esc(query)}</strong>.</p>
          <p><a class="btn" href="/">Terug</a></p></div>'''
        return HTMLResponse(public_page("Niets gevonden", body), status_code=404)

    choices = []
    for candidate in candidates:
        choices.append(
            f'''<label style="display:block;border:1px solid #e5dfd8;border-radius:10px;padding:11px 12px;margin:8px 0;color:#2f2926">
              <input style="width:auto;margin-right:8px" type="radio" name="candidate" value="{core.esc(candidate['value'])}" required>
              <strong>{core.esc(candidate['title'])}</strong><br><span class="muted">{core.esc(candidate['meta'])}</span>
            </label>'''
        )
    body = f'''<div class="card"><h2>Controleer wat je wilt verwijderen</h2>
      <p>{core.esc(datetime.fromisoformat(date_s).strftime('%d/%m/%Y'))} · gezocht naar: <strong>{core.esc(query)}</strong></p>
      <form method="post" action="/public/delete">
        <input type="hidden" name="source_prompt" value="{core.esc(prompt)}">
        <input type="hidden" name="date" value="{core.esc(date_s)}">
        {''.join(choices)}
        <p><button style="background:#8a2f2f">Geselecteerde regel verwijderen</button> <a class="btn alt" href="/">Annuleren</a></p>
      </form>
      <p class="muted">Er wordt pas iets gewijzigd nadat je hier een regel selecteert en bevestigt.</p>
    </div>'''
    core.audit("public-link", "public.delete_interpreted", payload={"prompt": prompt, "date": date_s, "query": query, "candidate_count": len(candidates)})
    return HTMLResponse(public_page("Verwijderen controleren", body))


@app.post("/public/delete")
def public_delete(candidate: str = Form(...), date: str = Form(""), source_prompt: str = Form("")):
    if candidate.startswith("event:"):
        try:
            event_id = int(candidate.split(":", 1)[1])
        except ValueError:
            event_id = 0
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

    if candidate.startswith("snapshot:"):
        encoded = candidate.split(":", 1)[1]
        try:
            target = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        except Exception:
            target = ""
        if not date or not target or not _remove_snapshot_text(date, target):
            body = '<div class="warn">Deze bestaande kalenderregel kon niet meer worden teruggevonden. Er is niets verwijderd.</div><p><a class="btn" href="/">Terug</a></p>'
            return HTMLResponse(public_page("Niet gevonden", body), status_code=404)
        core.audit("public-link", "public.snapshot_item_removed", payload={"date": date, "text": target, "source_prompt": source_prompt})
        return RedirectResponse("/?deleted=1", 303)

    body = '<div class="warn">Ongeldige verwijderkeuze. Er is niets gewijzigd.</div><p><a class="btn" href="/">Terug</a></p>'
    return HTMLResponse(public_page("Ongeldige keuze", body), status_code=400)
