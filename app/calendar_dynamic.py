from __future__ import annotations

import html
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app.day_order import is_replacement
import app.main as core
from app.entry import app


CATEGORY_COLORS = {
    "ouders": ("#99CA3B", "Ouders"),
    "personeel": ("#C614A1", "Personeel"),
    "uitstap": ("#F09009", "Uitstap / activiteit"),
    "waarschuwing": ("#D32F2F", "Afwezig / waarschuwing"),
    "algemeen": ("#2F2926", "Algemeen"),
}

CATEGORY_ALIASES = {
    "ouders": "ouders",
    "ouder": "ouders",
    "team": "personeel",
    "personeel": "personeel",
    "staff": "personeel",
    "uitstap": "uitstap",
    "waarschuwing": "waarschuwing",
    "algemeen": "algemeen",
    "auto": "auto",
    "": "auto",
}

MONTH_NAMES = {
    1: "JANUARI", 2: "FEBRUARI", 3: "MAART", 4: "APRIL", 5: "MEI", 6: "JUNI",
    7: "JULI", 8: "AUGUSTUS", 9: "SEPTEMBER", 10: "OKTOBER", 11: "NOVEMBER", 12: "DECEMBER",
}
WEEKDAYS = ["ma", "di", "woe", "do", "vrij", "za", "zo"]
SEASONS = {1: "WINTER", 2: "WINTER", 3: "LENTE", 4: "LENTE", 5: "LENTE", 6: "ZOMER", 7: "ZOMER", 8: "ZOMER", 9: "HERFST", 10: "HERFST", 11: "HERFST", 12: "WINTER"}
MONTH_PALETTES = {
    1: ("#5F7F9F", "#7FA2C0"), 2: ("#748CB7", "#99ACD0"),
    3: ("#79A36B", "#9BC181"), 4: ("#76AD66", "#9ECB7F"), 5: ("#5FA66E", "#86C491"),
    6: ("#D7A83E", "#EFC45D"), 7: ("#D9904F", "#EFA567"), 8: ("#CF895C", "#E6A073"),
    9: ("#D39A5F", "#E9B06A"), 10: ("#C86F54", "#DE935F"), 11: ("#A85B52", "#C97860"),
    12: ("#6F87A8", "#8CA7C8"),
}

PARENT_WORDS = (
    "ouder", "ouders", "oudercontact", "ouderavond", "ouderinfo", "infomoment voor ouders", "voor ouders",
)
PERSONNEL_WORDS = (
    "personeel", "team", "leerkracht", "leerkrachten", "zorgoverleg", "zoco", "vakgroep", "directie",
    "personeelsvergadering", "teamvergadering", "overleg", "pedagogische studiedag",
)
OUTING_WORDS = (
    "uitstap", "gwp", "bosklas", "bosklassen", "zeeklas", "zeeklassen", "erfgoedklas", "erfgoedklassen",
    "schoolreis", "museum", "zwemmen", "toneel", "theater",
)
WARNING_WORDS = (
    "afwezig", "afw.", " afw ", "afgelast", "annul", "geen opvang", "gesloten", "waarschuwing",
)


def infer_category(text: str, explicit: str = "auto") -> str:
    if is_replacement(text):
        return "algemeen"
    explicit = CATEGORY_ALIASES.get((explicit or "auto").strip().lower(), "auto")
    if explicit != "auto":
        return explicit
    t = " " + (text or "").lower() + " "
    if any(word in t for word in WARNING_WORDS):
        return "waarschuwing"
    if any(word in t for word in PARENT_WORDS):
        return "ouders"
    if any(word in t for word in OUTING_WORDS):
        return "uitstap"
    if any(word in t for word in PERSONNEL_WORDS):
        return "personeel"
    return "algemeen"


def category_for_row(row) -> str:
    explicit = row["category"] if "category" in row.keys() else "auto"
    text = " ".join(str(row[k] or "") for k in ("title", "description", "source_prompt") if k in row.keys())
    return infer_category(text, explicit)


def color_for_row(row) -> str:
    return CATEGORY_COLORS[category_for_row(row)][0]


def improved_parse_instruction(text: str):
    p = core._legacy_parse_instruction(text) if hasattr(core, "_legacy_parse_instruction") else core.parse_instruction(text)
    combined = text + " " + p.get("title", "")
    p["category"] = infer_category(combined, "auto")
    # A dated item without an hour is a valid untimed calendar item, not an error.
    if p.get("date") and not p.get("start_time"):
        p["all_day"] = True
        p["missing"] = [x for x in p.get("missing", []) if x not in ("starttijd", "eindtijd")]
    # One known time is also valid; it is shown as a point-in-time item.
    if p.get("date") and p.get("start_time") and not p.get("end_time"):
        p["missing"] = [x for x in p.get("missing", []) if x != "eindtijd"]
    return p


if not hasattr(core, "_legacy_parse_instruction"):
    core._legacy_parse_instruction = core.parse_instruction
core.parse_instruction = improved_parse_instruction


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


# Replace the pieces that previously reflected the abandoned Planner approach.
for p, m in [
    ("/interpret", "POST"), ("/events/create", "POST"), ("/events", "GET"),
    ("/events/{event_id}/publish", "POST"), ("/settings", "GET"), ("/settings", "POST"),
    ("/embed", "GET"), ("/api/v1/events", "POST"), ("/connector-openapi.json", "GET"),
]:
    _remove_route(p, m)


# Replace the visible shortcut inserted by app.production without touching the working account code.
_previous_page = core.page

def calendar_page(title: str, body: str, user=None):
    rendered = _previous_page(title, body, user)
    rendered = rendered.replace('<a class="btn alt" href="/smartschool">Smartschool OAuth</a>', '<a class="btn alt" href="/calendar-settings">Smartschool kalender</a>')
    return rendered

core.page = calendar_page


@app.on_event("startup")
def calendar_defaults():
    # Current visual reference supplied by Rob: September focus line.
    if not core.setting("month_focus_2026_09"):
        core.set_setting("month_focus_2026_09", "KS: HOEKENWERK ▪▪▪ LS: SPELLING")


@app.post("/interpret", response_class=HTMLResponse)
def interpret(request: Request, prompt: str = Form(...)):
    user = core.require_user(request)
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
    swatches = " ".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin:3px 10px 3px 0"><span style="width:10px;height:10px;border-radius:50%;background:{color}"></span>{label}</span>'
        for color, label in CATEGORY_COLORS.values()
    )
    checked = "checked" if p.get("all_day") else ""
    body = f'''{warn}<div class="card"><h2>Controleer kalenderitem</h2>
      <form method="post" action="/events/create">
        <input type="hidden" name="source_prompt" value="{core.esc(prompt)}">
        <label>Tekst in kalender</label><input name="title" value="{core.esc(p.get('title'))}" required>
        <div class="grid"><div><label>Datum</label><input name="date" type="date" value="{core.esc(p.get('date'))}" required></div>
        <div><label>Start (optioneel)</label><input name="start_time" type="time" value="{core.esc(p.get('start_time'))}"></div>
        <div><label>Einde (optioneel)</label><input name="end_time" type="time" value="{core.esc(p.get('end_time'))}"></div></div>
        <label style="display:flex;align-items:center;gap:8px"><input style="width:auto" type="checkbox" name="all_day" value="1" {checked}> Item zonder uur / hele dag</label>
        <label>Kleurcategorie <span class="muted">(automatisch gekozen, maar aanpasbaar)</span></label><select name="category">{options}</select>
        <div class="muted" style="margin-top:6px">{swatches}</div>
        <label>Locatie (optioneel)</label><input name="location">
        <label>Extra regel(s) (optioneel)</label><textarea name="description"></textarea>
        <p><button>Toevoegen aan kalender</button> <a class="btn alt" href="/">Annuleren</a></p>
      </form></div>'''
    core.audit(user["email"], "instruction.interpreted", payload={"prompt": prompt, "parsed": p})
    return HTMLResponse(core.page("Controle", body, user))


def _times_to_utc(date: str, start_time: str, end_time: str, all_day: bool):
    if all_day or not start_time:
        start_time = "00:00"
        end_time = "23:59"
        all_day = True
    elif not end_time:
        end_time = start_time
    start = core.to_utc(date, start_time)
    end = core.to_utc(date, end_time)
    if end < start:
        raise HTTPException(400, "Eindtijd kan niet vóór de starttijd liggen")
    return start, end, all_day


@app.post("/events/create")
def create_event(
    request: Request,
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
    user = core.require_user(request)
    resolved_category = infer_category(" ".join([title, description, source_prompt]), category)
    start, end, untimed = _times_to_utc(date, start_time, end_time, all_day == "1")
    con = core.db()
    duplicate = con.execute(
        "SELECT id,title FROM events WHERE lower(title)=lower(?) AND date(start_at)=date(?)",
        (title.strip(), start),
    ).fetchone()
    if duplicate:
        con.close()
        raise HTTPException(409, f"Mogelijk dubbel kalenderitem: {duplicate['title']}")
    now = core.now_iso()
    cur = con.execute(
        "INSERT INTO events(title,description,start_at,end_at,all_day,location,audience,category,status,source_prompt,visible_in_embed,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title.strip(), description.strip(), start, end, 1 if untimed else 0, location.strip(), "[]", resolved_category, "published", source_prompt, 1, user["id"], now, now),
    )
    eid = cur.lastrowid
    con.commit(); con.close()
    core.audit(user["email"], "calendar.item_added", eid, {"title": title, "category": resolved_category})
    return RedirectResponse("/events", 303)


@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    user = core.require_user(request)
    con = core.db(); rows = con.execute("SELECT * FROM events ORDER BY start_at DESC LIMIT 400").fetchall(); con.close()
    trs = []
    for row in rows:
        local = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ)
        when = local.strftime("%d/%m/%Y") if row["all_day"] else local.strftime("%d/%m/%Y %H:%M")
        cat = category_for_row(row); color, label = CATEGORY_COLORS[cat]
        visible = "Ja" if row["visible_in_embed"] else "Nee"
        button = "Verbergen" if row["visible_in_embed"] else "Tonen"
        trs.append(f'''<tr><td><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{color};margin-right:6px"></span>{core.esc(row['title'])}</td><td>{when}</td><td>{label}</td><td>{visible}</td><td><form method="post" action="/events/{row['id']}/visibility"><button>{button}</button></form></td></tr>''')
    body = f'''<div class="card"><h2>Kalenderitems</h2><p><a class="btn" href="/calendar-preview">Voorbeeld Smartschoolweergave</a></p>
      <table><tr><th>Item</th><th>Datum</th><th>Kleur</th><th>Zichtbaar</th><th></th></tr>{''.join(trs) or '<tr><td colspan="5">Nog geen kalenderitems.</td></tr>'}</table></div>'''
    return HTMLResponse(core.page("Kalender", body, user))


@app.post("/events/{event_id}/visibility")
def toggle_visibility(event_id: int, request: Request):
    user = core.require_user(request)
    con = core.db(); row = con.execute("SELECT visible_in_embed FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        con.close(); raise HTTPException(404, "Kalenderitem niet gevonden")
    new_value = 0 if row["visible_in_embed"] else 1
    con.execute("UPDATE events SET visible_in_embed=?,updated_at=? WHERE id=?", (new_value, core.now_iso(), event_id)); con.commit(); con.close()
    core.audit(user["email"], "calendar.visibility_changed", event_id, {"visible": bool(new_value)})
    return RedirectResponse("/events", 303)


def _top_links_html() -> str:
    links = [
        ("Onenote", "https://testscholengroepbrussel-my.sharepoint.com/:o:/g/personal/rob_huijghe_detelescoop_be/IgAOyfDFRfhZR6w08r5dAbt-AXKxmsm7ny2aksqyugdZvGU?e=poTTO2"),
        ("Schoolorganisatie", "https://testscholengroepbrussel-my.sharepoint.com/:x:/g/personal/rob_huijghe_detelescoop_be/IQAOn-s4eVqvR5qcZ2beO3ZvAb9UiMi8D4KVEg8vh4jZwSA?e=Pdc5CC"),
        ("Poetsrooster", "https://testscholengroepbrussel-my.sharepoint.com/:w:/g/personal/rob_huijghe_detelescoop_be/IQCCIRgSUsAbSIL9n44qDIiFAUKbP3c8McbmhLicR2busoM?e=GJ6gov"),
        ("Maximumfactuur", "https://testscholengroepbrussel-my.sharepoint.com/:x:/g/personal/rob_huijghe_detelescoop_be/IQA8mH1HopDgQo7KJk9Z_LJyAXcbZvDJmiHHcd_WQ5p_CVE?e=xvlxo1"),
        ("Zorgoverleg 2026-2027", "https://telescoop-sgr8.smartschool.be/Browse/Index/Index/redirParam/YTo1OntzOjQ6ImdvVG8iO3M6MTI6ImNvdXJzZU1vZERldCI7czozOiJjSUQiO2k6MDtzOjM6Im1vZCI7czo0OiJOZXdzIjtzOjM6Im5JRCI7czozOiIzMjYiO3M6NDoic3NJRCI7aTozNTMzO30="),
        ("Naschoolse activiteiten - lijst deelnemers.xlsx", "https://telescoop-sgr8.smartschool.be/deeplink/3533/f9b1e072-0097-42ce-97e4-bd6bdaa1a511"),
    ]
    return "".join(f'<p class="quick">{html.escape(label)} <a href="{html.escape(url)}" target="_blank" rel="noopener">🔗 openen</a></p>' for label, url in links)


def _event_line(row) -> str:
    local_start = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ)
    local_end = datetime.fromisoformat(row["end_at"]).astimezone(core.TZ)
    prefix = ""
    if not row["all_day"]:
        if local_start.strftime("%H:%M") == local_end.strftime("%H:%M"):
            prefix = local_start.strftime("%H.%M") + "u: "
        else:
            prefix = local_start.strftime("%H.%M") + "-" + local_end.strftime("%H.%M") + "u: "
    text = prefix + row["title"]
    if row["location"]:
        text += " — " + row["location"]
    color = color_for_row(row)
    desc = ""
    if row["description"]:
        desc = '<br>' + '<br>'.join(html.escape(x) for x in row["description"].splitlines() if x.strip())
    return f'<span style="color:{color};font-weight:{"700" if color != CATEGORY_COLORS["algemeen"][0] else "400"}">{html.escape(text)}</span>{desc}'


def _calendar_data():
    now = datetime.now(core.TZ)
    school_start_year = now.year if now.month >= 8 else now.year - 1
    start_local = datetime(school_start_year, 8, 1, tzinfo=core.TZ)
    end_local = datetime(school_start_year + 1, 8, 1, tzinfo=core.TZ)
    con = core.db()
    rows = con.execute(
        "SELECT * FROM events WHERE visible_in_embed=1 AND start_at>=? AND start_at<? ORDER BY start_at,id",
        (start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()),
    ).fetchall(); con.close()
    grouped = {}
    for row in rows:
        local = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ)
        key = (local.year, local.month)
        grouped.setdefault(key, {}).setdefault(local.date(), []).append(row)
    return grouped, school_start_year


def _render_calendar_body() -> str:
    grouped, school_year = _calendar_data()
    blocks = []
    # Begin with the current month; past dates within the month remain visible for context.
    today = datetime.now(core.TZ).date()
    month_cursor = datetime(today.year, today.month, 1, tzinfo=core.TZ)
    school_end = datetime(school_year + 1, 7, 1, tzinfo=core.TZ)
    while month_cursor <= school_end:
        key = (month_cursor.year, month_cursor.month)
        days = grouped.get(key, {})
        # Keep months only when they have content, except current month.
        if days or (month_cursor.year == today.year and month_cursor.month == today.month):
            m = month_cursor.month; c1, c2 = MONTH_PALETTES[m]
            focus = core.setting(f"month_focus_{month_cursor.year}_{m:02d}")
            focus_html = f'<div class="focus"><span class="dot" style="background:{c1}"></span>{html.escape(focus)}</div>' if focus else ""
            desktop_rows = []
            mobile_rows = []
            for day, day_rows in sorted(days.items()):
                label = f"{WEEKDAYS[day.weekday()]} {day.strftime('%d/%m')}"
                lines = "".join(f'<p class="event-line">{_event_line(r)}</p>' for r in day_rows)
                desktop_rows.append(f'<tr><td class="date-cell">{label}</td><td class="event-cell">{lines}</td></tr>')
                mobile_rows.append(f'<div class="mobile-day"><div class="mobile-date">{label}</div><div class="mobile-events">{lines}</div></div>')
            if not desktop_rows:
                desktop_rows.append('<tr><td class="event-cell" colspan="2">Nog geen kalenderitems.</td></tr>')
                mobile_rows.append('<div class="mobile-day"><div class="mobile-events">Nog geen kalenderitems.</div></div>')
            blocks.append(f'''<section class="month-card">
              <div class="month-head" style="background:linear-gradient(135deg,{c1} 0%,{c2} 100%)"><span class="month-title">{MONTH_NAMES[m]}</span><span class="season">{SEASONS[m]}</span></div>
              {focus_html}
              <table class="desktop-calendar"><tbody>{''.join(desktop_rows)}</tbody></table>
              <div class="mobile-calendar">{''.join(mobile_rows)}</div>
            </section>''')
        # next month
        if month_cursor.month == 12:
            month_cursor = datetime(month_cursor.year + 1, 1, 1, tzinfo=core.TZ)
        else:
            month_cursor = datetime(month_cursor.year, month_cursor.month + 1, 1, tzinfo=core.TZ)
    return ''.join(blocks)


def _smartschool_document() -> str:
    body = _render_calendar_body()
    return f'''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><style>
    *{{box-sizing:border-box}} html,body{{margin:0;padding:0;background:#fff;color:#2e2926;font-family:Inter,Aptos,"Segoe UI",Calibri,Arial,sans-serif;font-size:12px;line-height:1.55;-webkit-text-size-adjust:100%;text-size-adjust:100%}}
    .wrap{{padding:20px 10px 28px;max-width:1280px;margin:0 auto}} .logo{{display:block;margin:0 auto 8px;max-width:210px;width:100%;height:auto}}
    .links{{margin:0 0 20px}} .quick{{margin:0;color:#726761;font-size:12px;line-height:1.55}} .quick a{{color:#6b5f59;text-decoration:none;border-bottom:1px solid #d8cfc8}}
    .month-card{{margin:0 0 20px;background:#fff;border:1px solid #ece7e1;border-radius:20px;overflow:hidden;box-shadow:0 10px 26px rgba(40,33,28,.05)}}
    .month-head{{padding:8px 18px 7px;display:flex;align-items:center;justify-content:space-between;gap:12px}} .month-title{{font-size:18px;line-height:1.05;font-weight:700;letter-spacing:-.02em;color:#fff}}
    .season{{display:inline-block;padding:3px 9px;border-radius:999px;background:rgba(255,255,255,.18);color:#fff;font-size:10px;letter-spacing:.14em;text-transform:uppercase;border:1px solid rgba(255,255,255,.25)}}
    .focus{{padding:10px 16px;border-bottom:1px solid #efe9e3;background:linear-gradient(180deg,#fbfaf8 0%,#fff 100%);color:#605651;font-size:12px;letter-spacing:.03em}} .dot{{display:inline-block;width:8px;height:8px;border-radius:999px;margin-right:8px;vertical-align:middle}}
    .desktop-calendar{{width:100%;border-collapse:collapse;background:#fff;font-size:12px}} .date-cell{{width:112px;min-width:112px;max-width:112px;background:#fff5eb;color:#5b524d;font-size:12px;font-weight:700;white-space:nowrap;padding:13px 14px;vertical-align:top;border-bottom:1px solid #f0ebe6}}
    .event-cell{{background:#fff;color:#2f2926;font-size:12px;line-height:1.55;padding:13px 16px;vertical-align:top;border-bottom:1px solid #f0ebe6;overflow-wrap:anywhere}} .event-line{{margin:0 0 6px;font-size:12px;line-height:1.55}} .event-line:last-child{{margin-bottom:0}}
    .mobile-calendar{{display:none}}
    @media (max-width:560px){{
      html,body{{font-size:12px}} .wrap{{padding:10px 6px 18px}} .logo{{max-width:170px;margin-bottom:8px}} .links{{padding:0 6px;margin-bottom:14px}} .quick{{font-size:12px}}
      .month-card{{border-radius:14px;margin-bottom:14px;box-shadow:0 6px 18px rgba(40,33,28,.05)}} .month-head{{padding:8px 12px 7px}} .month-title{{font-size:17px}} .season{{font-size:9px;padding:3px 7px}}
      .focus{{padding:9px 12px;font-size:12px}} .desktop-calendar{{display:none}} .mobile-calendar{{display:block}}
      .mobile-day{{border-bottom:1px solid #f0ebe6}} .mobile-day:last-child{{border-bottom:0}} .mobile-date{{background:#fff5eb;color:#5b524d;font-size:12px;font-weight:700;padding:8px 12px}}
      .mobile-events{{padding:9px 12px 11px;background:#fff;color:#2f2926;font-size:12px;line-height:1.55;overflow-wrap:anywhere}} .event-line{{font-size:12px;line-height:1.55;margin-bottom:5px}}
    }}
    </style></head><body><main class="wrap"><img class="logo" src="https://telescoop-sgr8.smartschool.be/public/telescoop-sgr8/Images/P8JUKt6zzs28fnA9LjPg2owGK1768144749.PNG" alt="De Telescoop"><div class="links">{_top_links_html()}</div>{body}</main></body></html>'''


@app.get("/embed", response_class=HTMLResponse)
def smartschool_embed(token: str):
    if not hmac.compare_digest(token, core.setting("embed_token")):
        raise HTTPException(403, "Ongeldige kalenderlink")
    return HTMLResponse(_smartschool_document(), headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"})


@app.get("/calendar-preview", response_class=HTMLResponse)
def calendar_preview(request: Request):
    core.require_user(request)
    return HTMLResponse(_smartschool_document(), headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/calendar-settings", response_class=HTMLResponse)
def calendar_settings(request: Request):
    user = core.require_user(request)
    if user["role"] != "director":
        raise HTTPException(403, "Alleen directie")
    base = core.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    url = f'{base}/embed?token={core.setting("embed_token")}'
    iframe = f'<iframe src="{url}" width="100%" height="1050" frameborder="0" scrolling="yes" style="display:block;width:100%;max-width:100%;height:78vh;min-height:760px;border:0;background:#fff" title="Kalender De Telescoop"></iframe>'
    # Month focus inputs: current school year, Sep-Jun.
    now = datetime.now(core.TZ); sy = now.year if now.month >= 8 else now.year - 1
    focus_fields = []
    for month in list(range(9, 13)) + list(range(1, 7)):
        year = sy if month >= 9 else sy + 1
        key = f"month_focus_{year}_{month:02d}"
        focus_fields.append(f'<label>{MONTH_NAMES[month].title()} {year}</label><input name="{key}" value="{core.esc(core.setting(key))}">')
    legend = "".join(f'<div style="display:flex;gap:8px;align-items:center;margin:5px 0"><span style="width:12px;height:12px;border-radius:50%;background:{c}"></span>{label}</div>' for c, label in CATEGORY_COLORS.values())
    body = f'''<div class="card"><h2>Dynamische Smartschoolkalender</h2>
      <p>Deze weergave gebruikt dezelfde visuele taal als je actuele kalender, maar de inhoud komt voortaan uit de Calendar Hub.</p>
      <p><a class="btn" href="/calendar-preview" target="_blank">Voorbeeld openen</a></p>
      <label>Eenmalige iframe-code voor het Smartschool-nieuwsbericht</label><textarea readonly style="min-height:180px">{core.esc(iframe)}</textarea>
      <p class="muted">Als Smartschool een iframe weigert, gebruik tijdelijk de directe kalenderlink hieronder; dan bouwen we de fallback verder uit op basis van wat Smartschool precies doorlaat.</p>
      <label>Directe kalenderlink</label><input readonly value="{core.esc(url)}">
    </div>
    <div class="card"><h2>Automatische kleuren</h2>{legend}<p class="muted">De Hub kiest deze automatisch op basis van de tekst. Bij het toevoegen kan je de categorie altijd handmatig overschrijven.</p></div>
    <div class="card"><h2>Focusregel per maand</h2><form method="post" action="/calendar-settings">{''.join(focus_fields)}<p><button>Focusregels opslaan</button></p></form></div>'''
    return HTMLResponse(core.page("Smartschool kalender", body, user))


@app.post("/calendar-settings")
async def save_calendar_settings(request: Request):
    user = core.require_user(request)
    if user["role"] != "director":
        raise HTTPException(403, "Alleen directie")
    form = await request.form()
    for key, value in form.items():
        if re.fullmatch(r"month_focus_\d{4}_\d{2}", key):
            core.set_setting(key, str(value).strip())
    core.audit(user["email"], "calendar.settings_updated")
    return RedirectResponse("/calendar-settings", 303)


@app.get("/settings")
def redirect_old_settings(request: Request):
    core.require_user(request)
    return RedirectResponse("/calendar-settings", 303)


class CalendarEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    date: str
    start_time: str = ""
    end_time: str = ""
    all_day: bool = False
    description: str = ""
    location: str = ""
    category: str = "auto"
    source_prompt: str = ""


@app.post("/api/v1/events")
def api_create_calendar_event(body: CalendarEventIn, actor=Depends(core.api_actor)):
    category = infer_category(" ".join([body.title, body.description, body.source_prompt]), body.category)
    start, end, untimed = _times_to_utc(body.date, body.start_time, body.end_time, body.all_day)
    con = core.db(); now = core.now_iso()
    cur = con.execute(
        "INSERT INTO events(title,description,start_at,end_at,all_day,location,audience,category,status,source_prompt,visible_in_embed,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (body.title.strip(), body.description.strip(), start, end, 1 if untimed else 0, body.location.strip(), "[]", category, "published", body.source_prompt, 1, actor["user_id"], now, now),
    )
    eid = cur.lastrowid; con.commit(); con.close()
    core.audit(actor["email"], "api.calendar_item_added", eid, {"category": category})
    return {"id": eid, "status": "visible", "category": category, "color": CATEGORY_COLORS[category][0]}


@app.get("/connector-openapi.json")
def connector_openapi(request: Request):
    origin = core.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return {
        "openapi": "3.1.0",
        "info": {"title": "Telescoop Dynamic Calendar API", "version": "2.0.0"},
        "servers": [{"url": origin + "/api/v1"}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "security": [{"bearerAuth": []}],
        "paths": {
            "/interpret": {"post": {"operationId": "interpretCalendarInstruction", "summary": "Interpreteer een Nederlandse kalenderopdracht", "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}}}, "responses": {"200": {"description": "OK"}}}},
            "/events": {
                "get": {"operationId": "listCalendarItems", "summary": "Lijst kalenderitems", "responses": {"200": {"description": "OK"}}},
                "post": {"operationId": "addCalendarItem", "summary": "Voeg een item rechtstreeks toe aan de dynamische Smartschoolkalender", "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["title", "date"], "properties": {"title": {"type": "string"}, "date": {"type": "string", "format": "date"}, "start_time": {"type": "string", "description": "HH:MM, optioneel"}, "end_time": {"type": "string", "description": "HH:MM, optioneel"}, "all_day": {"type": "boolean"}, "description": {"type": "string"}, "location": {"type": "string"}, "category": {"type": "string", "enum": ["auto", "ouders", "personeel", "uitstap", "waarschuwing", "algemeen"], "default": "auto"}, "source_prompt": {"type": "string"}}}}}}, "responses": {"200": {"description": "Toegevoegd"}}}
            }
        }
    }
