from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


def fetch_recent_logs(
    limit: int | None = None,
    start_at: str | None = None,
    end_before: str | None = None,
    user_ids: list[str] | None = None,
    log_type: str | None = None,
    platform: str | None = None,
    locations_only: bool = False,
    offset: int = 0,
) -> list[dict[str, Any]]:
    settings = get_settings()
    client = get_supabase_client()
    query_limit = limit or settings.default_log_limit

    query = (
        client.table(settings.supabase_logs_table)
        .select("id, user_id, occurred_at, received_at, type, label, note, lat, lng, accuracy_m, speed_ms, motion_state, session_id, platform, app_version, config_version, client_event_id, payload")
        .order("occurred_at", desc=True)
        .order("id", desc=True)
        .range(offset, offset + query_limit - 1)
    )

    if locations_only:
        query = query.not_.is_("lat", "null").not_.is_("lng", "null")

    if start_at:
        query = query.gte("occurred_at", start_at)
    if end_before:
        query = query.lt("occurred_at", end_before)
    if user_ids:
        if len(user_ids) == 1:
            query = query.eq("user_id", user_ids[0])
        else:
            query = query.in_("user_id", user_ids)
    if log_type:
        query = query.eq("type", log_type)
    if platform:
        query = query.eq("platform", platform)

    response = query.execute()

    return response.data or []


def fetch_scoreboard_alert_breakdown(
    from_at: str | None = None,
    to_before: str | None = None,
    version: float | None = None,
    exclude_debug_user: bool = True,
) -> list[dict[str, Any]]:
    """PB-549: raw alerts breakdown via the scoreboard_alert_breakdown() DB
    function. TP/FP/FN classification is intentionally not computed --
    pending Scott's definitions; this surfaces counts for that conversation.
    """
    client = get_supabase_client()
    response = client.rpc(
        "scoreboard_alert_breakdown",
        {
            "p_from": from_at,
            "p_to": to_before,
            "p_version": version,
            "p_exclude_debug_user": exclude_debug_user,
        },
    ).execute()
    return response.data or []


def fetch_scoreboard_missed_alert_summary(
    from_at: str | None = None,
    to_before: str | None = None,
    exclude_debug_user: bool = True,
) -> list[dict[str, Any]]:
    """PB-549: missed_alert_feedback counts by scope via the
    scoreboard_missed_alert_summary() DB function."""
    client = get_supabase_client()
    response = client.rpc(
        "scoreboard_missed_alert_summary",
        {
            "p_from": from_at,
            "p_to": to_before,
            "p_exclude_debug_user": exclude_debug_user,
        },
    ).execute()
    return response.data or []


def fetch_scoreboard_alert_versions() -> list[str]:
    """PB-549: distinct alert_service_version values in use, for the
    scoreboard page's version filter dropdown."""
    client = get_supabase_client()
    response = client.rpc("scoreboard_alert_versions").execute()
    return [str(row["version"]) for row in response.data or [] if row.get("version") is not None]


_filter_options_cache: tuple[float, tuple[str, str, str], dict[str, list[str]]] | None = None


def fetch_filter_options() -> dict[str, list[str]]:
    """Read indexed columns only, skipping already-seen values between batches."""
    from time import monotonic
    global _filter_options_cache
    settings = get_settings()
    cache_key = (settings.supabase_url, settings.supabase_logs_table, settings.supabase_key)
    if _filter_options_cache:
        expires, key, options = _filter_options_cache
        if key == cache_key and monotonic() < expires:
            return options
    client = get_supabase_client()
    options = {}
    for column in ("user_id", "type"):
        values = set()
        last_value = None
        while True:
            query = client.table(settings.supabase_logs_table).select(column).order(column).limit(1000)
            if last_value is not None:
                query = query.gt(column, last_value)
            rows = query.execute().data or []
            if not rows:
                break
            batch = [row[column] for row in rows if isinstance(row.get(column), str)]
            if not batch:
                break
            values.update(value for value in batch if value.strip())
            next_value = batch[-1]
            if next_value == last_value:
                break
            last_value = next_value
        options[column] = sorted(values)
    _filter_options_cache = (monotonic() + 300, cache_key, options)
    return options
