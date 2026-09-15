from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routes import router


app = FastAPI(title="Activity Log Viewer")
settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="__session",
    same_site="lax",
    https_only=settings.session_https_only,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response
