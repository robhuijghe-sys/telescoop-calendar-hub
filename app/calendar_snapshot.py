from __future__ import annotations

import base64
import gzip
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import app.main as core
from app.calendar_dynamic import MONTH_NAMES, MONTH_PALETTES, SEASONS, WEEKDAYS, _event_line, _top_links_html

SNAPSHOT_PATH = Path(os.getenv("CALENDAR_SNAPSHOT_PATH", "/data/calendar_snapshot.json"))
SNAPSHOT_GZ_B64 = os.getenv("CALENDAR_SNAPSHOT_GZ_B64", "")


def _ensure_snapshot_file():
    if SNAPSHOT_PATH.exists() or not SNAPSHOT_GZ_B64:
        return
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = gzip.decompress(base64.b64decode(SNAPSHOT_GZ_B64.encode("ascii")))
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("entries"), list):
        raise RuntimeError("Invalid calendar snapshot payload")
    SNAPSHOT_PATH.write_bytes(raw)


def _load_snapshot():
    _ensure_snapshot_file()
    if not SNAPSHOT_PATH.exists():
        return {"focus": {}, "entries": []}
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"focus": {}, "entries": []}


def _dynamic_rows():
    con = core.db()
    rows = con.execute(
        "SELECT * FROM events WHERE visible_in_embed=1 ORDER BY start_at,id"
    ).fetchall()
    con.close()
    grouped = {}
    for row in rows:
        local = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ)
        grouped.setdefault(local.date().isoformat(), []).append(row)
    return grouped


def render_snapshot_calendar(hide_past=False, hidden_dates=()) -> str:
    snap = _load_snapshot()
    base_by_date = {e["date"]: e for e in snap.get("entries", [])}
    focus = snap.get("focus", {})
    dyn = _dynamic_rows()

    today = datetime.now(core.TZ).date()
    school_start_year = today.year if today.month >= 8 else today.year - 1
    end_year, end_month = school_start_year + 1, 8

    all_dates = set(base_by_date) | set(dyn)
    parsed_dates = []
    for ds in all_dates:
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            continue
        if ds in hidden_dates or (hide_past and d < today):
            continue
        if (d.year, d.month) < (today.year, today.month):
            continue
        if (d.year, d.month) > (end_year, end_month):
            continue
        parsed_dates.append(d)

    month_keys = sorted({(d.year, d.month) for d in parsed_dates} | (set() if hide_past else {(today.year, today.month)}))
    blocks = []
    for year, month in month_keys:
        month_days = sorted(d for d in parsed_dates if d.year == year and d.month == month)
        c1, c2 = MONTH_PALETTES[month]
        f = core.setting(f"month_focus_{year}_{month:02d}") or focus.get(f"{year}-{month:02d}", "")
        focus_html = f'<div class="focus"><span class="dot" style="background:{c1}"></span>{html.escape(f)}</div>' if f else ""
        desktop_rows = []
        mobile_rows = []
        for day in month_days:
            ds = day.isoformat()
            base = base_by_date.get(ds)
            label = base.get("label") if base else f"{WEEKDAYS[day.weekday()]} {day.strftime('%d/%m')}"
            pieces = []
            has_base_content = bool(base and base.get("html"))
            if has_base_content:
                pieces.append(f'<div class="base-content">{base["html"]}</div>')
            if ds in dyn:
                pieces.extend(f'<p class="event-line live-addition">{_event_line(row)}</p>' for row in dyn[ds])
            body = "".join(pieces) or '<span class="muted">Nog geen inhoud.</span>'
            event_cell_class = "event-cell live-only" if (not has_base_content and ds in dyn) else "event-cell"
            desktop_rows.append(f'<tr data-calendar-date="{ds}"><td class="date-cell">{html.escape(label)}</td><td class="{event_cell_class}">{body}</td></tr>')
            mobile_rows.append(f'<div class="mobile-day" data-calendar-date="{ds}"><div class="mobile-date">{html.escape(label)}</div><div class="mobile-events">{body}</div></div>')

        if not desktop_rows:
            desktop_rows.append('<tr><td class="event-cell" colspan="2">Nog geen kalenderitems.</td></tr>')
            mobile_rows.append('<div class="mobile-day"><div class="mobile-events">Nog geen kalenderitems.</div></div>')

        blocks.append(f'''<section class="month-card">
          <div class="month-head" style="background:linear-gradient(135deg,{c1} 0%,{c2} 100%)"><span class="month-title">{MONTH_NAMES[month]}</span><span class="season">{SEASONS[month]}</span></div>
          {focus_html}
          <table class="desktop-calendar"><tbody>{''.join(desktop_rows)}</tbody></table>
          <div class="mobile-calendar">{''.join(mobile_rows)}</div>
        </section>''')

    return f'''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><meta http-equiv="refresh" content="30"><style>
    *{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:#fff;color:#2e2926;font-family:Inter,Aptos,"Segoe UI",Calibri,Arial,sans-serif;font-size:12px;line-height:1.55;-webkit-text-size-adjust:100%;text-size-adjust:100%}}
    .wrap{{padding:20px 10px 28px;max-width:1280px;margin:0 auto}}.logo{{display:block;margin:0 auto 8px;max-width:210px;width:100%;height:auto}}
    .links{{margin:0 0 20px}}.quick{{margin:0;color:#726761;font-size:12px;line-height:1.55}}.quick a{{color:#6b5f59;text-decoration:none;border-bottom:1px solid #d8cfc8}}
    .month-card{{margin:0 0 20px;background:#fff;border:1px solid #ece7e1;border-radius:20px;overflow:hidden;box-shadow:0 10px 26px rgba(40,33,28,.05)}}
    .month-head{{padding:8px 18px 7px;display:flex;align-items:center;justify-content:space-between;gap:12px}}.month-title{{font-size:18px;line-height:1.05;font-weight:700;letter-spacing:-.02em;color:#fff}}
    .season{{display:inline-block;padding:3px 9px;border-radius:999px;background:rgba(255,255,255,.18);color:#fff;font-size:10px;letter-spacing:.14em;text-transform:uppercase;border:1px solid rgba(255,255,255,.25)}}
    .focus{{padding:10px 16px;border-bottom:1px solid #efe9e3;background:linear-gradient(180deg,#fbfaf8 0%,#fff 100%);color:#605651;font-size:12px;letter-spacing:.03em}}.dot{{display:inline-block;width:8px;height:8px;border-radius:999px;margin-right:8px;vertical-align:middle}}
    .desktop-calendar{{width:100%;border-collapse:collapse;background:#fff;font-size:12px}}.date-cell{{width:112px;min-width:112px;max-width:112px;background:#fff5eb;color:#5b524d;font-size:12px;font-weight:700;white-space:nowrap;padding:13px 14px;vertical-align:top;border-bottom:1px solid #f0ebe6}}
    .event-cell{{background:#fff;color:#2f2926;font-size:12px;line-height:1.55;padding:13px 16px;vertical-align:top;border-bottom:1px solid #f0ebe6;overflow-wrap:anywhere}}.event-cell.live-only{{vertical-align:middle}}.event-line{{margin:0 0 6px;font-size:12px;line-height:1.55}}.event-line:last-child{{margin-bottom:0}}
    .base-content,.base-content *{{font-family:Inter,Aptos,"Segoe UI",Calibri,Arial,sans-serif;font-size:12px;line-height:1.55;max-width:100%}}.base-content p{{margin-top:0}}.live-addition{{margin-top:6px}}.event-cell.live-only .live-addition{{margin-top:0}}
    .mobile-calendar{{display:none}}.muted{{color:#726761}}
    @media(max-width:560px){{html,body{{font-size:12px}}.wrap{{padding:10px 6px 18px}}.logo{{max-width:170px;margin-bottom:8px}}.links{{padding:0 6px;margin-bottom:14px}}.quick{{font-size:12px}}.month-card{{border-radius:14px;margin-bottom:14px;box-shadow:0 6px 18px rgba(40,33,28,.05)}}.month-head{{padding:8px 12px 7px}}.month-title{{font-size:17px}}.season{{font-size:9px;padding:3px 7px}}.focus{{padding:9px 12px;font-size:12px}}.desktop-calendar{{display:none}}.mobile-calendar{{display:block}}.mobile-day{{border-bottom:1px solid #f0ebe6}}.mobile-day:last-child{{border-bottom:0}}.mobile-date{{background:#fff5eb;color:#5b524d;font-size:12px;font-weight:700;padding:8px 12px}}.mobile-events{{padding:9px 12px 11px;background:#fff;color:#2f2926;font-size:12px;line-height:1.55;overflow-wrap:anywhere}}.event-line{{font-size:12px;line-height:1.55;margin-bottom:5px}}}}
    </style></head><body><main class="wrap"><img class="logo" src="https://telescoop-sgr8.smartschool.be/public/telescoop-sgr8/Images/P8JUKt6zzs28fnA9LjPg2owGK1768144749.PNG" alt="De Telescoop"><div class="links">{_top_links_html()}</div>{''.join(blocks)}</main></body></html>'''
