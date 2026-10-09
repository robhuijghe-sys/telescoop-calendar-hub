"""Canonical labels using only known hours, groups and places."""
import re
from bs4 import BeautifulSoup, NavigableString
from app.rich_editor import fragment_text, reshape_html

STAGE = re.compile(r'\b(?:stages?|stagiair\w*)\b', re.I)
CLOCK = r'(?:[01]?\d|2[0-3])(?:[.:h][0-5]\d(?:u)?|\s*uur|u(?:[0-5]\d)?)'
LESSON = r'\d+(?:ste|de)(?:\s*(?:en|[-–])\s*\d+(?:ste|de))?\s+(?:les)?uur'
MOMENT = re.compile(r'(?<![\w,.])(?:' + LESSON + r'|' + CLOCK + r'(?:\s*(?:tot|[-–—])\s*' + CLOCK + r')?|VM|NM|voormiddag|namiddag|hele dag)(?!\w)', re.I)
GROUP_ATOM = r'(?:K0K1|L5L6|GR[123]|[KL][0-6]|[123](?:ste|de) graad|jongste kleuters|oudste kleuters)'
GROUP = re.compile(r'(?<!\w)' + GROUP_ATOM + r'(?:\s*(?:\+|&|/|,|en|tot en met)\s*' + GROUP_ATOM + r')*(?!\w)', re.I)


def moment_label(value):
    value = value.strip()
    if re.search(r'\d+(?:ste|de).*uur', value, re.I):
        return re.sub(r'\b(?:les)?uur\b', 'lesuur', value, flags=re.I)
    if value.lower() in ('vm', 'voormiddag', 'nm', 'namiddag', 'hele dag'):
        return {'vm':'VM','voormiddag':'VM','nm':'NM','namiddag':'NM','hele dag':'hele dag'}[value.lower()]
    def clock(m):
        parts = re.findall(r'\d+', m[0])
        return f'{int(parts[0])}u{int(parts[1]) if len(parts)>1 else 0:02d}'
    return re.sub(r'\s*(?:tot|[-–—])\s*', ' - ', re.sub(CLOCK, clock, value, flags=re.I))


def normalize_text(value, moment='', location='', outing=False):
    # Established stage labels retain their name-first notation and extra duties.
    if STAGE.search(value):
        return value
    paired = re.fullmatch(r'(.+?)\s+(' + GROUP_ATOM + r')\s+(' + CLOCK + r')\s+en\s+(' + GROUP_ATOM + r')\s+(' + CLOCK + r')\.?', value.strip(), re.I)
    if paired:
        activity, first, start, second, end = paired.groups()
        return normalize_text(activity + ' ' + first, moment=moment_label(start)) + '\n' + normalize_text(activity + ' ' + second, moment=moment_label(end))
    if '\n' in value:
        return '\n'.join(normalize_text(line) for line in value.split('\n'))
    text = value.strip()
    original_text = text
    # Agenda bullets, durations and class-only slots are not separate activities.
    if not text or re.match(r'^[*•]\s', text):
        return value
    if re.fullmatch(GROUP_ATOM + r'(?:\s*[+&/]\s*' + GROUP_ATOM + r')*', text, re.I):
        return value
    stage = bool(STAGE.search(text))
    found = MOMENT.search(text)
    if found:
        before, after = text[:found.start()], text[found.end():]
        # Never turn a duration or deadline into the event's start time.
        duration = re.search(r'\d+\s*uur$', found[0], re.I) and re.match(r'\s*(?:in totaal|per |duur)', after, re.I)
        incidental = re.search(r'\b(?:tegen|vanaf|tot|na|voor|toezicht)\s*$', before, re.I)
        movable = not before.strip() or before.rstrip().endswith((':', '(', ',')) or re.match(r'\s*:\s', after) or not after.strip(' .:') or re.search(r'\bom\s*$', before, re.I) or GROUP.fullmatch(before.strip())
        if stage and re.search(r'\bvan\s*$', before, re.I):
            movable = True
            before = re.sub(r'\bvan\s*$', '', before, flags=re.I)
        if movable and not duration and not incidental:
            if not moment:
                moment = moment_label(found[0])
            if before.endswith('(') and after.startswith(')'):
                before, after = before[:-1], after[1:]
            before = re.sub(r'\bom\s*$', '', before, flags=re.I)
            tail = after.lstrip(' ,:.-–—')
            if stage and re.match(r'\s*[-–—]', after):
                tail = '– ' + tail
            text = (before.rstrip(' ,:.-') + ' ' + tail).strip()
    group = GROUP.search(text)
    class_label = ''
    if group:
        # A class introduced only as a location stays in the activity text.
        before_group = text[:group.start()]
        contextual = before_group.count('(') > before_group.count(')') and not before_group.endswith('(')
        absence = re.search(r'\b(?:afwezig|afw)\b', text, re.I)
        if not contextual and not absence and not re.search(r'\b(?:in|naar|vervangt|i\.p\.v\.)\s*$', before_group, re.I) and (stage or not re.search(r'\bbij\s*$', before_group, re.I)):
            class_label = re.sub(GROUP_ATOM, lambda m: {'1ste graad':'GR1','1de graad':'GR1','2de graad':'GR2','3de graad':'GR3'}.get(m[0].lower(), m[0].upper() if re.match(r'[KL]|GR',m[0],re.I) else m[0]), re.sub(r'\s+', ' ', group[0]), flags=re.I)
            before, after = text[:group.start()], text[group.end():]
            if stage:
                before = re.sub(r'\bbij\s*$', '', before, flags=re.I)
            if before.endswith('(') and after.startswith(')'):
                before, after = before[:-1], after[1:]
            tail = after.lstrip(' ,:.-–—')
            if stage and re.match(r'\s*[-–—]', after):
                tail = '– ' + tail
            text = (before.rstrip(' ,:.-') + ' ' + tail).strip()
    text = text.strip(' ,:-–—')
    def note_moment(m):
        if re.search(r'\d+\s*uur$', m[0], re.I) and re.match(r'\s*(?:in totaal|per |duur)', text[m.end():], re.I):
            return m[0]
        return moment_label(m[0])
    text = MOMENT.sub(note_moment, text)
    if not text:
        return (moment + ': ' + class_label if class_label else moment) or value
    # Move explicit place markers; parentheses with notes remain notes.
    if not location:
        place = re.search(r'\s+@\s*([^()]+?)(?=\s*\(|$)', text)
        if place:
            location = place[1].strip()
            text = (text[:place.start()] + text[place.end():]).strip()
        elif re.search(r'\bop school\b', text, re.I) and not re.search(r'\(op school\)|\bniet op school\b', text, re.I):
            text = re.sub(r'\s*\bop school\b', '', text, flags=re.I).strip()
            location = 'op school'
        elif re.search(r'\bCLB\b.*\bkabinet\b', text, re.I):
            text = re.sub(r'\s+kabinet\b', '', text, flags=re.I)
            location = 'kabinet'
    if outing and re.fullmatch(r'\([^)]*\)', text):
        text = 'Uitstap ' + text
    if outing and not location and not re.search(r'\([^)]*\)$', text):
        location, text = re.sub(r'^(?:uitstap\s+)?naar\s+|^uitstap\s+', '', text, flags=re.I), 'Uitstap'
    elif not location and re.match(r'^(?:uitstap\s+naar\s+|Natuurhistorisch museum|Museum van |MOT Grimbergen|plantentuin)', text, re.I):
        text = re.sub(r'^uitstap\s+naar\s+', '', text, flags=re.I)
        location, text = text, 'Uitstap'
    if location and ('(' + location + ')').casefold() not in text.casefold():
        text += ' (' + location + ')'
    if not moment and not class_label and not location and text == original_text.strip(' ,:-–—'):
        return value
    return (moment + ': ' if moment else '') + (class_label + ' - ' if class_label else '') + text


def normalize_html(value, activity=''):
    # Keep each line's colors and links. Splitting nested markup via text nodes
    # would lose the original position of links, so reshape each inline fragment.
    from app.simple_calendar import split_lines
    def lines(markup):
        soup = BeautifulSoup(markup, 'html.parser')
        for node in list(soup.find_all(string=True)):
            if '\n' in node:
                for i, part in enumerate(str(node).split('\n')):
                    if i:
                        node.insert_before(soup.new_tag('br'))
                    node.insert_before(NavigableString(part))
                node.extract()
        return split_lines(str(soup))
    fragments = lines(value)
    result = []
    for fragment in fragments:
        original = fragment_text(fragment)
        if re.fullmatch(r'digitale wolven\s*:', original, re.I):
            activity = 'Digitale wolven'
        normalized = normalize_text(original)
        head = MOMENT.match(normalized)
        if activity and head and GROUP.fullmatch(normalized[head.end():].lstrip(': ')):
            normalized += ' - ' + activity
        result.append(reshape_html(fragment, normalized) if normalized != original else fragment)
    return '<br/>'.join(lines('<br/>'.join(result)))


def check_calendar(s, reason='manual'):
    con = s.core.db()
    changed, checked, stages_skipped = [], 0, 0
    # Keep a restorable copy before the first whole-calendar normalization.
    from pathlib import Path
    import sqlite3
    backup_path = str(s.core.DB_PATH) + '.before-format.bak'
    if not Path(backup_path).exists():
        backup = sqlite3.connect(backup_path)
        try:
            con.backup(backup)
        finally:
            backup.close()
    try:
        con.execute('BEGIN IMMEDIATE')
        records = con.execute('SELECT * FROM editor_lines WHERE deleted=0 ORDER BY date_local,id').fetchall()
        workshop_days = {r['date_local'] for r in records if any(re.fullmatch(r'digitale wolven\s*:?', t.strip(), re.I) for t in r['title'].splitlines())}
        merged = set()
        for index, row in enumerate(records):
            checked += 1
            if row['id'] in merged:
                continue
            if STAGE.search(row['title']):
                stages_skipped += 1
            body = row['body_html']
            if (row['date_local'] in workshop_days and MOMENT.fullmatch(row['title'].strip(' :'))
                    and index + 1 < len(records)):
                following = records[index + 1]
                if following['date_local'] == row['date_local'] and GROUP.fullmatch(following['title'].strip()):
                    body += ' ' + following['body_html'] + ' - Digitale wolven'
                    merged.add(following['id'])
                    changed.append({'key':'basis:' + str(following['id']), 'before':dict(following), 'merged_into':row['id']})
                    con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?',(following['id'],))
            rich = normalize_html(body, 'Digitale wolven' if row['date_local'] in workshop_days else '')
            title = fragment_text(rich)
            if rich != row['body_html'] or title != row['title']:
                changed.append({'key': 'basis:' + str(row['id']), 'before': dict(row), 'after': title})
                con.execute('UPDATE editor_lines SET body_html=?,title=?,version=version+1 WHERE id=?', (rich,title,row['id']))
        for row in con.execute('SELECT * FROM events WHERE visible_in_embed=1').fetchall():
            checked += 1
            stage = row['category'] == 'stage' or STAGE.search(row['title'])
            if stage:
                stages_skipped += 1
            title = row['title'] if stage else normalize_text(row['title'])
            description = row['description'] if stage else normalize_text(row['description'])
            rich = normalize_html(reshape_html(row['title_html'], title)) if row['title_html'] else ''
            desc_rich = normalize_html(row['description_html']) if row['description_html'] else ''
            if title != row['title'] or description != row['description'] or rich != row['title_html'] or desc_rich != row['description_html']:
                changed.append({'key': 'event:' + str(row['id']), 'before': dict(row), 'after': title})
                con.execute('UPDATE events SET title=?,description=?,title_html=?,description_html=?,updated_at=? WHERE id=?', (title,description,rich,desc_rich,s.core.now_iso(),row['id']))
        report = {'checked':checked,'changed':len(changed),'stages_skipped':stages_skipped,'timezone':'Europe/Brussels','reason':reason,'checked_at':s.core.now_iso()}
        if changed:
            s.audit(con, 'calendar.format_normalized', {'report':report,'changes':changed})
        con.execute("INSERT INTO settings(key,value) VALUES('calendar_format_last_check',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (s.json.dumps(report),))
        con.commit()
        return report
    finally:
        con.close()
