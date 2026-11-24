"""Prepare the 2027–2028 school calendar and release it on 24 June 2027.

Only newly added dates are seeded. Existing calendar records and subsequent
edits remain authoritative. The public renderer enforces the publication date;
the normal day editor and the year preview can already show the draft.
"""
import html
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastapi.responses import HTMLResponse

YEAR = "2027-2028"
START = date(2027, 9, 1)
END = date(2028, 8, 31)
LAST_SCHOOL_DAY = date(2028, 6, 30)
PUBLISH_ON = date(2027, 6, 24)
PUBLICATION_KEY = "calendar_publication_2027_2028"
MARKER = "school_calendar_2027_2028_prepared_v1"
WORKGROUP_MARKER = "school_calendar_2027_2028_workgroups_v1"
SOURCE = "https://www.vlaanderen.be/onderwijs-en-vorming/wat-mag-en-moet-op-school/schoolvakanties-vrije-dagen-en-afwezigheden/schoolvakanties"

HOLIDAYS = (
    (date(2027, 11, 1), date(2027, 11, 7), "Herfstvakantie"),
    (date(2027, 12, 27), date(2028, 1, 9), "Kerstvakantie"),
    (date(2028, 2, 28), date(2028, 3, 5), "Krokusvakantie"),
    (date(2028, 4, 3), date(2028, 4, 17), "Paasvakantie"),
    (date(2028, 7, 1), date(2028, 8, 31), "Zomervakantie"),
)
FREE_DAYS = {
    date(2027, 11, 11): "Wapenstilstand – vrije dag",
    date(2028, 5, 1): "Dag van de Arbeid – vrije dag",
    date(2028, 5, 25): "Hemelvaart – vrije dag",
    date(2028, 5, 26): "Brugdag na Hemelvaart – vrije dag",
    date(2028, 6, 5): "Pinkstermaandag – vrije dag",
}


def school_day(day):
    return (START <= day <= LAST_SCHOOL_DAY and day.weekday() < 5
            and day not in FREE_DAYS
            and not any(first <= day <= last for first, last, _ in HOLIDAYS))


def school_week(day):
    monday = day - timedelta(days=day.weekday())
    return any(school_day(monday + timedelta(days=i)) for i in range(5))


def shift_school_weeks(day, count):
    direction = 1 if count >= 0 else -1
    for _ in range(abs(count)):
        day += timedelta(weeks=direction)
        while not school_week(day):
            if day < START - timedelta(days=6) or day > LAST_SCHOOL_DAY + timedelta(days=6):
                raise ValueError("The requested school-week offset leaves this school year")
            day += timedelta(weeks=direction)
    return day


def meeting_dates():
    # First Tuesday of the school year, then four teaching-week intervals.
    day = START + timedelta(days=(1 - START.weekday()) % 7)
    meetings, elapsed = [], 0
    while day <= LAST_SCHOOL_DAY:
        if school_week(day):
            if not meetings or elapsed == 4:
                if not school_day(day):
                    raise ValueError("A team meeting falls on a non-school Tuesday")
                meetings.append(day)
                elapsed = 0
            elapsed += 1
        day += timedelta(weeks=1)
    return meetings


def build_plan():
    meetings = meeting_dates()
    cycles = []
    for number, first in enumerate((date(2027, 11, 12), date(2028, 2, 4)), 1):
        sessions = [shift_school_weeks(first, i) for i in range(3)]
        deadline = shift_school_weeks(first, -4)
        collect = deadline - timedelta(days=deadline.weekday())
        agenda = max(meeting for meeting in meetings if meeting < collect)
        if not all(school_day(day) for day in sessions + [deadline, collect]):
            raise ValueError("Research planning falls on a non-school day")
        cycles.append({"number": number, "sessions": [d.isoformat() for d in sessions],
                       "collect": collect.isoformat(), "deadline": deadline.isoformat(),
                       "agenda": agenda.isoformat()})
    return {"school_year": YEAR, "start": START.isoformat(), "end": END.isoformat(),
            "publish_on": PUBLISH_ON.isoformat(), "timezone": "Europe/Brussels",
            "holiday_source": SOURCE, "meetings": [d.isoformat() for d in meetings],
            "cycles": cycles}


def workgroup_plan(plan):
    maths = []
    for value in plan["meetings"]:
        try:
            day = shift_school_weeks(date.fromisoformat(value), 2)
        except ValueError:
            # Two teaching weeks after the final June meeting is next year.
            continue
        if day <= LAST_SCHOOL_DAY:
            if not school_day(day) or day.weekday() != 1:
                raise ValueError("A maths workgroup falls on a non-school Tuesday")
            maths.append(day.isoformat())
    mondays = []
    day = START + timedelta(days=(-START.weekday()) % 7)
    while day <= LAST_SCHOOL_DAY:
        if school_day(day):
            topic = "WO" if len(mondays) % 2 == 0 else "kleuters"
            mondays.append({"date": day.isoformat(), "topic": topic})
        day += timedelta(weeks=1)
    return {"time": "16u45 - 17u30", "maths": maths, "mondays": mondays}


def short_date(value):
    day = date.fromisoformat(value)
    months = ("", "januari", "februari", "maart", "april", "mei", "juni",
              "juli", "augustus", "september", "oktober", "november", "december")
    return f"{day.day} {months[day.month]} {day.year}"


def planned_lines(plan):
    rows = []

    def add(day, title, kind="algemeen"):
        rows.append((day.isoformat() if isinstance(day, date) else day, title, kind))

    add(START, "Start schooljaar 2027–2028")
    add(LAST_SCHOOL_DAY, "Laatste schooldag van schooljaar 2027–2028")
    for first, last, name in HOLIDAYS:
        add(first, f"{name.upper()} – tot en met {short_date(last.isoformat())}")
    for day, title in sorted(FREE_DAYS.items()):
        add(day, title)
    for day in plan["meetings"]:
        add(day, "15u45 - 16u30: Teamvergadering", "personeel")
        for cycle in plan["cycles"]:
            if cycle["agenda"] == day:
                number = cycle["number"]
                add(day, f"• Start onderzoek: vragen verzamelen (cyclus {number}).", "personeel")
                add(day, f"• Vragen verzamelen vanaf {short_date(cycle['collect'])}; "
                    f"doorgeven uiterlijk {short_date(cycle['deadline'])}. "
                    "Onderzoeksreeks van drie weken: één namiddag en twee keer één uur.", "personeel")
    for cycle in plan["cycles"]:
        number = cycle["number"]
        add(cycle["collect"], f"Onderzoek WO – onderzoeksvragen verzamelen (cyclus {number}). "
            f"Geef de vragen uiterlijk {short_date(cycle['deadline'])} door.", "secretariaat")
        add(cycle["deadline"], f"Onderzoek WO – onderzoeksvragen doorgeven (cyclus {number}): "
            f"vandaag de deadline, vier schoolweken vóór de start op {short_date(cycle['sessions'][0])}.",
            "secretariaat")
        labels = ("NM: Onderzoek WO – cyclus {n}, sessie 1: start en uitstap. De hele middag is voorzien.",
                  "Onderzoek WO – cyclus {n}, sessie 2: verwerken en verder onderzoeken. Duur: één uur.",
                  "Onderzoek WO – cyclus {n}, sessie 3: afronden en bevindingen delen. Duur: één uur.")
        for day, title in zip(cycle["sessions"], labels):
            add(day, title.format(n=number))
    return sorted(rows, key=lambda row: row[0])


def seed_school_year(con, core):
    """Atomic, idempotent insertion; never re-create edited or deleted entries."""
    con.execute("BEGIN IMMEDIATE")
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            con.rollback()
            return False
        plan = build_plan()
        additions = planned_lines(plan)
        hidden = {row[0] for row in con.execute("SELECT date_local FROM editor_days WHERE hidden=1")}
        if any(day in hidden for day, _, _ in additions):
            raise RuntimeError("A planned date is explicitly hidden; the draft was not changed")
        # The visibility rule is saved in the same transaction as the entries.
        existing = con.execute("SELECT value FROM settings WHERE key=?", (PUBLICATION_KEY,)).fetchone()
        if existing:
            raise RuntimeError("A publication plan already exists; preserve it for review")
        con.execute("INSERT INTO settings(key,value) VALUES(?,?)",
                    (PUBLICATION_KEY, json.dumps(plan, ensure_ascii=False)))
        added_ids = []
        for day, title, kind in additions:
            if con.execute("SELECT 1 FROM editor_lines WHERE date_local=? AND title=? AND deleted=0",
                           (day, title)).fetchone():
                continue
            ident = con.execute("INSERT INTO editor_lines(date_local,body_html,title,activity_type,whole_day) "
                                "VALUES(?,?,?,?,0)", (day, html.escape(title), title, kind)).lastrowid
            added_ids.append(ident)
        payload = json.dumps({"plan": plan, "added_line_ids": added_ids}, ensure_ascii=False)
        con.execute("INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)",
                    ("school-calendar", "calendar.school_year_prepared", payload, core.now_iso()))
        con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (MARKER, payload))
        con.commit()
        return True
    except Exception:
        con.rollback()
        raise


def prepare_school_year(core):
    # A deployment must not seed unrelated temporary databases used by tests.
    if not Path(core.DB_PATH).resolve().is_relative_to(Path("/data")):
        return
    con = core.db()
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (MARKER,)).fetchone():
            return
        backup_path = Path(str(core.DB_PATH) + ".before-school-year-2027-2028.bak")
        if not backup_path.exists():
            backup = sqlite3.connect(str(backup_path))
            try:
                con.backup(backup)
            finally:
                backup.close()
        if seed_school_year(con, core):
            print("SCHOOL_YEAR_2027_2028_PREPARED publish_on=2027-06-24", flush=True)
    finally:
        con.close()


def seed_workgroups(con, core):
    """Append workgroups without reapplying or overwriting the first year plan."""
    con.execute("BEGIN IMMEDIATE")
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (WORKGROUP_MARKER,)).fetchone():
            con.rollback()
            return False
        stored = con.execute("SELECT value FROM settings WHERE key=?", (PUBLICATION_KEY,)).fetchone()
        if not stored:
            raise RuntimeError("Prepare the school year before adding workgroups")
        plan = json.loads(stored[0])
        groups = workgroup_plan(plan)
        additions = [(day, groups['time'] + ": Vakgroep wiskunde") for day in groups['maths']]
        additions += [(group['date'], groups['time'] + ": Vakgroep " + group['topic'])
                      for group in groups['mondays']]
        hidden = {row[0] for row in con.execute("SELECT date_local FROM editor_days WHERE hidden=1")}
        if any(day in hidden for day, _ in additions):
            raise RuntimeError("A planned workgroup date is explicitly hidden; nothing was changed")
        ids = []
        for day, title in additions:
            if con.execute("SELECT 1 FROM editor_lines WHERE date_local=? AND title=? AND deleted=0",
                           (day, title)).fetchone():
                continue
            ids.append(con.execute("INSERT INTO editor_lines(date_local,body_html,title,activity_type,whole_day) "
                                   "VALUES(?,?,?,'personeel',0)",
                                   (day, html.escape(title), title)).lastrowid)
        plan['workgroups'] = groups
        con.execute("UPDATE settings SET value=? WHERE key=?",
                    (json.dumps(plan, ensure_ascii=False), PUBLICATION_KEY))
        payload = json.dumps({"workgroups": groups, "added_line_ids": ids}, ensure_ascii=False)
        con.execute("INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)",
                    ("school-calendar", "calendar.school_year_workgroups_prepared", payload, core.now_iso()))
        con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (WORKGROUP_MARKER, payload))
        con.commit()
        return True
    except Exception:
        con.rollback()
        raise


def prepare_workgroups(core):
    if not Path(core.DB_PATH).resolve().is_relative_to(Path("/data")):
        return
    con = core.db()
    try:
        if con.execute("SELECT 1 FROM settings WHERE key=?", (WORKGROUP_MARKER,)).fetchone():
            return
        backup_path = Path(str(core.DB_PATH) + ".before-workgroups-2027-2028.bak")
        if not backup_path.exists():
            backup = sqlite3.connect(str(backup_path))
            try:
                con.backup(backup)
            finally:
                backup.close()
        if seed_workgroups(con, core):
            print("SCHOOL_YEAR_2027_2028_WORKGROUPS_PREPARED", flush=True)
    finally:
        con.close()


def publication_plans(settings):
    plans = []
    for key, value in settings.items():
        if not key.startswith("calendar_publication_"):
            continue
        plan = json.loads(value)
        first, last, publish = (date.fromisoformat(plan[k]) for k in ("start", "end", "publish_on"))
        if first > last:
            raise ValueError("Invalid school-year publication range")
        plans.append((first, last, publish))
    return plans


def public_date_visible(day, today, settings):
    return not any(first <= day <= last and today < publish
                   for first, last, publish in publication_plans(settings))


def public_calendar_end(today, settings, default_end):
    return max([default_end] + [(last.year, last.month)
               for first, last, publish in publication_plans(settings)
               if publish <= today <= last])


def register_school_year_preview(s):
    @s.app.get("/kalender-schooljaar/2027-2028")
    def preview():
        from app.day_cards import render_calendar, scoped_css, month_header
        con = s.core.db()
        try:
            stored = con.execute("SELECT value FROM settings WHERE key=?", (PUBLICATION_KEY,)).fetchone()
            if not stored:
                return HTMLResponse(s.page("Schooljaar 2027–2028", "<p>Deze kalender is nog niet voorbereid.</p>"), status_code=404)
            plan = json.loads(stored[0])
            dates = sorted({row['date_local'] for row in con.execute(
                "SELECT date_local FROM editor_lines WHERE deleted=0 AND date_local BETWEEN ? AND ?",
                (plan["start"], plan["end"]))})
            dates = sorted(set(dates) | {s.datetime.fromisoformat(row['start_at']).astimezone(s.core.TZ).date().isoformat()
                for row in con.execute("SELECT start_at FROM events WHERE visible_in_embed=1")
                if plan["start"] <= s.datetime.fromisoformat(row['start_at']).astimezone(s.core.TZ).date().isoformat() <= plan["end"]})
            cards = render_calendar(s, hide_past=False, dates=dates, cards_only=True, connection=con)
        finally:
            con.close()
        today = s.datetime.now(s.core.TZ).date()
        status = ("Gepubliceerd in de schoolkalender." if today.isoformat() >= plan["publish_on"] else
                  "Concept – zichtbaar in de schoolkalender vanaf " + short_date(plan["publish_on"]) + ".")
        body = ("<section class=\"card\"><h2>Schooljaar 2027–2028</h2>"
                f"<p role=\"status\">{html.escape(status)}</p>"
                "<p>Teamvergadering op dinsdag, telkens na vier schoolweken. Volledige vakantieweken tellen niet mee. "
                "Ook de deadlines voor onderzoeksvragen liggen vier schoolweken vóór de start. "
                "Per onderzoeksreeks: één namiddag en twee keer één uur.</p>"
                "<div style=\"overflow-x:auto\"><table class=\"year-summary\"><thead><tr><th>Cyclus</th><th>Vragen verzamelen</th>"
                "<th>Vragen doorgeven</th><th>Onderzoeksmomenten</th></tr></thead><tbody>")
        for cycle in plan["cycles"]:
            body += (f"<tr><td>{cycle['number']}</td><td>{short_date(cycle['collect'])}</td>"
                     f"<td>{short_date(cycle['deadline'])}</td><td>"
                     + "<br>".join(short_date(day) for day in cycle["sessions"]) + "</td></tr>")
        body += "</tbody></table></div>"
        if plan.get('workgroups'):
            body += ("<p><strong>Vakgroepen: 16u45–17u30.</strong> Wiskunde op dinsdag, twee schoolweken na "
                     "elke teamvergadering. Op de beschikbare maandagen wisselen WO en kleuters elkaar af, "
                     "met WO als eerste. Op vrije maandagen is er geen vakgroep; de afwisseling loopt verder "
                     "op de volgende beschikbare maandag.</p>")
        body += ("<p><a href=\"" + SOURCE + "\" target=\"_blank\" rel=\"noopener noreferrer\">"
                 "Officiële schoolvakanties</a></p></section><div class=\"calendar-preview\">")
        month = None
        for day, card in sorted(cards.items()):
            if day[:7] != month:
                if month is not None:
                    body += "</section>"
                month = day[:7]
                body += '<section class="month-card">' + month_header(int(day[5:7]))
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(card, "html.parser")
            heading = soup.select_one(".day-header")
            edit = soup.new_tag("a", href="/kalender-dag/" + day,
                                attrs={"class": "btn alt", "aria-label": "Bewerk " + short_date(day)})
            edit.string = "Bewerken"
            heading.append(edit)
            body += str(soup)
        body += ("</section>" if month is not None else "") + "</div>"
        summary_css = (".year-summary{width:100%;min-width:560px;border-collapse:collapse;font-size:14px}"
                       ".year-summary th,.year-summary td{padding:12px 10px;text-align:left;vertical-align:top;"
                       "border-bottom:1px solid #dce2ee;line-height:1.45}"
                       ".year-summary th{font-weight:700;color:#232563}"
                       ".calendar-preview .month-head .season{background:none;border:0;padding:0}")
        document = s.page("Schooljaar 2027–2028", body).replace(
            "</style>", scoped_css(".calendar-preview") + summary_css + "</style>", 1)
        return HTMLResponse(document)
