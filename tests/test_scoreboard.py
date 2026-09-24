from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app import routes, supabase_client


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only")
    app.include_router(routes.router)
    from fastapi.staticfiles import StaticFiles
    app.mount('/static', StaticFiles(directory='app/static'), name='static')
    monkeypatch.setattr(routes, 'get_settings', lambda: SimpleNamespace(app_password='test', default_log_limit=100))
    with TestClient(app) as client:
        client.post('/login', data={'password': 'test'}, follow_redirects=False)
        yield client


def test_fetch_scoreboard_alert_breakdown_calls_rpc(monkeypatch):
    rpc = MagicMock()
    rpc.execute.return_value = SimpleNamespace(data=[{'decision': 'sent', 'alert_count': 5}])
    db = MagicMock()
    db.rpc.return_value = rpc
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)

    result = supabase_client.fetch_scoreboard_alert_breakdown()

    db.rpc.assert_called_once_with('scoreboard_alert_breakdown')
    assert result == [{'decision': 'sent', 'alert_count': 5}]


def test_fetch_scoreboard_missed_alert_summary_calls_rpc(monkeypatch):
    rpc = MagicMock()
    rpc.execute.return_value = SimpleNamespace(data=[{'alert_scope': 'location', 'report_count': 3}])
    db = MagicMock()
    db.rpc.return_value = rpc
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)

    result = supabase_client.fetch_scoreboard_missed_alert_summary()

    db.rpc.assert_called_once_with('scoreboard_missed_alert_summary')
    assert result == [{'alert_scope': 'location', 'report_count': 3}]


def test_scoreboard_route_requires_auth():
    app = FastAPI()
    app.include_router(routes.router)
    from fastapi.staticfiles import StaticFiles
    app.mount('/static', StaticFiles(directory='app/static'), name='static')
    app.add_middleware(SessionMiddleware, secret_key="test-only")
    with TestClient(app) as anon_client:
        response = anon_client.get('/scoreboard')
        assert response.status_code == 401


def test_scoreboard_route_renders_breakdown_and_excludes_muted_from_total(client, monkeypatch):
    breakdown = [
        {'decision': 'sent', 'suppressed_reason': None, 'alert_helpful': 'none',
         'alert_issue': None, 'counted_as_miss': True, 'alert_count': 10},
        {'decision': 'suppressed', 'suppressed_reason': 'muted', 'alert_helpful': 'none',
         'alert_issue': None, 'counted_as_miss': False, 'alert_count': 4},
    ]
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda: breakdown)
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda: [])

    response = client.get('/scoreboard')

    assert response.status_code == 200
    assert 'Alert Scoreboard' in response.text
    # counted_total sums only counted_as_miss rows (10, not 14) -- rendered
    # as the "Sent" stat tile value.
    assert '<p class="stat-tile-value">10</p>' in response.text
    # Excluded (muted) row still shows in the bar chart and raw table, just
    # not counted toward the miss total.
    assert 'Suppressed' in response.text
    assert 'muted' in response.text


def test_breakdown_tone_only_colors_explicit_helpful_ratings():
    from app.routes import _breakdown_tone

    assert _breakdown_tone({'alert_helpful': 'yes'}) == 'good'
    assert _breakdown_tone({'alert_helpful': 'no'}) == 'serious'
    assert _breakdown_tone({'alert_helpful': 'none'}) == 'neutral'
    assert _breakdown_tone({'alert_helpful': None}) == 'neutral'


def test_scoreboard_route_groups_by_decision_and_applies_tone(client, monkeypatch):
    breakdown = [
        {'decision': 'sent', 'suppressed_reason': None, 'alert_helpful': 'yes',
         'alert_issue': None, 'counted_as_miss': True, 'alert_count': 5},
        {'decision': 'sent', 'suppressed_reason': None, 'alert_helpful': 'no',
         'alert_issue': 'late', 'counted_as_miss': True, 'alert_count': 3},
        {'decision': 'suppressed', 'suppressed_reason': 'motion_activity', 'alert_helpful': 'none',
         'alert_issue': None, 'counted_as_miss': True, 'alert_count': 20},
    ]
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda: breakdown)
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda: [])

    response = client.get('/scoreboard')

    assert response.status_code == 200
    # Suppressed group heading appears before the Sent group heading.
    suppressed_idx = response.text.index('bar-group-header">Suppressed')
    sent_idx = response.text.index('bar-group-header">Sent')
    assert suppressed_idx < sent_idx
    # Tone classes present for the explicit-rating rows.
    assert 'tone-good' in response.text
    assert 'tone-serious' in response.text
    # The suppressed row (no explicit rating) doesn't get a status tone.
    # 3 occurrences: bar-track, bar-fill, and the icon span each carry
    # the tone class.
    assert response.text.count('tone-good') == 3
    assert response.text.count('tone-serious') == 3
