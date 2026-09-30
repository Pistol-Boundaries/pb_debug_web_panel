from datetime import date, datetime, time, timedelta, timezone
from hmac import compare_digest
from urllib.parse import urlencode
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.supabase_client import (
    fetch_recent_logs,
    fetch_filter_options,
    fetch_scoreboard_alert_breakdown,
    fetch_scoreboard_alert_versions,
    fetch_scoreboard_missed_alert_summary,
)


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
    page = 1
    has_older = False
    page_size = get_settings().default_log_limit
    error_message: str | None = None
    start_date = request.query_params.get("start_date", "").strip()
    end_date = request.query_params.get("end_date", "").strip()
    users = ",".join(request.query_params.getlist("users")).strip()
    log_type = request.query_params.get("log_type", "").strip()
    platform = request.query_params.get("platform", "").strip().lower()

    try:
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError:
            raise ValueError("Page must be a positive whole number.")
        if page < 1:
            raise ValueError("Page must be a positive whole number.")
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
            limit=page_size + 1,
            offset=(page - 1) * page_size,
            start_at=start_at,
            end_before=end_before,
            user_ids=user_ids,
            log_type=log_type or None,
            platform=platform or None,
        )
        has_older = len(rows) > page_size
        for row in rows[:page_size]:
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

    selected_users = _parse_users(users)
    options_warning = None
    try:
        options = fetch_filter_options()
    except Exception:
        options = {"user_id": [], "type": []}
        options_warning = "Could not load all filter choices. Showing values from this page and current selections."
    user_options = sorted(set(options["user_id"]) | set(selected_users) | {log["user_id"] for log in logs if log.get("user_id") not in (None, "-")})
    type_options = sorted(set(options["type"]) | ({log_type} if log_type else set()) | {log["type"] for log in logs if log.get("type") not in (None, "-")})

    def page_url(number: int) -> str:
        params = dict(request.query_params)
        params["users"] = users
        params["page"] = str(number)
        return "/?" + urlencode(params)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "logs": logs,
            "user_options": user_options,
            "type_options": type_options,
            "selected_users": selected_users,
            "options_warning": options_warning,
            "page": page,
            "newer_url": page_url(page - 1) if page > 1 else None,
            "older_url": page_url(page + 1) if has_older else None,
            "current_page_url": page_url(page),
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
    selected_users = list(dict.fromkeys(value.strip() for value in request.query_params.getlist("user_id") if value.strip()))
    # Only default a new visit; explicit blank fields mean unrestricted time.
    if "start_time" not in request.query_params and "end_time" not in request.query_params:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        filters["start_time"] = (now - timedelta(hours=1)).isoformat()
        filters["end_time"] = now.isoformat()
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
        rows = []
        while len(rows) < 5000:
            batch = fetch_recent_logs(
                limit=min(500, 5000 - len(rows)),
                offset=len(rows),
                locations_only=True,
                user_ids=selected_users or None,
                start_at=start.isoformat() if start else None,
                end_before=end.isoformat() if end else None,
            )
            if not batch:
                break
            rows.extend(batch)
        points = [
            {
                "occurred_at": row.get("occurred_at"),
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

    options_warning = None
    try:
        available_users = fetch_filter_options()["user_id"]
    except Exception:
        available_users = []
        options_warning = "Could not load all user choices. Showing users from this map and current selections."
    user_options = sorted(set(available_users) | set(selected_users) | {point["user_id"] for point in points if point.get("user_id")})

    return templates.TemplateResponse(
        request,
        "map.html",
        {"request": request, "points": points, "error_message": error_message, "filters": filters,
         "selected_users": selected_users, "user_options": user_options, "options_warning": options_warning},
    )


def _breakdown_tone(row: dict[str, Any]) -> str:
    """Color the ONE signal that's already an explicit user judgment --
    alert_helpful yes/no -- and nothing else. Suppressed rows and
    unrated "sent" rows stay neutral: whether those are actually good
    or bad is exactly the undefined question pending Scott's
    definitions, so this must not quietly pre-judge them via color."""
    if row.get("alert_helpful") == "yes":
        return "good"
    if row.get("alert_helpful") == "no":
        return "serious"
    return "neutral"


def _breakdown_label(row: dict[str, Any]) -> str:
    """Human-readable category name for one breakdown row, combining the
    dimensions that actually vary (decision/suppressed_reason when
    suppressed, alert_helpful/alert_issue when sent) into one bar label."""
    if row.get("decision") == "suppressed":
        return f"Suppressed — {row.get('suppressed_reason') or 'unknown'}"
    parts = ["Sent"]
    helpful = row.get("alert_helpful")
    if helpful and helpful != "none":
        parts.append(f"helpful: {helpful}")
    issue = row.get("alert_issue")
    if issue:
        parts.append(issue)
    return " — ".join(parts)


@router.get("/scoreboard", response_class=HTMLResponse)
async def scoreboard(request: Request) -> HTMLResponse:
    if not _is_authenticated(request):
        return _login_response(request)

    start_date = request.query_params.get("start_date", "").strip()
    end_date = request.query_params.get("end_date", "").strip()
    version_raw = request.query_params.get("version", "").strip()
    # Only default on a fresh visit (no params at all); an explicit uncheck
    # means "show debug data" and must stay unchecked on reload.
    include_debug_user = (
        request.query_params.get("include_debug_user") == "on"
        if request.query_params
        else False
    )

    breakdown: list[dict[str, Any]] = []
    missed_summary: list[dict[str, Any]] = []
    error_message: str | None = None
    try:
        start_value = _parse_date(start_date) if start_date else None
        end_value = _parse_date(end_date) if end_date else None
        if start_value and end_value and start_value > end_value:
            raise ValueError("Start date must be on or before end date.")
        version_value: float | None = None
        if version_raw:
            try:
                version_value = float(version_raw)
            except ValueError:
                raise ValueError("Version must be a number, e.g. 0.1.")

        from_at = (
            datetime.combine(start_value, time.min, tzinfo=timezone.utc).isoformat()
            if start_value
            else None
        )
        to_before = (
            datetime.combine(end_value + timedelta(days=1), time.min, tzinfo=timezone.utc).isoformat()
            if end_value
            else None
        )
        exclude_debug_user = not include_debug_user

        breakdown = fetch_scoreboard_alert_breakdown(
            from_at=from_at,
            to_before=to_before,
            version=version_value,
            exclude_debug_user=exclude_debug_user,
        )
        missed_summary = fetch_scoreboard_missed_alert_summary(
            from_at=from_at,
            to_before=to_before,
            exclude_debug_user=exclude_debug_user,
        )
    except ValueError as exc:
        error_message = str(exc)
    except Exception as exc:
        error_message = str(exc)

    try:
        version_options = fetch_scoreboard_alert_versions()
    except Exception:
        version_options = []
    if version_raw and version_raw not in version_options:
        try:
            version_options = sorted({*version_options, version_raw}, key=float)
        except ValueError:
            pass  # invalid input already surfaced via error_message above

    total_alerts = sum(row["alert_count"] for row in breakdown)
    sent_total = sum(row["alert_count"] for row in breakdown if row.get("decision") == "sent")
    suppressed_total = sum(row["alert_count"] for row in breakdown if row.get("decision") == "suppressed")
    counted_total = sum(row["alert_count"] for row in breakdown if row.get("counted_as_miss"))
    excluded_total = sum(row["alert_count"] for row in breakdown if not row.get("counted_as_miss"))

    # Grouped by decision (Suppressed, then Sent) rather than a flat count
    # sort: a pure magnitude sort interleaves "why was it suppressed"
    # reasons with "was it helpful once sent" outcomes, which is exactly
    # the two comparisons the Scott conversation needs to make within
    # each group, not just against the whole list. Sorted by count within
    # each group so magnitude is still visible where it matters.
    max_count = max((row["alert_count"] for row in breakdown), default=0)

    def _bar(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "label": _breakdown_label(row),
            "count": row["alert_count"],
            "counted_as_miss": bool(row.get("counted_as_miss")),
            "tone": _breakdown_tone(row),
            "pct": round(row["alert_count"] / max_count * 100, 1) if max_count else 0,
        }

    breakdown_groups = [
        {
            "name": name,
            "bars": [
                _bar(row)
                for row in sorted(
                    (r for r in breakdown if r.get("decision") == decision),
                    key=lambda r: r["alert_count"],
                    reverse=True,
                )
            ],
        }
        for decision, name in (("suppressed", "Suppressed"), ("sent", "Sent"))
    ]
    breakdown_groups = [g for g in breakdown_groups if g["bars"]]

    max_missed = max((row["report_count"] for row in missed_summary), default=0)
    missed_bars = [
        {
            "label": row.get("alert_scope") or "unknown",
            "count": row["report_count"],
            # Unlike the breakdown chart, every row here is an unambiguous
            # negative signal by construction (a user reported a real
            # miss) -- not a new classification, just naming what this
            # table already is.
            "tone": "critical",
            "pct": round(row["report_count"] / max_missed * 100, 1) if max_missed else 0,
        }
        for row in sorted(missed_summary, key=lambda r: r["report_count"], reverse=True)
    ]

    return templates.TemplateResponse(
        request,
        "scoreboard.html",
        {
            "request": request,
            "breakdown": breakdown,
            "breakdown_groups": breakdown_groups,
            "missed_bars": missed_bars,
            "total_alerts": total_alerts,
            "sent_total": sent_total,
            "suppressed_total": suppressed_total,
            "counted_total": counted_total,
            "excluded_total": excluded_total,
            "error_message": error_message,
            "version_options": version_options,
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "version": version_raw,
                "include_debug_user": include_debug_user,
            },
        },
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
