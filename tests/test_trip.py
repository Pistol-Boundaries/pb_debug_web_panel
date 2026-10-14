from unittest.mock import MagicMock

import pytest

from app import routes
from test_activity_logs import client


@pytest.fixture(autouse=True)
def options(monkeypatch):
    monkeypatch.setattr(routes, 'fetch_filter_options', lambda: {'user_id': ['walker'], 'type': []})


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


def test_trip_alerts_are_not_a_zero_count(client, monkeypatch):
    fetch = MagicMock()
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/trip', params={**PARAMS, 'tab': 'alerts'})
    assert 'Trip alert data is not connected yet' in response.text
    fetch.assert_not_called()


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
