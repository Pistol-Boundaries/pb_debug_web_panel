from unittest.mock import MagicMock

from app import routes
from test_activity_logs import client


def test_local_run_is_private_and_does_not_query_production(client, monkeypatch):
    fetch = MagicMock(side_effect=AssertionError('Local logs must not query production'))
    monkeypatch.setattr(routes, 'fetch_recent_logs', fetch)
    response = client.get('/local-run')
    assert response.status_code == 200
    assert 'id="file"' in response.text
    assert 'local_run_parser.js' in response.text
    assert 'id="basemap" checked' not in response.text
    fetch.assert_not_called()
    client.post('/logout', follow_redirects=False)
    assert client.get('/local-run').status_code == 401
