from fastapi.responses import HTMLResponse

from app.calendar_snapshot import render_snapshot_calendar
from app.public_calendar import app, _remove_route
import app.parser_fix  # noqa: F401 - patches core.parse_instruction for public calendar input

# Replace the database-only renderer with the migrated full calendar + live additions.
_remove_route("/smartschool-calendar", "GET")


@app.get("/smartschool-calendar", response_class=HTMLResponse)
def public_smartschool_calendar_snapshot():
    return HTMLResponse(
        render_snapshot_calendar(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
