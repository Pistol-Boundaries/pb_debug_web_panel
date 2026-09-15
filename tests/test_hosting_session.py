from fastapi.testclient import TestClient


def test_firebase_session_and_private_pages(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY', 'test-key')
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app
    from app import routes
    monkeypatch.setattr(routes, 'fetch_recent_logs', lambda **kwargs: [])
    with TestClient(app) as client:
        assert client.get('/').status_code == 401
        login = client.post('/login', data={'password': get_settings().app_password}, follow_redirects=False)
        assert '__session=' in login.headers['set-cookie']
        page = client.get('/')
        assert page.status_code == 200
        assert page.headers['cache-control'] == 'private, no-store'
        client.post('/logout', follow_redirects=False)
        assert client.get('/').status_code == 401
    get_settings.cache_clear()


def test_stylesheet_uses_same_origin_behind_proxy(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY', 'test-key')
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app, base_url='http://internal-cloud-run.example') as client:
        page = client.get('/')
        assert 'href="/static/styles.css?' in page.text
        assert 'http://internal-cloud-run.example/static/' not in page.text
        css = client.get('/static/styles.css')
        assert css.status_code == 200
        assert 'text/css' in css.headers['content-type']
        assert '.pagination' in css.text
    get_settings.cache_clear()
