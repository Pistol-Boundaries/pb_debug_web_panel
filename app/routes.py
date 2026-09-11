from datetime import date, datetime, time, timedelta, timezone
from hmac import compare_digest
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.supabase_client import fetch_recent_logs


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
PLATFORMS = ["ios", "android"]

def _display_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str) and not value.strip():
        return "-"
    return str(value)


def _format_timestamp(value: Any) -> str:
    text = _display_value(value)
    if text == "-":
        return text

    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text

    month_day = parsed.strftime("%b %d").replace(" 0", " ")
    time_text = parsed.strftime("%I:%M %p").lstrip("0")
    return f"{month_day}, {time_text}"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_users(value: str | None) -> list[str]:
    if not value:
        return []

    parts = value.replace("\n", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def _is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _login_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "error_message": None,
        },
        status_code=401,
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    if not _is_authenticated(request):
        return _login_response(request)

    logs: list[dict[str, Any]] = []
    error_message: str | None = None
    start_date = request.query_params.get("start_date", "").strip()
    end_date = request.query_params.get("end_date", "").strip()
    users = request.query_params.get("users", "").strip()
    log_type = request.query_params.get("log_type", "").strip()
    platform = request.query_params.get("platform", "").strip().lower()

    try:
        start_value = _parse_date(start_date) if start_date else None
        end_value = _parse_date(end_date) if end_date else None
        user_ids = _parse_users(users)

        if start_value and end_value and start_value > end_value:
            raise ValueError("Start date must be on or before end date.")
        if platform and platform not in PLATFORMS:
            raise ValueError("Invalid platform.")

        start_at = None
        end_before = None
        if start_value:
            start_at = datetime.combine(start_value, time.min, tzinfo=timezone.utc).isoformat()
        if end_value:
            next_day = end_value + timedelta(days=1)
            end_before = datetime.combine(next_day, time.min, tzinfo=timezone.utc).isoformat()

        rows = fetch_recent_logs(
            start_at=start_at,
            end_before=end_before,
            user_ids=user_ids,
            log_type=log_type or None,
            platform=platform or None,
        )
        for row in rows:
            log = {key: _display_value(value) for key, value in row.items()}
            for field in ("occurred_at", "received_at"):
                log[field] = _format_timestamp(row.get(field))
                log[f"{field}_raw"] = _display_value(row.get(field))
            log["payload"] = row.get("payload")
            logs.append(log)
    except ValueError as exc:
        error_message = str(exc)
    except Exception as exc:
        error_message = str(exc)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "logs": logs,
            "error_message": error_message,
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "users": users,
                "log_type": log_type,
                "platform": platform,
            },
            "platform_options": [
                {"value": "ios", "label": "iOS"},
                {"value": "android", "label": "Android"},
            ],
        },
    )


@router.get("/map", response_class=HTMLResponse)
async def map_view(request: Request) -> HTMLResponse:
    if not _is_authenticated(request):
        return _login_response(request)

    points = []
    error_message = None
    filters = {
        name: request.query_params.get(name, "").strip()
        for name in ("user_id", "start_time", "end_time")
    }
    try:
        bounds = {}
        for name in ("start_time", "end_time"):
            value = filters[name]
            if not value:
                bounds[name] = None
                continue
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("Enter a valid start/end date and time.")
            bounds[name] = (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None
                            else parsed.astimezone(timezone.utc))
        start = bounds["start_time"]
        end = bounds["end_time"]
        if start and end and start >= end:
            raise ValueError("Start time must be before end time.")
        rows = fetch_recent_logs(
            locations_only=True,
            user_ids=[filters["user_id"]] if filters["user_id"] else None,
            start_at=start.isoformat() if start else None,
            end_before=end.isoformat() if end else None,
        )
        points = [
            {
                "lat": row["lat"],
                "lng": row["lng"],
                "label": f"{row.get('occurred_at')} · {row.get('user_id')}",
                "user_id": row.get("user_id"),
                "session_id": row.get("session_id"),
            }
            for row in reversed(rows)
            if row.get("lat") is not None and row.get("lng") is not None
        ]
    except Exception as exc:
        error_message = str(exc)

    return templates.TemplateResponse(
        request,
        "map.html",
        {"request": request, "points": points, "error_message": error_message, "filters": filters},
    )


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request, password: str = Form(...)) -> HTMLResponse:
    settings = get_settings()
    if compare_digest(password, settings.app_password):
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "error_message": "Incorrect password.",
        },
        status_code=401,
    )


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
