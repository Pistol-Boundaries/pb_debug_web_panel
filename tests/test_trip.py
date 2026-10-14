from unittest.mock import MagicMock

import pytest

from app import routes
from test_activity_logs import client


@pytest.fixture(autouse=True)
def options(monkeypatch):
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['walker'], 'type': []})
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_scopes', lambda: ['location', 'jurisdiction'])


def test_trip_requires_selection_and_auth(client, monkeypatch):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip')
    assert 'Start with a user and date range' in response.text
    fetch.assert_not_called()
    client.post('/logout', follow_redirects=False)
    assert client.get('/trip').status_code == 401


PARAMS = {'user_id': 'walker', 'start_date': '2026-10-01', 'end_date': '2026-10-02'}


def test_trip_map_boundaries_and_order(client, monkeypatch):
    fetch = MagicMock(side_effect=[[
        {'lat': 1, 'lng': 2, 'occurred_at': '2026-10-02T12:00:00Z'},
        {'lat': 0, 'lng': 0, 'occurred_at': '2026-10-01T12:00:00Z'},
    ], []])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params=PARAMS)
    assert response.status_code == 200
    assert response.context['points'][0]['lat'] == 0
    fetch.assert_any_call(limit=500, offset=0, locations_only=True, user_ids=['walker'],
                          start_at='2026-10-01T00:00:00+00:00', end_before='2026-10-03T00:00:00+00:00')
    assert 'user_id=walker' in response.context['tab_urls']['logs']
    assert 'end_date=2026-10-02' in response.context['tab_urls']['alerts']


@pytest.mark.parametrize('params', [
    {'user_id': ''}, {'start_date': 'bad'}, {'end_date': '2026-09-01'}, {'page': '0'}, {'end_date': '9999-12-31'},
])
def test_trip_invalid_filters_never_query(client, monkeypatch, params):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    assert 'Unable to load trip' in client.get('/trip', params={**PARAMS, **params}).text
    fetch.assert_not_called()


def test_trip_logs_pagination_and_escaping(client, monkeypatch):
    row = {'label': '<script>bad()</script>', 'payload': {'nested': False}}
    fetch = MagicMock(return_value=[row] * 101)
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params={**PARAMS, 'tab': 'logs', 'page': '2'})
    assert fetch.call_args.kwargs['offset'] == 100
    assert len(response.context['logs']) == 100
    assert 'page=3' in response.context['older_url']
    assert '<script>bad()</script>' not in response.text
    assert '&lt;script&gt;' in response.text


def test_trip_alerts_empty(client, monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_trip_alerts', fetch)
    response = client.get('/trip', params={**PARAMS, 'tab': 'alerts'})
    assert 'No alerts on this page' in response.text
    assert 'Coming soon' not in response.text
    fetch.assert_called_once_with(user_id='walker', start_at='2026-10-01T00:00:00+00:00',
                                  end_before='2026-10-03T00:00:00+00:00', limit=101, offset=0, scopes=None)


def test_trip_truncation_and_fetch_error(client, monkeypatch):
    row = {'lat': 1, 'lng': 2}
    fetch = MagicMock(side_effect=lambda **kw: [row] * kw['limit'])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params=PARAMS)
    assert len(response.context['points']) == 5000
    assert 'Showing the latest 5,000' in response.text
    fetch.side_effect = RuntimeError('Unavailable')
    assert 'Unable to load trip' in client.get('/trip', params=PARAMS).text


def test_trip_multiple_log_types_and_navigation(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    fetch = MagicMock(return_value=[{'type': 'location'}] * 101)
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params={**PARAMS, 'tab': 'logs', 'page': '2',
                                         'log_type': ['location', 'upload', 'location']})
    assert fetch.call_args.kwargs['log_type'] == ['location', 'upload']
    assert 'value="upload" checked' in response.text
    assert '2 selected' in response.text
    for url in [*response.context['tab_urls'].values(), response.context['newer_url'], response.context['older_url']]:
        params = parse_qs(urlparse(url).query)
        assert params['log_type'] == ['location', 'upload']
        assert params['user_id'] == ['walker']
        assert params['start_date'] == [PARAMS['start_date']]
    fetch.return_value = []
    response = client.get('/trip', params={**PARAMS, 'tab': 'logs'})
    assert fetch.call_args.kwargs['log_type'] is None
    assert response.context['page'] == 1


def test_trip_map_preserves_log_filter_without_filtering_locations(client, monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params={**PARAMS, 'log_type': ['upload', 'location']})
    assert 'log_type' not in fetch.call_args.kwargs
    assert 'type="hidden" name="log_type" value="upload"' in response.text


def test_trip_selected_types_survive_options_failure(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_recent_logs', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_filter_options', MagicMock(side_effect=RuntimeError('Unavailable')))
    response = client.get('/trip', params={**PARAMS, 'tab': 'logs', 'log_type': ['custom', 'upload']})
    assert 'value="custom" checked' in response.text
    assert 'Filter choices could not be loaded' in response.text


def test_trip_default_three_hours(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip')
    filters = response.context['filters']
    start, end = [datetime.fromisoformat(filters[key]) for key in ('start_time', 'end_time')]
    assert end - start == timedelta(hours=3)
    assert abs((datetime.now(timezone.utc) - end).total_seconds()) < 5
    fetch.assert_not_called()
    client.get('/trip?user_id=walker')
    assert fetch.call_args.kwargs['start_at'] is not None


def test_trip_exact_times_and_links(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    fetch = MagicMock(return_value=[{'type': 'upload'}] * 101)
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params={'user_id': 'walker', 'tab': 'logs', 'start_time': '2026-10-14T10:15:23-04:00', 'end_time': '2026-10-14T11:16:24-04:00', 'log_type': ['upload', 'location']})
    args = fetch.call_args.kwargs
    assert args['start_at'] == '2026-10-14T14:15:23+00:00'
    assert args['end_before'] == '2026-10-14T15:16:24+00:00'
    for url in [response.context['older_url'], *response.context['tab_urls'].values()]:
        params = parse_qs(urlparse(url).query)
        assert params['start_time'] == [args['start_at']]
        assert params['end_time'] == [args['end_before']]
    assert 'type="datetime-local" step="1"' in response.text


@pytest.mark.parametrize('start,end', [('', ''), ('bad', 'bad'), ('2026-10-14T12:00', '2026-10-14T12:00'), ('2026-10-14T13:00', '2026-10-14T12:00')])
def test_trip_invalid_exact_bounds(client, monkeypatch, start, end):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params={'user_id': 'walker', 'start_time': start, 'end_time': end})
    assert 'Unable to load trip' in response.text
    fetch.assert_not_called()


def test_trip_alerts_pagination_metadata_and_escaping(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    rows = [{'id': i, 'created_at': '2026-10-01T12:00:00Z', 'decision': 'sent' if i % 2 else 'suppressed',
             'name': '<script>bad()</script>', 'suppressed_reason': 'muted', 'source': 'radar',
             'event_metadata': {'nested': {'enabled': False}}} for i in range(101)]
    fetch = MagicMock(return_value=rows)
    monkeypatch.setattr(routes, 'fetch_trip_alerts', fetch)
    logs = MagicMock()
    monkeypatch.setattr(routes, 'fetch_recent_logs', logs)
    response = client.get('/trip', params={**PARAMS, 'tab': 'alerts', 'page': '2', 'log_type': ['upload', 'location']})
    assert len(response.context['alerts']) == 100
    assert fetch.call_args.kwargs['offset'] == 100
    logs.assert_not_called()
    assert 'sent' in response.text and 'suppressed' in response.text
    assert '&lt;script&gt;bad()&lt;/script&gt;' in response.text
    assert '<script>bad()</script>' not in response.text
    assert '"enabled": false' in response.text
    for key, page in [('newer_url', '1'), ('older_url', '3')]:
        params = parse_qs(urlparse(response.context[key]).query)
        assert params['tab'] == ['alerts']
        assert params.get('page', ['1']) == [page]
        assert params['user_id'] == ['walker']
        assert params['log_type'] == ['upload', 'location']
    fetch.return_value = rows[:1]
    assert client.get('/trip', params={**PARAMS, 'tab': 'alerts'}).context['older_url'] is None


def test_trip_alerts_failure_and_invalid_bounds(client, monkeypatch):
    fetch = MagicMock(side_effect=RuntimeError('Alert read unavailable'))
    monkeypatch.setattr(routes, 'fetch_trip_alerts', fetch)
    response = client.get('/trip', params={**PARAMS, 'tab': 'alerts'})
    assert 'Alert read unavailable' in response.text
    assert 'No alerts on this page' not in response.text
    fetch.reset_mock()
    client.get('/trip', params={**PARAMS, 'tab': 'alerts', 'start_time': 'bad', 'end_time': 'bad'})
    fetch.assert_not_called()
    client.post('/logout', follow_redirects=False)
    assert client.get('/trip', params={**PARAMS, 'tab': 'alerts'}).status_code == 401
    fetch.assert_not_called()


def test_alert_query_uses_user_time_bounds_and_stable_pagination(monkeypatch):
    from types import SimpleNamespace
    from app import supabase_client
    query = MagicMock()
    for method in ('select', 'eq', 'gte', 'lt', 'order', 'range'):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[{'id': 1}])
    db = MagicMock()
    db.table.return_value = query
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)
    assert supabase_client.fetch_trip_alerts('walker', 'start', 'end', offset=100) == [{'id': 1}]
    db.table.assert_called_once_with('alerts')
    query.eq.assert_called_once_with('user_id', 'walker')
    query.gte.assert_called_once_with('created_at', 'start')
    query.lt.assert_called_once_with('created_at', 'end')
    query.range.assert_called_once_with(100, 200)
    assert query.order.call_args_list[0].args == ('created_at',)
    assert query.order.call_args_list[1].args == ('id',)
    assert 'event_metadata' in query.select.call_args.args[0]


def test_trip_scope_filter_and_navigation(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    fetch = MagicMock(return_value=[{'alert_scope': 'location'}] * 101)
    monkeypatch.setattr(routes, 'fetch_trip_alerts', fetch)
    response = client.get('/trip', params={**PARAMS, 'tab': 'alerts', 'page': 2,
                                         'alert_scope': ['location', 'jurisdiction', 'location']})
    assert fetch.call_args.kwargs['scopes'] == ['location', 'jurisdiction']
    assert 'value="jurisdiction" checked' in response.text
    for url in [*response.context['tab_urls'].values(), response.context['older_url'], response.context['newer_url']]:
        assert parse_qs(urlparse(url).query)['alert_scope'] == ['location', 'jurisdiction']
    fetch.return_value = []
    client.get('/trip', params={**PARAMS, 'tab': 'alerts', 'alert_scope': ''})
    assert fetch.call_args.kwargs['scopes'] is None
    monkeypatch.setattr(routes, 'fetch_recent_logs', lambda **kwargs: [])
    response = client.get('/trip', params={**PARAMS, 'tab': 'logs', 'alert_scope': 'location'})
    assert 'type="hidden" name="alert_scope" value="location"' in response.text


def test_trip_scope_options_failure_keeps_selection(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_scopes', MagicMock(side_effect=RuntimeError('Unavailable')))
    monkeypatch.setattr(routes, 'fetch_trip_alerts', lambda **kwargs: [])
    response = client.get('/trip', params={**PARAMS, 'tab': 'alerts', 'alert_scope': 'location'})
    assert 'value="location" checked' in response.text
    assert 'Some filter choices could not be loaded' in response.text


def test_alert_query_scope_union(monkeypatch):
    from types import SimpleNamespace
    from app import supabase_client
    query = MagicMock()
    for method in ('select', 'eq', 'gte', 'lt', 'order', 'range', 'in_'):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    db = MagicMock()
    db.table.return_value = query
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)
    supabase_client.fetch_trip_alerts('walker', 'start', 'end', scopes=['location', 'jurisdiction'])
    query.in_.assert_called_once_with('alert_scope', ['location', 'jurisdiction'])
    query.in_.reset_mock()
    supabase_client.fetch_trip_alerts('walker', 'start', 'end')
    query.in_.assert_not_called()
