import app.main as core
from app.calendar_dynamic import app

_previous_page = core.page


def live_calendar_page(title: str, body: str, user=None):
    rendered = _previous_page(title, body, user)
    rendered = rendered.replace(
        "Smartschool testmodus actief: publiceren schrijft nog niet naar Smartschool.",
        "Dynamische kalender actief: opgeslagen kalenderitems verschijnen automatisch in de Smartschoolweergave.",
    )
    return rendered


core.page = live_calendar_page
