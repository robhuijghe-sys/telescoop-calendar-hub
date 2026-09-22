import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "tch-parser-title-smoke.db")
os.environ["APP_SECRET"] = "parser-title-smoke-secret"
os.environ["COOKIE_SECURE"] = "false"

from app.public_calendar_snapshot import app  # noqa: F401
import app.main as core

cases = {
    "voeg toe 22/10 directie afwezig: werkgroep internationalisering": "Directie afwezig: werkgroep internationalisering",
    "voeg toe donderdag 22/10 directie afwezig: werkgroep internationalisering": "Directie afwezig: werkgroep internationalisering",
    "voeg toe op 22 oktober directie afwezig": "Directie afwezig",
    "voeg donderdag 22/10 om 14u30 teamvergadering toe": "Teamvergadering",
    "voeg do 22/10 oudercontact toe": "Oudercontact",
}

for prompt, expected_title in cases.items():
    parsed = core.parse_instruction(prompt)
    assert parsed["title"] == expected_title, (prompt, parsed["title"], expected_title)

parsed = core.parse_instruction("voeg toe donderdag 22/10 directie afwezig: werkgroep internationalisering")
assert parsed["date"].endswith("-10-22"), parsed

print("TCH_PARSER_TITLE_SMOKE_TEST=PASS")
