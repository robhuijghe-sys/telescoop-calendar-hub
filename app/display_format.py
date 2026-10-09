"""Canonical calendar labels; stages and unknown details remain intact."""
import re
from bs4 import BeautifulSoup, NavigableString
from app.rich_editor import fragment_text, reshape_html

STAGE = re.compile(r'\b(?:stages?|stagiair\w*)\b', re.I)
CLOCK = r'(?:[01]?\d|2[0-3])(?:[.:h][0-5]\d(?:u)?|\s*uur|u(?:[0-5]\d)?)'
LESSON = r'\d+(?:ste|de)(?:\s*(?:en|[-–])\s*\d+(?:ste|de))?\s+(?:les)?uur'
MOMENT = re.compile(r'(?<![\w,.])(?:' + LESSON + r'|' + CLOCK + r'(?:\s*(?:tot|[-–—])\s*' + CLOCK + r')?|VM|NM|voormiddag|namiddag|hele dag)(?!\w)', re.I)
GROUP_ATOM = r'(?:K0K1|L5L6|GR[123]|[KL][0-6])'
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
    if STAGE.search(value):
        return value
    if '\n' in value:
        return '\n'.join(normalize_text(line) for line in value.split('\n'))
    text = value.strip()
    original_text = text
    # Agenda bullets, durations and class-only slots are not separate activities.
    if not text or re.match(r'^[*•]\s', text):
        return value
    if re.fullmatch(GROUP_ATOM + r'(?:\s*[+&/]\s*' + GROUP_ATOM + r')*', text, re.I):
        return value
    found = MOMENT.search(text)
    if found:
        before, after = text[:found.start()], text[found.end():]
        # Never turn a duration or deadline into the event's start time.
        duration = re.search(r'\d+\s*uur$', found[0], re.I) and re.match(r'\s*(?:in totaal|per |duur)', after, re.I)
        incidental = re.search(r'\b(?:tegen|vanaf|tot|na|voor)\s*$', before, re.I)
        movable = not before.strip() or before.rstrip().endswith((':', '(', ',')) or not after.strip(' .:') or re.search(r'\bom\s*$', before, re.I) or GROUP.fullmatch(before.strip())
        if movable and not duration and not incidental:
            if not moment:
                moment = moment_label(found[0])
            if before.endswith('(') and after.startswith(')'):
                before, after = before[:-1], after[1:]
            before = re.sub(r'\bom\s*$', '', before, flags=re.I)
            text = (before.rstrip(' ,:.-') + ' ' + after.lstrip(' ,:.-–—')).strip()
    group = GROUP.search(text)
    class_label = ''
    if group:
        # A class introduced only as a location stays in the activity text.
        before_group = text[:group.start()]
        contextual = before_group.count('(') > before_group.count(')') and not before_group.endswith('(')
        absence = re.search(r'\b(?:afwezig|afw)\b', text, re.I)
        if not contextual and not absence and not re.search(r'\b(?:in|bij|naar|vervangt|i\.p\.v\.)\s*$', before_group, re.I):
            class_label = re.sub(GROUP_ATOM, lambda m:m[0].upper(), re.sub(r'\s+', ' ', group[0]), flags=re.I)
            before, after = text[:group.start()], text[group.end():]
            if before.endswith('(') and after.startswith(')'):
                before, after = before[:-1], after[1:]
            text = (before.rstrip(' ,:.-') + ' ' + after.lstrip(' ,:.-–—')).strip()
    text = text.strip(' ,:-–—')
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
    soup = BeautifulSoup(value, 'html.parser')
    if STAGE.search(fragment_text(value)) and all(STAGE.search(t) for t in fragment_text(value).splitlines() if t.strip()):
        return value
    from app.simple_calendar import split_lines
    for node in list(soup.find_all(string=True)):
        if '\n' in node:
            for i, part in enumerate(str(node).split('\n')):
                if i:
                    node.insert_before(soup.new_tag('br'))
                node.insert_before(NavigableString(part))
            node.extract()
    fragments = split_lines(str(soup))
    changed = False
    result = []
    for fragment in fragments:
        original = fragment_text(fragment)
        if re.fullmatch(r'digitale wolven\s*:', original, re.I):
            activity = 'Digitale wolven'
        normalized = normalize_text(original)
        head = MOMENT.match(normalized)
        if activity and head and GROUP.fullmatch(normalized[head.end():].lstrip(': ')):
            normalized += ' - ' + activity
        changed |= normalized != original
        result.append(reshape_html(fragment, normalized) if normalized != original else fragment)
    return '<br/>'.join(result) if changed else value


def check_calendar(s, reason='manual'):
    con = s.core.db()
    changed, skipped, checked = [], 0, 0
    try:
        con.execute('BEGIN IMMEDIATE')
        records = con.execute('SELECT * FROM editor_lines WHERE deleted=0').fetchall()
        workshop_days = {r['date_local'] for r in records if any(re.fullmatch(r'digitale wolven\s*:', t.strip(), re.I) for t in r['title'].splitlines())}
        for row in records:
            checked += 1
            if all(STAGE.search(t) for t in row['title'].splitlines() if t.strip()):
                skipped += 1
                continue
            rich = normalize_html(row['body_html'], 'Digitale wolven' if row['date_local'] in workshop_days else '')
            title = fragment_text(rich)
            if rich != row['body_html'] or title != row['title']:
                changed.append({'key': 'basis:' + str(row['id']), 'before': dict(row), 'after': title})
                con.execute('UPDATE editor_lines SET body_html=?,title=?,version=version+1 WHERE id=?', (rich,title,row['id']))
        for row in con.execute('SELECT * FROM events WHERE visible_in_embed=1').fetchall():
            checked += 1
            if row['category'] == 'stage' or STAGE.search(row['title']):
                skipped += 1
                continue
            title = normalize_text(row['title'])
            description = normalize_text(row['description'])
            if title != row['title'] or description != row['description']:
                changed.append({'key': 'event:' + str(row['id']), 'before': dict(row), 'after': title})
                rich = reshape_html(row['title_html'], title) if row['title_html'] else ''
                desc_rich = normalize_html(row['description_html']) if row['description_html'] else ''
                con.execute('UPDATE events SET title=?,description=?,title_html=?,description_html=?,updated_at=? WHERE id=?', (title,description,rich,desc_rich,s.core.now_iso(),row['id']))
        report = {'checked':checked,'changed':len(changed),'stages_skipped':skipped,'reason':reason,'checked_at':s.core.now_iso()}
        if changed:
            s.audit(con, 'calendar.format_normalized', {'report':report,'changes':changed})
        con.execute("INSERT INTO settings(key,value) VALUES('calendar_format_last_check',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (s.json.dumps(report),))
        con.commit()
        return report
    finally:
        con.close()
