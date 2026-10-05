"""Stable display ordering and meeting groups; stored records stay untouched."""
import re
from bs4 import BeautifulSoup

ABSENCE = re.compile(r'\b(?:afw\.?|afwezig(?:heid)?)\b', re.I)
REPLACEMENT = re.compile(r'vervang|neemt\b.*\bover\b|→|->|gaat door met|geen (?:turnen|zwemmen|sport|les)|i\.p\.v\.', re.I)
MEETING = re.compile(r'\b(?:[\w-]*vergadering(?:en)?|vakgroep(?:en)?|[\w-]*overleg|oudervereniging|klassenraad|klassenraden)\b', re.I)
AGENDA = re.compile(r'^[*•–-]\s*|\bagendapunt(?:en)?\b', re.I)
SWAP = re.compile(r'\b(?:wissel|leswissel|vervanging(?:en)?)\b', re.I)
FORMAL_MEETING = re.compile(r'\b(?:vakgroep(?:en)?|[\w-]*vergadering(?:en)?)\b', re.I)
MEETING_COLOR = '#8e44ad'
READING_BLOCK = re.compile(
    r'^(?:[23]\s+weken\s+(?:LIST|close\s+reading)|LIST\s+tot\s+einde\s+schooljaar)'
    r'(?:\s*\([^)]*\))?$', re.I)


def is_meeting(text):
    """Do not turn an absence or a replacement mentioning a meeting into one."""
    match = MEETING.search(text)
    if not match or ABSENCE.search(text) or AGENDA.match(text):
        return False
    return not (REPLACEMENT.search(text[:match.start()]) or SWAP.search(text[:match.start()]))


def meeting_reference(text):
    match = re.search(r'\bvakgroep(?:vergadering)?\s*:?\s*(NED|WO|WIS|kleuter)\b', text, re.I)
    if match:
        return 'vakgroep ' + match[1].lower()
    match = MEETING.search(text)
    return match[0].lower() if match else None


def is_replacement(text):
    return bool(REPLACEMENT.search(text)) and not ABSENCE.search(text)


def group_workshops(fragments):
    """Keep a unique workshop heading and its explicit class slots together."""
    texts = [BeautifulSoup(f, 'html.parser').get_text(' ', strip=True) for f in fragments]
    heads = [i for i, t in enumerate(texts) if re.fullmatch(r'digitale wolven\s*:?', t, re.I)]
    slots = [i for i, t in enumerate(texts) if re.fullmatch(r'\d+(?:ste|de)(?:\s+en\s+\d+(?:ste|de))?\s+lesuur\s*:\s*(?:GR[123]|[KL][1-6])(?:\s*\+\s*(?:GR[123]|[KL][1-6]))*', t, re.I)]
    if len(heads) != 1 or not slots:
        return fragments
    head = heads[0]
    heading = BeautifulSoup(fragments[head], 'html.parser')
    for node in heading.find_all(string=True):
        if re.fullmatch(r'\s*digitale wolven\s*:?', str(node), re.I):
            node.replace_with(str(node).rstrip().rstrip(':') + ':')
            break
    group = '<div class="activity-group">' + str(heading) + '\n' + '\n'.join(fragments[i] for i in sorted(slots, key=lambda i: time_key(texts[i]))) + '</div>'
    return [group if i == head else f for i, f in enumerate(fragments) if i not in slots]


def time_key(text):
    if re.search(r'\bhele dag\b', text, re.I):
        return 0
    if re.search(r'\b(?:VM|voormiddag)\b', text, re.I):
        return 8 * 60
    if re.search(r'\b(?:NM|namiddag)\b', text, re.I):
        return 13 * 60
    match = re.search(r'(?<!\d)([01]?\d|2[0-3])(?:[:.h]([0-5]\d)|u([0-5]\d)?)(?!\d)', text, re.I)
    if match:
        return int(match[1])*60 + int(match[2] or match[3] or 0)
    match = re.search(r'\b([01]?\d|2[0-3])\s+uur\b', text, re.I)
    if match:
        return int(match[1])*60
    match = re.search(r'\b(\d+)(?:ste|de)(?:\s+en\s+\d+(?:ste|de))?\s+(?:les)?uur\b', text, re.I)
    return 8*60 + (int(match[1])-1)*50 if match else 24*60


def meeting_time_key(text):
    # School lesson periods include the morning break and lunch. A replacement
    # time later in the description must not override the meeting's lesson slot.
    lesson = re.search(r'\b([1-6])(?:ste|de)(?:\s+en\s+\d+(?:ste|de))?\s+lesuur\b', text, re.I)
    clock = re.search(r'(?<!\d)([01]?\d|2[0-3])(?:[:.h][0-5]\d|u(?:[0-5]\d)?|\s+uur\b)', text, re.I)
    if lesson and (not clock or lesson.start() < clock.start()):
        return (525, 575, 640, 690, 800, 850)[int(lesson[1]) - 1]
    return time_key(text)


def ordered_fragments(fragments, style_meetings=False):
    fragments = group_workshops(fragments)
    texts = [BeautifulSoup(f, 'html.parser').get_text(' ', strip=True) for f in fragments]
    reading_blocks = {fragment for fragment, text in zip(fragments, texts)
                      if READING_BLOCK.fullmatch(text)}
    meetings = {i: [] for i, text in enumerate(texts) if is_meeting(text)}
    stages, meeting_for = [], None
    attached = set()
    for i, text in enumerate(texts):
        if i in meetings:
            # Agenda bullets remain with the team/vakgroep, even if a general
            # zorgoverleg entry was imported between the heading and its agenda.
            if meeting_for is None or FORMAL_MEETING.search(text):
                meeting_for = i
        elif re.search(r'\bstage(?:s|stagiair)?\b|\bstagiair', text, re.I):
            stages.append(i)
        elif meeting_for is not None and AGENDA.search(text):
            meetings[meeting_for].append(i)
            attached.add(i)
    for i, text in enumerate(texts):
        if i in meetings or i in attached or ABSENCE.search(text):
            continue
        if not (REPLACEMENT.search(text) or SWAP.search(text)):
            continue
        reference = meeting_reference(text)
        candidates = [m for m in meetings if reference and meeting_reference(texts[m]) == reference]
        if not candidates and SWAP.search(text):
            candidates = [m for m in meetings if (ref := meeting_reference(texts[m]))
                          and ref.startswith('vakgroep ')
                          and re.search(r'\b' + re.escape(ref.split()[-1]) + r'\b', text, re.I)]
        if len(candidates) == 1:
            meetings[candidates[0]].append(i)
            attached.add(i)
    stages = [i for i in stages if i not in attached]
    bottom = set(meetings) | set(stages) | attached
    absent = [i for i,t in enumerate(texts) if i not in bottom and ABSENCE.search(t)]
    groups = {i: [] for i in absent}
    rest, loose = [], []
    for i,text in enumerate(texts):
        if i in groups or i in bottom:
            continue
        if not REPLACEMENT.search(text):
            rest.append(i)
            continue
        # Prefer an explicit reference to the absent person, then source proximity.
        target = re.search(r'\bvervang\w*\s+([\wÀ-ÿ-]+)', text, re.I)
        matches = [a for a in absent if target and re.search(r'\b'+re.escape(target[1])+r'\b', texts[a], re.I)]
        preceding = [a for a in absent if a < i]
        owner = matches[0] if matches else (preceding[-1] if preceding else (absent[0] if len(absent)==1 else None))
        if owner is None:
            loose.append(i)
        else:
            groups[owner].append(i)
    order = []
    for a in absent:
        order.append(a)
        order.extend(sorted(groups[a], key=lambda i: time_key(texts[i])))
    order.extend(sorted(loose, key=lambda i: time_key(texts[i])))
    order.extend(sorted(rest, key=lambda i: time_key(texts[i])))
    order.extend(sorted(stages, key=lambda i: time_key(texts[i])))
    result = [fragments[i] for i in order]
    for meeting in sorted(meetings, key=lambda i: meeting_time_key(texts[i])):
        group = [fragments[i] for i in [meeting] + sorted(meetings[meeting])]
        if style_meetings:
            result.append('<div class="meeting-group">' + ''.join(group) + '</div>')
        else:
            result.extend(group)
    # Pin the period labels first; keep all other activity and meeting ordering.
    return sorted(result, key=lambda fragment: fragment not in reading_blocks)
