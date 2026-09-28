"""One-time, additive calendar data request approved by Rob on 2026-09-28."""
import html
import json
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TITLE = 'stage Imane in K0K1 8u30 tot 12u40'
KEY = 'calendar.stage_imane.2026_2027.v1'
TZ = ZoneInfo('Europe/Brussels')
FIRST, LAST = date(2026, 10, 1), date(2027, 6, 30)
HOLIDAYS = {
    '2026-11-05': 'herfstvakantie',
    '2026-12-24': 'kerstvakantie',
    '2026-12-31': 'kerstvakantie',
    '2027-02-11': 'krokusvakantie',
    '2027-04-01': 'paasvakantie',
    '2027-04-08': 'paasvakantie',
    '2027-05-06': 'Hemelvaart',
}
CLOSURE = re.compile(r'\bstudiedag\b|\bschoolvrij\w*\b|\b(?:facultatieve?\s+)?vrije\s+(?:school)?dag\b|\bgeen\s+(?:school|lessen)\b|\bschool\s+(?:is\s+)?gesloten\b|\b(?:herfst|kerst|krokus|paas|zomer)vakantie\b|\bhemelvaart\b|\bwapenstilstand\b|\bpinkstermaandag\b', re.I)
IMANE = re.compile(r'\bimane\b', re.I)
STAGE = re.compile(r'\bstage\w*\b|\bstagiair\w*\b', re.I)


def _thursdays():
    return [(FIRST + timedelta(days=7 * n)).isoformat()
            for n in range(((LAST - FIRST).days // 7) + 1)]


def _stored_calendar(con):
    rows = [dict(r) for r in con.execute('SELECT * FROM editor_lines ORDER BY id')]
    events = [dict(r) for r in con.execute('SELECT * FROM events ORDER BY id')]
    days = [dict(r) for r in con.execute('SELECT * FROM editor_days ORDER BY date_local')]
    links = [dict(r) for r in con.execute('SELECT * FROM editor_links ORDER BY id')]
    return rows, events, days, links


def _same_stage(text):
    return bool(IMANE.search(text) and STAGE.search(text)
                and re.search(r'k0\s*[/+&-]?\s*k?1', text, re.I)
                and re.search(r'\b0?8[u:.]30\b', text, re.I)
                and re.search(r'\b12[u:.]40\b', text, re.I))


def apply_imane_request(core):
    """Read current data, add only missing stages atomically, then read back."""
    con = core.db()
    try:
        old = con.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
        if old:
            return json.loads(old[0])  # Never undo subsequent manual edits.
        backup_path = str(core.DB_PATH) + '.before-imane-20260928.bak'
        if not Path(backup_path).exists():
            backup = sqlite3.connect(backup_path)
            try:
                con.backup(backup)
            finally:
                backup.close()
        con.execute('BEGIN IMMEDIATE')
        # Recheck under the write lock, in case another instance applied it.
        old = con.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
        if old:
            con.rollback()
            return json.loads(old[0])
        before = _stored_calendar(con)
        rows, events, days, links = before
        if not rows:
            raise RuntimeError('Existing school calendar is empty; no stages added.')
        candidates = _thursdays()
        excluded = {d: reason for d, reason in HOLIDAYS.items()}
        existing = {d: [] for d in candidates}
        closure_evidence = []
        for r in rows:
            d, text = r['date_local'], r['title']
            if r['deleted'] or d not in existing:
                continue
            if CLOSURE.search(text):
                excluded[d] = text
                closure_evidence.append({'date': d, 'title': text})
            if IMANE.search(text) and STAGE.search(text):
                existing[d].append(('basis:' + str(r['id']), _same_stage(text)))
        for r in days:
            if r['hidden'] and r['date_local'] in existing:
                excluded[r['date_local']] = 'day explicitly hidden in current calendar'
        for r in events:
            if not r['visible_in_embed']:
                continue
            start = datetime.fromisoformat(r['start_at']).astimezone(TZ)
            end = datetime.fromisoformat(r['end_at']).astimezone(TZ)
            text = ' '.join(str(r.get(k) or '') for k in ('title', 'description', 'location', 'audience'))
            if CLOSURE.search(r['title']):
                for d in candidates:
                    morning = datetime.combine(date.fromisoformat(d), time(8, 30), TZ)
                    noon = datetime.combine(date.fromisoformat(d), time(12, 40), TZ)
                    if start < noon and end > morning:
                        excluded[d] = r['title']
                        closure_evidence.append({'date': d, 'title': r['title']})
            d = start.date().isoformat()
            if d in existing and IMANE.search(text) and STAGE.search(text):
                correct = (start.strftime('%H:%M') == '08:30' and end.strftime('%H:%M') == '12:40'
                           and start.date() == end.date() and not r['all_day']
                           and bool(re.search(r'k0\s*[/+&-]?\s*k?1', text, re.I)))
                existing[d].append(('event:' + str(r['id']), correct))
        conflicts = {d: entries for d, entries in existing.items()
                     if entries and (d in excluded or len(entries) != 1 or not entries[0][1])}
        if conflicts:
            raise RuntimeError('Existing Imane stages need review; nothing added: ' + json.dumps(conflicts))
        dates = [d for d in candidates if d not in excluded]
        new_ids, already = {}, []
        for d in dates:
            if existing[d]:
                already.append(d)
                continue
            ident = con.execute('INSERT INTO editor_lines(date_local,body_html,title) VALUES(?,?,?)',
                                (d, '<span style="color:#2F2926">' + html.escape(TITLE) + '</span>', TITLE)).lastrowid
            new_ids[d] = ident
        after = _stored_calendar(con)
        if [r for r in after[0] if r['id'] not in set(new_ids.values())] != before[0] or after[1:] != before[1:]:
            raise RuntimeError('Unexpected change to existing calendar; transaction rolled back.')
        for d, ident in new_ids.items():
            saved = con.execute('SELECT * FROM editor_lines WHERE id=?', (ident,)).fetchone()
            if saved['date_local'] != d or saved['title'] != TITLE or saved['deleted']:
                raise RuntimeError('Stage validation failed; transaction rolled back.')
        result = {'request': TITLE, 'timezone': 'Europe/Brussels', 'dates': dates,
                  'added': len(new_ids), 'already_present': already, 'line_ids': new_ids,
                  'excluded': excluded, 'local_closure_evidence': closure_evidence,
                  'other_calendar_data_unchanged': True, 'created_at': core.now_iso()}
        payload = json.dumps(result, ensure_ascii=False)
        con.execute('INSERT INTO settings(key,value) VALUES(?,?)', (KEY, payload))
        con.execute('INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)',
                    ('rob.huijghe@detelescoop.be', 'calendar.stage_imane_added', payload, core.now_iso()))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    check = core.db()
    try:
        stored = json.loads(check.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()[0])
        for d, ident in stored['line_ids'].items():
            row = check.execute('SELECT date_local,title,deleted FROM editor_lines WHERE id=?', (ident,)).fetchone()
            if tuple(row) != (d, TITLE, 0):
                raise RuntimeError('Post-commit read-back differs from saved request.')
        result['persistent_readback_verified'] = True
    finally:
        check.close()
    print('IMANE_CALENDAR_SAVED ' + json.dumps(result, ensure_ascii=False), flush=True)
    return result


def verify_imane_render(core, result):
    """Independently verify desktop and mobile views after persistent readback."""
    if not result.get('persistent_readback_verified'):
        return  # This request was already applied; honor later manual edits.
    from bs4 import BeautifulSoup
    from app.calendar_snapshot import render_snapshot_calendar
    con = core.db()
    try:
        hidden = {r[0] for r in con.execute('SELECT date_local FROM editor_days WHERE hidden=1')}
    finally:
        con.close()
    soup = BeautifulSoup(render_snapshot_calendar(hide_past=False, hidden_dates=hidden), 'html.parser')
    expected = {d: 1 for d in result['dates']}
    for name, selector in [('desktop', '.desktop-calendar [data-calendar-date]'), ('mobile', '.mobile-day[data-calendar-date]')]:
        found = {}
        for day in soup.select(selector):
            d = day['data-calendar-date']
            if d not in _thursdays():
                continue
            matches = [el for el in day.select('.base-content,.live-addition')
                       if IMANE.search(el.get_text(' ', strip=True)) and STAGE.search(el.get_text(' ', strip=True))]
            if matches:
                found[d] = len(matches)
        result[name + '_verified'] = found == expected
        result[name + '_stage_count'] = sum(found.values())
        if found != expected:
            result[name + '_mismatches'] = {d: found.get(d, 0) for d in set(found) | set(expected)
                                            if found.get(d, 0) != expected.get(d, 0)}
    receipt = Path(str(core.DB_PATH) + '.imane-20260928-result.json')
    temporary = receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(receipt)
    print('IMANE_CALENDAR_RENDERED ' + json.dumps(result, ensure_ascii=False), flush=True)
