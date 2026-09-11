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
) -> list[dict[str, Any]]:
    settings = get_settings()
    client = get_supabase_client()
    query_limit = limit or settings.default_log_limit

    query = (
        client.table(settings.supabase_logs_table)
        .select("id, user_id, occurred_at, received_at, type, label, note, lat, lng, accuracy_m, speed_ms, motion_state, session_id, platform, app_version, config_version, client_event_id, payload")
        .order("occurred_at", desc=True)
        .order("id", desc=True)
        .limit(query_limit)
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
