"""One-time, audited rescheduling of the two three-session research blocks.

Dates and labels were checked against the live calendar on 17 November 2026.
No medical screenings or research-question deadlines are included.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

import app.main as core

MARKER = "research_cycle_moved_2026_11_27"
CHANGES = (
    (2726, "2026-11-23", "op onderzoek", "2026-11-27"),
    (1304, "2026-11-30", "onderzoek sessie 2", "2026-12-04"),
    (1323, "2026-12-07", "onderzoek sessie 3", "2026-12-11"),
    (1462, "2027-03-08", "op onderzoek", "2027-03-12"),
    (1479, "2027-03-15", "onderzoek sessie 2", "2027-03-19"),
    (1490, "2027-03-22", "onderzoek sessie 3", "2027-03-26"),
)


def verify(con):
    """Abort the entire migration if any record or destination has changed."""
    ids = tuple(row[0] for row in CHANGES)
    rows = {r["id"]: r for r in con.execute(
        "SELECT id,date_local,title,version,deleted FROM editor_lines "
        "WHERE id IN (" + ",".join("?" for _ in ids) + ")", ids
    )}
    problems = []
    for ident, before, title, after in CHANGES:
        original, destination = date.fromisoformat(before), date.fromisoformat(after)
        record = rows.get(ident)
        if original.weekday() != 0 or destination.weekday() != 4:
            problems.append(f"{ident}: unexpected weekday")
        if record is None or record["deleted"] or record["date_local"] != before or record["title"].strip().casefold() != title.casefold():
            problems.append(f"{ident}: source differs from inspected live data")
            continue
        duplicate = con.execute(
            "SELECT id FROM editor_lines WHERE deleted=0 AND id<>? AND date_local=? AND lower(title)=lower(?)",
            (ident, after, title)
        ).fetchone()
        if duplicate:
            problems.append(f"{ident}: duplicate on {after}")
        hidden = con.execute(
            "SELECT hidden FROM editor_days WHERE date_local=?", (after,)
        ).fetchone()
        if hidden and hidden["hidden"]:
            problems.append(f"{ident}: destination day {after} is hidden")
    return rows, problems


def apply_research_cycle():
    con = core.db()
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            return
        rows, problems = verify(con)
        if problems:
            # All-or-nothing: nothing is changed if a source or target is unsafe.
            print("RESEARCH_CYCLE_NOT_APPLIED " + json.dumps(problems, ensure_ascii=False), flush=True)
            return

        # A separate SQLite backup on the persistent Railway volume, before writes.
        backup_path = Path(str(core.DB_PATH) + ".before-research-20261127.bak")
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
        rows, problems = verify(con)
        if problems:
            con.rollback()
            print("RESEARCH_CYCLE_NOT_APPLIED " + json.dumps(problems, ensure_ascii=False), flush=True)
            return

        moved = []
        for ident, before, title, after in CHANGES:
            con.execute(
                "UPDATE editor_lines SET date_local=?,version=version+1 "
                "WHERE id=? AND deleted=0 AND date_local=?",
                (after, ident, before)
            )
            moved.append({
                "id": ident,
                "title": rows[ident]["title"],
                "from": before,
                "to": after,
                "old_version": rows[ident]["version"],
            })
        payload = json.dumps({"changes": moved}, ensure_ascii=False)
        con.execute(
            "INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)",
            ("school-calendar", "calendar.research_cycle_rescheduled", payload, core.now_iso())
        )
        con.execute(
            "INSERT INTO settings(key,value) VALUES(?,?)",
            (MARKER, payload)
        )
        con.commit()
        print("RESEARCH_CYCLE_APPLIED " + payload, flush=True)
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
