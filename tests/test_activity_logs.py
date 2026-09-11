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
    monkeypatch.setattr(routes, 'get_settings', lambda: SimpleNamespace(app_password='test'))
    with TestClient(app) as client:
        client.post('/login', data={'password': 'test'}, follow_redirects=False)
        yield client


def test_query_uses_activity_schema(monkeypatch):
    query = MagicMock()
    for method in ('select', 'order', 'limit', 'gte', 'lt', 'eq', 'in_'):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    db = MagicMock()
    db.table.return_value = query
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)
    monkeypatch.setattr(supabase_client, 'get_settings', lambda: SimpleNamespace(supabase_logs_table='activity_logs', default_log_limit=100))
    assert supabase_client.fetch_recent_logs(start_at='start', end_before='end', user_ids=['a','b'], log_type='new_event', platform='ios') == []
    db.table.assert_called_once_with('activity_logs')
    query.order.assert_any_call('occurred_at', desc=True)
    query.gte.assert_called_once_with('occurred_at', 'start')
    query.lt.assert_called_once_with('occurred_at', 'end')
    query.in_.assert_called_once_with('user_id', ['a','b'])
    query.eq.assert_any_call('type', 'new_event')
    columns = query.select.call_args.args[0].split(', ')
    assert 'created_at' not in columns
    assert {'lat', 'lng', 'payload', 'received_at'} <= set(columns)


def test_empty_and_new_event_filter(client, monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/?start_date=2026-09-11&end_date=2026-09-11&log_type=new_event&users=a,b')
    assert response.status_code == 200
    assert 'No logs found' in response.text
    assert 'Recent map' in response.text
    fetch.assert_called_once_with(start_at='2026-09-11T00:00:00+00:00', end_before='2026-09-12T00:00:00+00:00', user_ids=['a','b'], log_type='new_event', platform=None)


@pytest.mark.parametrize('coordinates', [(0, 0), (None, None)])
def test_records_and_payload_are_rendered_safely(client, monkeypatch, coordinates):
    row = dict(id=1, user_id='example-user', occurred_at='2026-09-11T12:00:00Z', received_at='2026-09-11T12:01:00Z', type='new_event', label='<script>alert(1)</script>', note=None, lat=coordinates[0], lng=coordinates[1], accuracy_m=0, speed_ms=0, motion_state=None, session_id=None, platform='ios', app_version=None, config_version=None, client_event_id=None, payload={'nested': {'enabled': False, 'text': '<script>'}})
    monkeypatch.setattr(routes, 'fetch_recent_logs', lambda **kwargs: [row])
    html = client.get('/').text
    assert 'example-user' in html and 'new_event' in html
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
    assert '"enabled": false' in html
    assert 'data-timestamp="2026-09-11T12:01:00Z"' in html
    assert 'type-success' not in html
    assert '<td>0</td>' in html


def test_invalid_dates_and_read_error(client, monkeypatch):
    fetch = MagicMock(side_effect=RuntimeError('Read unavailable'))
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    assert 'Start date must be' in client.get('/?start_date=2026-09-12&end_date=2026-09-11').text
    fetch.assert_not_called()
    assert 'Read unavailable' in client.get('/').text


def test_map_locations_empty_and_error(client, monkeypatch):
    fetch = MagicMock(return_value=[
        dict(lat=1, lng=2, occurred_at="later", user_id="u", session_id="s"),
        dict(lat=0, lng=0, occurred_at="earlier", user_id="u", session_id="s"),
    ])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map')
    assert response.status_code == 200
    fetch.assert_called_once_with(locations_only=True, user_ids=None, start_at=None, end_before=None)
    assert response.context['points'][0]['lat'] == 0
    assert 'Static debug points' not in response.text
    fetch.return_value = []
    assert 'No location records found' in client.get('/map').text
    fetch.side_effect = RuntimeError('Read unavailable')
    assert 'Unable to load locations' in client.get('/map').text
    client.post('/logout', follow_redirects=False)
    assert client.get('/map').status_code == 401


def test_map_filters(client, monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map', params={'user_id': ' walker ', 'start_time': '2026-09-11T14:43:00', 'end_time': '2026-09-11T14:57:00'})
    fetch.assert_called_once_with(locations_only=True, user_ids=['walker'], start_at='2026-09-11T14:43:00+00:00', end_before='2026-09-11T14:57:00+00:00')
    assert 'value="walker"' in response.text
    assert 'value="2026-09-11T14:43:00"' in response.text


@pytest.mark.parametrize('params', [
    {'start_time': 'bad'},
    {'start_time': '2026-09-11T15:00', 'end_time': '2026-09-11T14:00'},
    {'start_time': '2026-09-11T15:00', 'end_time': '2026-09-11T15:00'},
])
def test_map_invalid_filters(client, monkeypatch, params):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map', params=params)
    assert 'Unable to load locations' in response.text
    fetch.assert_not_called()


@pytest.mark.parametrize('field, expected', [('start_time', 'start_at'), ('end_time', 'end_before')])
def test_map_one_sided_time_filter(client, monkeypatch, field, expected):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    client.get('/map', params={field: '2026-09-11T14:00'})
    assert fetch.call_args.kwargs[expected] == '2026-09-11T14:00:00+00:00'
