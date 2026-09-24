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
    # counted_total sums only counted_as_miss rows (10, not 14)
    assert '<strong>10</strong>' in response.text
