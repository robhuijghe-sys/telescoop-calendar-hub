"""One-time school calendar task: move January parent-meeting buffer reminder.

Keep other parent meetings and future parent-meeting cycles untouched.
"""
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import app.main as core

TARGET = "2027-01-04"
LAST_RELEVANT_DATE = "2027-01-24"  # day before the parent-meeting week
TITLE = "Buffers ingeven voor oudercontacten"
MARKER = "school_calendar_parent_meeting_buffers_2027_01_04_v1"


def related(title):
    words = (title or "").casefold()
    return "buffer" in words and "oudercontact" in words


def candidates(con):
    items = []
    for row in con.execute(
        "SELECT id,date_local,title FROM editor_lines "
        "WHERE deleted=0 AND date_local BETWEEN ? AND ? ORDER BY date_local,id",
        (TARGET, LAST_RELEVANT_DATE),
    ):
        if related(row["title"]):
            items.append({"kind": "line", "id": row["id"], "date": row["date_local"], "title": row["title"]})
    for row in con.execute(
        "SELECT id,title,start_at,end_at FROM events WHERE visible_in_embed=1"
    ):
        if not related(row["title"]):
            continue
        local = datetime.fromisoformat(row["start_at"]).astimezone(core.TZ).date().isoformat()
        if TARGET <= local <= LAST_RELEVANT_DATE:
            items.append({"kind": "event", "id": row["id"], "date": local, "title": row["title"],
                          "start": row["start_at"], "end": row["end_at"]})
    return sorted(items, key=lambda r: (r["date"] != TARGET, r["date"], r["kind"] != "line", r["id"]))


def apply_parent_meeting_buffers():
    # Avoid mutating an imported or temporary local database during tests.
    if not Path(core.DB_PATH).resolve().is_relative_to(Path("/data")):
        return
    if date.fromisoformat(TARGET).weekday() != 0:
        raise RuntimeError("The parent-meeting buffer task must fall on Monday")
    con = core.db()
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            return
        hidden = con.execute("SELECT hidden FROM editor_days WHERE date_local=?", (TARGET,)).fetchone()
        if hidden and hidden["hidden"]:
            print("PARENT_BUFFERS_NOT_APPLIED destination hidden", flush=True)
            return
        # A recoverable SQLite copy, preserved on the Railway volume.
        backup_path = Path(str(core.DB_PATH) + ".before-parent-buffers-20270104.bak")
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
        found = candidates(con)
        actions = []
        if found:
            keep = found[0]
            if keep["date"] != TARGET:
                if keep["kind"] == "line":
                    con.execute("UPDATE editor_lines SET date_local=?,version=version+1 WHERE id=?",
                                (TARGET, keep["id"]))
                else:
                    offset = (date.fromisoformat(TARGET) - date.fromisoformat(keep["date"])).days
                    new_start = (datetime.fromisoformat(keep["start"]) + timedelta(days=offset)).isoformat()
                    new_end = (datetime.fromisoformat(keep["end"]) + timedelta(days=offset)).isoformat()
                    con.execute("UPDATE events SET start_at=?,end_at=?,updated_at=? WHERE id=?",
                                (new_start, new_end, core.now_iso(), keep["id"]))
                actions.append({"operation": "moved", "kind": keep["kind"], "id": keep["id"],
                                "from": keep["date"], "to": TARGET, "title": keep["title"]})
            else:
                actions.append({"operation": "already-present", "kind": keep["kind"],
                                "id": keep["id"], "date": TARGET, "title": keep["title"]})
            for duplicate in found[1:]:
                if duplicate["kind"] == "line":
                    con.execute("UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?",
                                (duplicate["id"],))
                else:
                    con.execute("UPDATE events SET visible_in_embed=0,updated_at=? WHERE id=?",
                                (core.now_iso(), duplicate["id"]))
                actions.append({"operation": "removed-duplicate", "kind": duplicate["kind"],
                                "id": duplicate["id"], "date": duplicate["date"],
                                "title": duplicate["title"]})
        else:
            ident = con.execute(
                "INSERT INTO editor_lines(date_local,body_html,title,activity_type,whole_day) "
                "VALUES(?,?,?,?,?)", (TARGET, TITLE, TITLE, "secretariaat", 0),
            ).lastrowid
            actions.append({"operation": "added", "kind": "line", "id": ident,
                            "date": TARGET, "title": TITLE})
        payload = json.dumps({"changes": actions}, ensure_ascii=False)
        con.execute("INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)",
                    ("school-calendar", "calendar.parent_meeting_buffers_rescheduled", payload, core.now_iso()))
        con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (MARKER, payload))
        con.commit()
        current = candidates(con)
        if len(current) != 1 or current[0]["date"] != TARGET:
            print("PARENT_BUFFERS_POSTCHECK_FAILED " + json.dumps(current, ensure_ascii=False), flush=True)
        else:
            print("PARENT_BUFFERS_APPLIED " + payload, flush=True)
            print("PARENT_BUFFERS_VERIFIED " + json.dumps(current, ensure_ascii=False), flush=True)
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
