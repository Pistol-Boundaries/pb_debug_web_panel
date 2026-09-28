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

    db.rpc.assert_called_once_with(
        'scoreboard_alert_breakdown',
        {'p_from': None, 'p_to': None, 'p_version': None, 'p_exclude_debug_user': True},
    )
    assert result == [{'decision': 'sent', 'alert_count': 5}]


def test_fetch_scoreboard_missed_alert_summary_calls_rpc(monkeypatch):
    rpc = MagicMock()
    rpc.execute.return_value = SimpleNamespace(data=[{'alert_scope': 'location', 'report_count': 3}])
    db = MagicMock()
    db.rpc.return_value = rpc
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)

    result = supabase_client.fetch_scoreboard_missed_alert_summary()

    db.rpc.assert_called_once_with(
        'scoreboard_missed_alert_summary',
        {'p_from': None, 'p_to': None, 'p_exclude_debug_user': True},
    )
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
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: breakdown)
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])

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
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: breakdown)
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])

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


def test_scoreboard_route_passes_filters_to_fetch_functions(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        routes, 'fetch_scoreboard_alert_breakdown',
        lambda **kwargs: calls.append(('breakdown', kwargs)) or [],
    )
    monkeypatch.setattr(
        routes, 'fetch_scoreboard_missed_alert_summary',
        lambda **kwargs: calls.append(('missed', kwargs)) or [],
    )
    monkeypatch.setattr(
        routes, 'fetch_scoreboard_missed_alert_classification',
        lambda **kwargs: calls.append(('classification', kwargs)) or [],
    )

    response = client.get(
        '/scoreboard',
        params={
            'start_date': '2026-09-01',
            'end_date': '2026-09-02',
            'version': '0.2',
            'include_debug_user': 'on',
        },
    )

    assert response.status_code == 200
    breakdown_kwargs = next(kwargs for name, kwargs in calls if name == 'breakdown')
    assert breakdown_kwargs['from_at'] == '2026-09-01T00:00:00+00:00'
    assert breakdown_kwargs['to_before'] == '2026-09-03T00:00:00+00:00'
    assert breakdown_kwargs['version'] == 0.2
    assert breakdown_kwargs['exclude_debug_user'] is False
    # Form reflects the submitted filters back (not just defaults).
    assert 'value="2026-09-01"' in response.text
    assert 'value="0.2"' in response.text
    assert 'checked' in response.text


def test_scoreboard_route_rejects_start_after_end(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])

    response = client.get(
        '/scoreboard',
        params={'start_date': '2026-09-05', 'end_date': '2026-09-01'},
    )

    assert response.status_code == 200
    assert 'Start date must be on or before end date.' in response.text


def test_scoreboard_route_rejects_non_numeric_version(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])

    response = client.get('/scoreboard', params={'version': 'not-a-number'})

    assert response.status_code == 200
    assert 'Version must be a number' in response.text


def test_scoreboard_route_defaults_exclude_debug_user_on_fresh_visit(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        routes, 'fetch_scoreboard_alert_breakdown',
        lambda **kwargs: calls.append(kwargs) or [],
    )
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])

    response = client.get('/scoreboard')

    assert response.status_code == 200
    assert calls[0]['exclude_debug_user'] is True


def test_scoreboard_route_renders_version_dropdown_from_db(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_versions', lambda: ['0.1', '0.2'])

    response = client.get('/scoreboard', params={'version': '0.2'})

    assert response.status_code == 200
    assert '<option value="">All versions</option>' in response.text
    assert '<option value="0.1" >0.1</option>' in response.text
    assert '<option value="0.2" selected>0.2</option>' in response.text


def test_scoreboard_route_keeps_stale_selected_version_in_options(client, monkeypatch):
    # A version that's no longer in the DB (e.g. bookmarked URL) still
    # shows as selected rather than silently resetting to "All versions".
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_versions', lambda: ['0.2'])

    response = client.get('/scoreboard', params={'version': '0.1'})

    assert response.status_code == 200
    assert '<option value="0.1" selected>0.1</option>' in response.text


def test_scoreboard_route_falls_back_when_versions_fetch_fails(client, monkeypatch):
    def boom():
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_versions', boom)

    response = client.get('/scoreboard')

    assert response.status_code == 200
    assert '<option value="">All versions</option>' in response.text


def test_fetch_scoreboard_missed_alert_classification_calls_rpc(monkeypatch):
    rpc = MagicMock()
    rpc.execute.return_value = SimpleNamespace(
        data=[{'alert_scope': 'location', 'classification': 'suppressed_by_rule', 'report_count': 2}]
    )
    db = MagicMock()
    db.rpc.return_value = rpc
    monkeypatch.setattr(supabase_client, 'get_supabase_client', lambda: db)

    result = supabase_client.fetch_scoreboard_missed_alert_classification()

    db.rpc.assert_called_once_with(
        'scoreboard_missed_alert_classification',
        {'p_from': None, 'p_to': None, 'p_exclude_debug_user': True},
    )
    assert result == [{'alert_scope': 'location', 'classification': 'suppressed_by_rule', 'report_count': 2}]


def test_scoreboard_route_groups_missed_alert_classification_with_distinct_tones(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(
        routes, 'fetch_scoreboard_missed_alert_classification',
        lambda **kwargs: [
            {'alert_scope': 'location', 'classification': 'suppressed_by_rule', 'report_count': 2},
            {'alert_scope': 'jurisdiction', 'classification': 'no_event_received', 'report_count': 16},
            {'alert_scope': 'location', 'classification': 'no_event_received', 'report_count': 24},
        ],
    )

    response = client.get('/scoreboard')

    assert response.status_code == 200
    # Suppressed-by-rule group heading appears before no-event-received.
    suppressed_idx = response.text.index('Suppressed by Rule')
    no_event_idx = response.text.index('No Event Received')
    assert suppressed_idx < no_event_idx
    assert 'tone-critical' in response.text
    assert 'tone-warning' in response.text
    # alert_sent bucket absent from this fixture -> no serious-tone group rendered.
    assert 'Alert Was Sent' not in response.text
    # No-event-received scope bars sorted largest first (Location 24 before Jurisdiction 16).
    location_idx = response.text.index('Location', no_event_idx)
    jurisdiction_idx = response.text.index('Jurisdiction', no_event_idx)
    assert location_idx < jurisdiction_idx


def test_scoreboard_route_shows_empty_state_with_no_missed_classification(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_scoreboard_alert_breakdown', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_summary', lambda **kwargs: [])
    monkeypatch.setattr(routes, 'fetch_scoreboard_missed_alert_classification', lambda **kwargs: [])

    response = client.get('/scoreboard')

    assert response.status_code == 200
    assert 'Missed-alert outcomes' in response.text
