from fastapi import Request
from fastapi.responses import RedirectResponse

from app.production import app


@app.middleware("http")
async def redirect_unauthenticated_browser(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    public_or_api = (
        path == "/login"
        or path == "/health"
        or path == "/connector-openapi.json"
        or path.startswith("/api/")
        or path.startswith("/oauth/")
        or path.startswith("/embed")
    )
    if response.status_code == 401 and not public_or_api:
        return RedirectResponse(url="/login", status_code=303)
    return response
