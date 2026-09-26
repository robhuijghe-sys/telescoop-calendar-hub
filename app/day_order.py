"""Stable display ordering; stored content and formatting remain untouched."""
import re
from bs4 import BeautifulSoup

ABSENCE = re.compile(r'\b(?:afw\.?|afwezig(?:heid)?)\b', re.I)
REPLACEMENT = re.compile(r'vervang|neemt\b.*\bover\b|→|->|gaat door met|geen (?:turnen|zwemmen|sport|les)|i\.p\.v\.', re.I)


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
    match = re.search(r'\b(\d+)(?:ste|de)\s+(?:les)?uur\b', text, re.I)
    return 8*60 + (int(match[1])-1)*50 if match else 24*60


def ordered_fragments(fragments):
    texts = [BeautifulSoup(f, 'html.parser').get_text(' ', strip=True) for f in fragments]
    meetings, stages, meeting_for = {}, [], None
    attached = set()
    for i, text in enumerate(texts):
        if re.search(r'\b(?:team|personeels|vakgroep)?vergadering\b', text, re.I):
            meetings[i] = []
            meeting_for = i
        elif re.search(r'\bstage(?:s|stagiair)?\b|\bstagiair', text, re.I):
            stages.append(i)
        elif meeting_for is not None and (re.match(r'^[*•–-]\s*', text) or re.search(r'\bagendapunt(?:en)?\b', text, re.I)):
            meetings[meeting_for].append(i)
            attached.add(i)
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
    for meeting in sorted(meetings, key=lambda i: time_key(texts[i])):
        order.append(meeting)
        order.extend(meetings[meeting])
    return [fragments[i] for i in order]
