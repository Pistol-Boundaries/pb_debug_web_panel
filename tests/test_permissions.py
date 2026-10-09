from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app import routes


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


def _row(user_id, occurred_at, **payload):
    base = {'location': 'always', 'precise_location': True, 'notifications': True,
            'motion': 'granted', 'trigger': 'boot'}
    base.update(payload)
    return {'user_id': user_id, 'occurred_at': occurred_at, 'platform': 'ios',
            'app_version': '1.2.6', 'payload': base}


def test_permission_rows_keep_latest_per_user():
    logs = [  # newest first, as fetch_recent_logs returns them
        _row('u1', '2026-10-08T10:00:00Z', motion='denied', trigger='resume'),
        _row('u1', '2026-10-08T09:00:00Z'),
        _row('u2', '2026-10-08T08:00:00Z', location='while_using'),
    ]

    rows = routes._permission_rows(logs)

    assert [r['user_id'] for r in rows] == ['u1', 'u2']
    assert rows[0]['motion'] == {'text': 'denied', 'tone': 'serious'}
    assert rows[0]['trigger'] == 'resume'
    assert rows[1]['location'] == {'text': 'while_using', 'tone': 'warning'}


def test_permission_row_tones():
    [row] = routes._permission_rows([
        _row('u1', '2026-10-08T10:00:00Z', location='denied', precise_location=False,
             notifications=None, motion=None),
    ])
    assert row['location']['tone'] == 'critical'
    assert row['precise'] == {'text': 'off', 'tone': 'warning'}
    assert row['notifications'] == {'text': '-', 'tone': 'neutral'}
    assert row['motion'] == {'text': '-', 'tone': 'neutral'}
    assert 'log_type=permission_state' in row['logs_url']


def test_permissions_page_renders_summary(client, monkeypatch):
    calls = {}

    def fake_fetch(**kwargs):
        calls.update(kwargs)
        return [
            _row('u1', '2026-10-08T10:00:00Z'),
            _row('u2', '2026-10-08T09:00:00Z', location='while_using', motion='denied',
                 notifications=False),
        ]

    monkeypatch.setattr(routes, 'fetch_recent_logs', fake_fetch)

    response = client.get('/permissions')

    assert response.status_code == 200
    assert calls['log_type'] == 'permission_state'
    assert '2 users &middot; 1 on Always' in response.text
    assert '1 with motion granted' in response.text
    assert 'perm-badge tone-serious' in response.text


def test_permissions_page_empty_and_error(client, monkeypatch):
    monkeypatch.setattr(routes, 'fetch_recent_logs', lambda **_: [])
    assert 'No permission_state rows yet' in client.get('/permissions').text

    def boom(**_):
        raise RuntimeError('db down')

    monkeypatch.setattr(routes, 'fetch_recent_logs', boom)
    response = client.get('/permissions')
    assert response.status_code == 200
    assert 'Unable to load permission states' in response.text
