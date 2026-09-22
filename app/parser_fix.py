from __future__ import annotations

import re

import app.main as core

MONTH_WORDS = (
    "januari|februari|maart|april|mei|juni|juli|augustus|"
    "september|oktober|november|december"
)
FULL_WEEKDAYS = "maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag"
SHORT_WEEKDAYS = "ma|di|woe|do|vrij|za|zo"

# Preserve the parser that already handles dates, times and automatic colour categories.
if not hasattr(core, "_before_title_cleanup_parse_instruction"):
    core._before_title_cleanup_parse_instruction = core.parse_instruction


def _clean_calendar_title(title: str) -> str:
    s = str(title or "").strip()

    # Remove a weekday abbreviation only when it clearly introduces a numeric date.
    s = re.sub(
        rf"\b(?:{SHORT_WEEKDAYS})\s+(?=\d{{1,2}}\s*[/-]\s*\d{{1,2}}\b)",
        " ",
        s,
        flags=re.I,
    )

    # Full weekday names are structural calendar words, not part of the activity title.
    s = re.sub(rf"\b(?:{FULL_WEEKDAYS})\b", " ", s, flags=re.I)

    # Numeric dates: 22/10, 22-10, 22/10/2026, 22-10-26.
    s = re.sub(
        r"\b\d{1,2}\s*[/-]\s*\d{1,2}(?:\s*[/-]\s*\d{2,4})?\b",
        " ",
        s,
        flags=re.I,
    )

    # Written dates: 22 oktober, 22 oktober 2026.
    s = re.sub(
        rf"\b\d{{1,2}}\s+(?:{MONTH_WORDS})(?:\s+\d{{4}})?\b",
        " ",
        s,
        flags=re.I,
    )

    # Clean structural leftovers around the removed date.
    s = re.sub(r"^\s*(?:op|voor)\b\s*", "", s, flags=re.I)
    s = re.sub(r"\s+([,:;])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.-/–—")

    if not s:
        return title.strip()
    return s[0].upper() + s[1:]


def parse_instruction_without_date_in_title(text: str):
    parsed = core._before_title_cleanup_parse_instruction(text)
    parsed["title"] = _clean_calendar_title(parsed.get("title", ""))
    return parsed


core.parse_instruction = parse_instruction_without_date_in_title
