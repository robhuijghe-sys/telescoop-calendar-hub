"""Shared stage labels; stored titles, times and class information stay intact."""
import re


STAGE_COLOR = '#5dade2'
STAGE_TITLE = re.compile(r'^stage\b', re.IGNORECASE)
TITLE_HOURS = re.compile(
    r'\s+van\s+\d{1,2}(?:[u:.h]\d{0,2})?'
    r'(?:\s+tot\s+\d{1,2}(?:[u:.h]\d{0,2})?)?'
    r'(?=\s*(?:$|\())', re.IGNORECASE)


def is_stage(title):
    return bool(STAGE_TITLE.match(str(title).strip()))


def stage_label(title, start, end, all_day=False):
    title = str(title).strip()
    title = STAGE_TITLE.sub('Stage', title, count=1) if is_stage(title) else 'Stage ' + title
    if all_day:
        return title
    # A title can already include hours entered in ordinary language. The
    # structured event times are authoritative; keep any note after the hours.
    existing = TITLE_HOURS.search(title)
    suffix = ''
    if existing:
        suffix = title[existing.end():]
        title = title[:existing.start()].rstrip()
    clock = lambda value: f'{value.hour}u{value.minute:02d}'
    return f'{title} van {clock(start)} tot {clock(end)}{suffix}'
