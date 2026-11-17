"""One-time update of Ananda's school-day absences and Friday replacements.

Approved schedule: 19–24 November (school days only), and 1 December 2026.
Replacement schedule: Friday 20 November 2026.
Do not show personal reasons for absence.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

import app.main as core

MARKER = "calendar_ananda_absences_2026_11_17_v1"
ABSENCE_DATES = (
    "2026-11-19",
    "2026-11-20",
    "2026-11-23",
    "2026-11-24",
    "2026-12-01",
)
FRIDAY = "2026-11-20"
REPLACEMENTS = (
    "2de en 3de lesuur: GR3 - Eline (vervangt Ananda)",
    "4de lesuur: L2 - Helena (NED, vervangt Ananda)",
    "5de lesuur: L2 - Helena (NED, vervangt Ananda)",
    "6de lesuur: L1 - Axelle (WO thema, vervangt Ananda)",
)


def inspect(con):
    """Return only affected calendar records, not other staff's appointments."""
    dates = set(ABSENCE_DATES)
    rows = con.execute(
        "SELECT id,date_local,title,activity_type,whole_day "
        "FROM editor_lines WHERE deleted=0 AND date_local >= ? "
        "AND date_local <= ? ORDER BY date_local,id",
        (min(dates), max(dates)),
    ).fetchall()
    found = [
        dict(r) for r in rows
        if r["date_local"] in dates
        and ("ananda" in r["title"].casefold() or
             (r["date_local"] == FRIDAY and any(
                r["title"].casefold() == label.casefold() for label in REPLACEMENTS
             )))
    ]
    return found


def add_ananda_calendar():
    con = core.db()
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            return
        if any(date.fromisoformat(day).weekday() >= 5 for day in ABSENCE_DATES):
            raise RuntimeError("Only school days should be registered")
        if date.fromisoformat(FRIDAY).weekday() != 4:
            raise RuntimeError("Substitution date is not a Friday")
        hidden = [r["date_local"] for r in con.execute(
            "SELECT date_local FROM editor_days WHERE hidden=1"
        ) if r["date_local"] in ABSENCE_DATES]
        if hidden:
            print("ANANDA_CALENDAR_ABORTED hidden-days " + json.dumps(hidden), flush=True)
            return

        # Save a recoverable copy before any rows are inserted.
        backup_path = Path(str(core.DB_PATH) + ".before-ananda-20261117.bak")
        if not backup_path.exists():
            backup = sqlite3.connect(str(backup_path))
            try:
                con.backup(backup)
            finally:
                backup.close()

        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            con.rollback()
            return

        # The public calendar can hide a whole day. Do not unintentionally
        # reactivate hidden days or alter existing appointments.
        changes = []
        for day in ABSENCE_DATES:
            current = [
                r for r in con.execute(
                    "SELECT title FROM editor_lines WHERE date_local=? AND deleted=0",
                    (day,),
                )
                if "ananda" in r["title"].casefold()
                and ("afwezig" in r["title"].casefold() or "afw" in r["title"].casefold())
            ]
            if current:
                changes.append({"date": day, "item": "Ananda afwezig", "operation": "already-present"})
                continue
            title = "DAG: Ananda afwezig"
            ident = con.execute(
                "INSERT INTO editor_lines(date_local,body_html,title,activity_type,whole_day) "
                "VALUES(?,?,?,?,?)",
                (day, title, title, "waarschuwing", 1),
            ).lastrowid
            changes.append({"date": day, "id": ident, "item": title, "operation": "added"})

        for title in REPLACEMENTS:
            present = con.execute(
                "SELECT id FROM editor_lines WHERE date_local=? AND deleted=0 AND lower(title)=lower(?)",
                (FRIDAY, title),
            ).fetchone()
            if present:
                changes.append({"date": FRIDAY, "id": present["id"], "item": title, "operation": "already-present"})
                continue
            ident = con.execute(
                "INSERT INTO editor_lines(date_local,body_html,title,activity_type,whole_day) "
                "VALUES(?,?,?,?,?)",
                (FRIDAY, title, title, "waarschuwing", 0),
            ).lastrowid
            changes.append({"date": FRIDAY, "id": ident, "item": title, "operation": "added"})

        payload = json.dumps({"changes": changes}, ensure_ascii=False)
        con.execute(
            "INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)",
            ("school-calendar", "calendar.ananda_absences_scheduled", payload, core.now_iso()),
        )
        con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (MARKER, payload))
        con.commit()
        print("ANANDA_CALENDAR_APPLIED " + payload, flush=True)
        print("ANANDA_CALENDAR_VERIFIED " + json.dumps(inspect(con), ensure_ascii=False), flush=True)
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
