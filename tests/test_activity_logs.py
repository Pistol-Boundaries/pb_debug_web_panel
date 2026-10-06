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


def test_query_uses_activity_schema(monkeypatch):
    query = MagicMock()
    for method in ('select', 'order', 'range', 'gte', 'lt', 'eq', 'in_'):
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
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/?start_date=2026-09-11&end_date=2026-09-11&log_type=new_event&users=a,b')
    assert response.status_code == 200
    assert 'No logs found' in response.text
    assert 'Recent map' in response.text
    fetch.assert_called_once_with(limit=101, offset=0, start_at='2026-09-11T00:00:00+00:00', end_before='2026-09-12T00:00:00+00:00', user_ids=['a','b'], log_type='new_event', platform=None)


@pytest.mark.parametrize('coordinates', [(0, 0), (None, None)])
def test_records_and_payload_are_rendered_safely(client, monkeypatch, coordinates):
    row = dict(id=1, user_id='example-user', occurred_at='2026-09-11T12:00:00Z', received_at='2026-09-11T12:01:00Z', type='new_event', label='<script>alert(1)</script>', note=None, lat=coordinates[0], lng=coordinates[1], accuracy_m=0, speed_ms=0, motion_state=None, session_id=None, platform='ios', app_version=None, config_version=None, client_event_id=None, payload={'nested': {'enabled': False, 'text': '<script>'}})
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
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
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    assert 'Start date must be' in client.get('/?start_date=2026-09-12&end_date=2026-09-11').text
    fetch.assert_not_called()
    assert 'Read unavailable' in client.get('/').text


def test_map_locations_empty_and_error(client, monkeypatch):
    fetch = MagicMock(side_effect=[[
        dict(lat=1, lng=2, occurred_at="later", user_id="u", session_id="s"),
        dict(lat=0, lng=0, occurred_at="earlier", user_id="u", session_id="s"),
    ], []])
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map')
    assert response.status_code == 200
    assert fetch.call_count == 2
    from datetime import datetime, timedelta, timezone
    args = fetch.call_args.kwargs
    assert args['limit'] == 500 and args['locations_only'] is True
    start = datetime.fromisoformat(args['start_at'])
    end = datetime.fromisoformat(args['end_before'])
    assert end - start == timedelta(hours=1)
    assert abs((datetime.now(timezone.utc) - end).total_seconds()) < 5
    assert response.context['points'][0]['lat'] == 0
    assert 'Static debug points' not in response.text
    fetch.side_effect = None
    fetch.return_value = []
    assert 'No location records found' in client.get('/map').text
    fetch.side_effect = RuntimeError('Read unavailable')
    assert 'Unable to load locations' in client.get('/map').text
    client.post('/logout', follow_redirects=False)
    assert client.get('/map').status_code == 401


def test_map_filters(client, monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map', params={'user_id': ' walker ', 'start_time': '2026-09-11T14:43:00', 'end_time': '2026-09-11T14:57:00'})
    fetch.assert_called_once_with(limit=500, offset=0, locations_only=True, user_ids=['walker'], start_at='2026-09-11T14:43:00+00:00', end_before='2026-09-11T14:57:00+00:00')
    assert 'value="walker"' in response.text
    assert 'value="2026-09-11T14:43:00"' in response.text


@pytest.mark.parametrize('params', [
    {'start_time': 'bad'},
    {'start_time': '2026-09-11T15:00', 'end_time': '2026-09-11T14:00'},
    {'start_time': '2026-09-11T15:00', 'end_time': '2026-09-11T15:00'},
])
def test_map_invalid_filters(client, monkeypatch, params):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map', params=params)
    assert 'Unable to load locations' in response.text
    fetch.assert_not_called()


@pytest.mark.parametrize('field, expected', [('start_time', 'start_at'), ('end_time', 'end_before')])
def test_map_one_sided_time_filter(client, monkeypatch, field, expected):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    client.get('/map', params={field: '2026-09-11T14:00'})
    assert fetch.call_args.kwargs[expected] == '2026-09-11T14:00:00+00:00'


def test_log_pages_preserve_filters(client, monkeypatch):
    row = dict(id=1, occurred_at=None, received_at=None, payload=None)
    fetch = MagicMock(return_value=[row] * 101)
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/', params={'page': 2, 'users': 'a,b', 'log_type': 'location_reading'})
    assert len(response.context['logs']) == 100
    assert fetch.call_args.kwargs['offset'] == 100
    assert fetch.call_args.kwargs['limit'] == 101
    assert 'page=3' in response.context['older_url']
    assert 'users=a%2Cb' in response.context['older_url']
    assert 'page=1' in response.context['newer_url']
    fetch.return_value = [row]
    response = client.get('/?page=3')
    assert response.context['older_url'] is None
    assert response.context['newer_url'] is not None
    fetch.return_value = []
    response = client.get('/?page=4')
    assert response.context['newer_url'] is not None
    assert response.context['older_url'] is None


@pytest.mark.parametrize('page', ['0', '-1', 'oops'])
def test_invalid_log_page(client, monkeypatch, page):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    assert 'Page must be a positive whole number' in client.get('/', params={'page': page}).text
    fetch.assert_not_called()


@pytest.mark.parametrize('start,end,expected_start,expected_end', [
    ('2026-09-14T20:30:00-04:00', '2026-09-14T21:00:00-04:00', '2026-09-15T00:30:00+00:00', '2026-09-15T01:00:00+00:00'),
    ('2026-01-14T20:30:00-05:00', '2026-01-14T21:00:00-05:00', '2026-01-15T01:30:00+00:00', '2026-01-15T02:00:00+00:00'),
])
def test_map_local_time_offsets(client, monkeypatch, start, end, expected_start, expected_end):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map', params={'start_time': start, 'end_time': end})
    assert fetch.call_args.kwargs['start_at'] == expected_start
    assert fetch.call_args.kwargs['end_before'] == expected_end
    assert 'Start time (local, inclusive)' in response.text


def test_map_explicit_empty_times_remain_unrestricted(client, monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map?start_time=&end_time=')
    assert fetch.call_args.kwargs['start_at'] is None
    assert fetch.call_args.kwargs['end_before'] is None
    assert response.context['filters']['start_time'] == ''


def test_map_points_include_platform_in_label(client, monkeypatch):
    rows = [
        dict(lat=1, lng=1, occurred_at='2026-09-29T09:36:00Z', user_id='u', session_id='s1', platform='android'),
        dict(lat=2, lng=2, occurred_at='2026-09-29T09:37:00Z', user_id='u', session_id='s2', platform='ios'),
        dict(lat=3, lng=3, occurred_at='2026-09-29T09:38:00Z', user_id='u', session_id='s3', platform=None),
    ]
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['u'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', MagicMock(side_effect=[rows, []]))

    response = client.get('/map')

    points = response.context['points']
    platforms = {p['platform'] for p in points}
    assert platforms == {'android', 'ios', 'unknown'}
    android_point = next(p for p in points if p['platform'] == 'android')
    assert 'android' in android_point['display_label']
    # Same field the JS tooltip/list rebuild reads client-side (map.html),
    # server-rendered here so it's present even without JS.
    assert 'android' in response.text
    assert 'ios' in response.text
    assert 'unknown' in response.text


def test_map_fetches_multiple_batches_and_caps(client, monkeypatch):
    row = dict(lat=0, lng=0, occurred_at='2026-09-15T12:00:00Z', user_id='u', session_id='s')
    fetch = MagicMock(side_effect=[[row] * 500, [row] * 100, []])
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map')
    assert len(response.context['points']) == 600
    assert [call.kwargs['offset'] for call in fetch.call_args_list] == [0, 500, 600]
    fetch.reset_mock(side_effect=True)
    fetch.return_value = [row] * 500
    response = client.get('/map')
    assert len(response.context['points']) == 5000
    assert fetch.call_count == 10
    assert 'Narrow the time range' in response.text


def test_dropdown_multiple_users_and_pagination(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': ['location_reading']})
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/?users=a&users=b&page=2&log_type=custom')
    assert fetch.call_args.kwargs['user_ids'] == ['a', 'b']
    assert response.context['selected_users'] == ['a', 'b']
    assert 'users=a%2Cb' in response.context['newer_url']
    assert '<select id="log_type"' in response.text
    assert 'value="custom" selected' in response.text


def test_filter_options_batches_and_cache(monkeypatch):
    monkeypatch.setattr(supabase_client, '_filter_options_cache', None)
    monkeypatch.setattr(supabase_client, 'get_settings', lambda: SimpleNamespace(supabase_url='test', supabase_logs_table='activity_logs', supabase_key='test'))
    query = MagicMock()
    for method in ('select', 'order', 'limit', 'gt'):
        getattr(query, method).return_value = query
    query.execute.side_effect = [
        SimpleNamespace(data=[{'user_id': 'a'}, {'user_id': 'a'}]),
        SimpleNamespace(data=[{'user_id': 'b'}]), SimpleNamespace(data=[]),
        SimpleNamespace(data=[{'type': 'location_reading'}]), SimpleNamespace(data=[]),
    ]
    db = MagicMock()
    db.table.return_value = query
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)
    expected = {'user_id': ['a', 'b'], 'type': ['location_reading']}
    assert supabase_client.fetch_filter_options() == expected
    query.gt.assert_any_call('user_id', 'a')
    assert supabase_client.fetch_filter_options() == expected
    assert query.execute.call_count == 5


def test_map_multi_user_dropdown(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['a', 'b'], 'type': []})
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/map?user_id=a&user_id=b&start_time=&end_time=')
    assert fetch.call_args.kwargs['user_ids'] == ['a', 'b']
    assert fetch.call_args.kwargs['start_at'] is None
    assert response.context['selected_users'] == ['a', 'b']
    assert 'value="a" selected' in response.text
    assert 'value="b" selected' not in response.text
    monkeypatch.setattr(routes, 'fetch_filter_options', MagicMock(side_effect=RuntimeError('offline')))
    response = client.get('/map?user_id=older-user')
    assert 'value="older-user" selected' in response.text
    assert 'Could not load all user choices' in response.text


def test_map_passes_beacon_metadata(client, monkeypatch):
    row = dict(lat=1, lng=2, occurred_at='2026-10-06T12:00:00Z', user_id='u', session_id='s', type='upload', label='Beacon point queued', motion_state='still', note='<b>stop point</b>')
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['u'], 'type': []})
    monkeypatch.setattr(routes, 'fetch_recent_logs', MagicMock(side_effect=[[row], []]))
    response = client.get('/map')
    point = response.context['points'][0]
    for key in ('type', 'label', 'motion_state', 'note', 'occurred_at'):
        assert point[key] == row[key]
    assert '<b>stop point</b>' not in response.text
