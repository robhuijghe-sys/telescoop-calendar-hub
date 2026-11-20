"""One-time, recoverable change to the public school calendar for the strike.

Monday 23 November 2026: no other entries; school closed.
Move the kindergarten team meeting and all three agenda items to 30 November.
The original event/line IDs and formatting are retained when moved.
"""
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import app.main as core

SOURCE = "2026-11-23"
DEST = "2026-11-30"
CLOSURE = "School gesloten wegens staking"
MARKER = "school_calendar_strike_2026_11_23_v1"


def _is_meeting(title):
    value = (title or "").casefold()
    return "vakgroep kleuter" in value or "kleuterteam" in value


def _is_agenda(title):
    value = re.sub(r"^\s*[•*·-]+\s*", "", (title or "").casefold()).strip()
    return (
        value == "bakjestijd"
        or ("thema" in value and "voorkennis" in value)
        or "woordenschatonderwijs (taelman)" in value
    )


def _events_on(con, day):
    return [
        dict(r) for r in con.execute(
            "SELECT * FROM events WHERE visible_in_embed=1 ORDER BY start_at,id"
        )
        if datetime.fromisoformat(r["start_at"]).astimezone(core.TZ).date().isoformat() == day
    ]


def apply_strike_nov23():
    # Only change the persistent production calendar, not temporary test data.
    if not Path(core.DB_PATH).resolve().is_relative_to(Path("/data")):
        return
    if date.fromisoformat(SOURCE).weekday() != 0 or date.fromisoformat(DEST).weekday() != 0:
        raise RuntimeError("Expected two consecutive Mondays")
    if (date.fromisoformat(DEST) - date.fromisoformat(SOURCE)).days != 7:
        raise RuntimeError("The kindergarten team must move exactly one week")
    con = core.db()
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            return

        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            con.rollback()
            return

        current = [dict(r) for r in con.execute(
            "SELECT * FROM editor_lines WHERE date_local=? AND deleted=0 ORDER BY id",
            (SOURCE,)
        )]
        events = _events_on(con, SOURCE)
        move_lines = [r for r in current if _is_meeting(r["title"]) or _is_agenda(r["title"])]
        move_events = [r for r in events if _is_meeting(r["title"])]
        meeting_count = sum(_is_meeting(r["title"]) for r in current) + len(move_events)
        meeting_content = (
            " ".join((r["title"] or "") + " " + (r["body_html"] or "") for r in move_lines)
            + " ".join((r["title"] or "") + " " + (r["description"] or "") for r in move_events)
        ).casefold()
        if meeting_count != 1 or not all(
            keyword in meeting_content
            for keyword in ("bakjestijd", "voorkennis", "woordenschatonderwijs")
        ):
            con.rollback()
            print("STRIKE_20261123_ABORTED meeting or agenda changed: " + json.dumps({
                "meeting_count": meeting_count,
                "source_titles": [r["title"] for r in current],
                "source_event_titles": [r["title"] for r in events],
            }, ensure_ascii=False), flush=True)
            return

        dest_hidden = con.execute(
            "SELECT hidden FROM editor_days WHERE date_local=?", (DEST,)
        ).fetchone()
        dest_lines = list(con.execute(
            "SELECT title FROM editor_lines WHERE date_local=? AND deleted=0", (DEST,)
        ))
        dest_events = _events_on(con, DEST)
        if (dest_hidden and dest_hidden["hidden"]) or any(
            _is_meeting(r["title"]) for r in dest_lines + dest_events
        ):
            con.rollback()
            print("STRIKE_20261123_ABORTED destination hidden or meeting already booked", flush=True)
            return

        # Make a SQLite-consistent, recoverable copy before changing anything.
        backup_path = Path(str(core.DB_PATH) + ".before-strike-20261123.bak")
        con.rollback()
        if not backup_path.exists():
            backup = sqlite3.connect(str(backup_path))
            try:
                con.backup(backup)
            finally:
                backup.close()
        con.execute("BEGIN IMMEDIATE")

        # Recheck for concurrent edits after releasing the transaction for backup.
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            con.rollback()
            return
        current2 = [dict(r) for r in con.execute(
            "SELECT * FROM editor_lines WHERE date_local=? AND deleted=0 ORDER BY id", (SOURCE,)
        )]
        events2 = _events_on(con, SOURCE)
        dest2 = list(con.execute(
            "SELECT title FROM editor_lines WHERE date_local=? AND deleted=0", (DEST,)
        ))
        if ([r["id"] for r in current2] != [r["id"] for r in current]
            or [r["id"] for r in events2] != [r["id"] for r in events]
            or [r["title"] for r in dest2] != [r["title"] for r in dest_lines]):
            con.rollback()
            print("STRIKE_20261123_ABORTED concurrent edit detected", flush=True)
            return

        ids_to_move = [r["id"] for r in move_lines]
        event_ids_to_move = [r["id"] for r in move_events]
        for item in move_lines:
            con.execute(
                "UPDATE editor_lines SET date_local=?,version=version+1 WHERE id=? AND deleted=0",
                (DEST, item["id"])
            )
        for item in move_events:
            updated_start = (datetime.fromisoformat(item["start_at"]) + timedelta(days=7)).isoformat()
            updated_end = (datetime.fromisoformat(item["end_at"]) + timedelta(days=7)).isoformat()
            con.execute(
                "UPDATE events SET start_at=?,end_at=?,updated_at=? WHERE id=?",
                (updated_start, updated_end, core.now_iso(), item["id"])
            )

        # Remove all other information on strike day, including absences, stages,
        # the LIST period, care meetings and any structured calendar events.
        cleared_lines = [r for r in current if r["id"] not in ids_to_move]
        cleared_events = [r for r in events if r["id"] not in event_ids_to_move]
        con.execute(
            "UPDATE editor_lines SET deleted=1,version=version+1 "
            "WHERE date_local=? AND deleted=0", (SOURCE,)
        )
        for item in cleared_events:
            con.execute(
                "UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?",
                (core.now_iso(), item["id"])
            )
        # Ensure the day remains visible, even if it was hidden by an old edit.
        con.execute("DELETE FROM editor_days WHERE date_local=?", (SOURCE,))
        closure_id = con.execute(
            "INSERT INTO editor_lines(date_local,body_html,title,activity_type,whole_day) "
            "VALUES(?,?,?,?,?)",
            (SOURCE, CLOSURE, CLOSURE, "waarschuwing", 1)
        ).lastrowid

        after_source = list(con.execute(
            "SELECT title FROM editor_lines WHERE date_local=? AND deleted=0", (SOURCE,)
        ))
        after_events = _events_on(con, SOURCE)
        moved_present = {
            r["id"] for r in con.execute(
                "SELECT id FROM editor_lines WHERE date_local=? AND deleted=0", (DEST,)
            )
        }
        moved_event_present = {r["id"] for r in _events_on(con, DEST)}
        if ([r["title"] for r in after_source] != [CLOSURE] or after_events
            or not set(ids_to_move).issubset(moved_present)
            or not set(event_ids_to_move).issubset(moved_event_present)):
            raise RuntimeError("Strike calendar post-check failed before commit")

        report = {
            "closed_date": SOURCE, "closure_id": closure_id,
            "moved_to": DEST,
            "moved_lines": [{"id": r["id"], "title": r["title"]} for r in move_lines],
            "moved_events": [{"id": r["id"], "title": r["title"]} for r in move_events],
            "cleared_lines": [{"id": r["id"], "title": r["title"]} for r in cleared_lines],
            "cleared_events": [{"id": r["id"], "title": r["title"]} for r in cleared_events],
        }
        payload = json.dumps(report, ensure_ascii=False)
        con.execute(
            "INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)",
            ("school-calendar", "calendar.strike_nov23", payload, core.now_iso())
        )
        con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (MARKER, payload))
        con.commit()
        print("STRIKE_20261123_APPLIED " + payload, flush=True)
        print("STRIKE_20261123_VERIFIED only closure on 23 Nov; "
              "kindergarten meeting and agenda moved to 30 Nov", flush=True)
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
