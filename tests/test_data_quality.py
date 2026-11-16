"""PB-624 Data Quality page: logic and rendering, with the dq_* fetches faked
so no Supabase connection is needed."""
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


def _fake_fetches(monkeypatch, **overrides):
    data = {
        'fetch_dq_locations_by_data_source': lambda: [
            {'data_source': 'Texas Bars', 'locations': 1200},
            {'data_source': '(none)', 'locations': 34},
        ],
        'fetch_dq_duplicate_place_ids': lambda: [
            {'place_id': 'ChIJabc', 'copies': 2, 'names': ['Lucky Break Saloon', 'Lucky Break Saloon'],
             'sources': ['Texas Bars', 'Texas Bars']},
        ],
        'fetch_dq_jurisdictions_missing_geofence': lambda: [
            {'id': '06999', 'name': 'Nowhere', 'type': 'county', 'parent_id': '06'},
        ],
        'fetch_dq_jurisdictions_without_topics': lambda: [
            {'id': '06041', 'name': 'Marin', 'type': 'county', 'parent_id': '06'},
            {'id': '06073', 'name': 'San Diego', 'type': 'county', 'parent_id': '06'},
            {'id': '0803455000', 'name': 'Denver', 'type': 'city', 'parent_id': '08031'},
        ],
        'fetch_dq_locations_by_status': lambda: [
            {'status': 'prohibited', 'data_source': 'Iowa Casinos', 'locations': 19},
            {'status': 'pending', 'data_source': 'Texas Bars', 'locations': 1200},
            {'status': 'allowed', 'data_source': 'Texas Bars', 'locations': 15},
            {'status': 'mystery', 'data_source': 'Manual', 'locations': 2},
        ],
        'fetch_dq_child_locations_without_parent': lambda: [
            {'id': 'loc-9', 'name': 'Orphan Snack Bar', 'data_source': 'Manual',
             'place_id': 'ChIJorphan', 'status': 'pending'},
        ],
        'fetch_dq_multipart_geofences_by_source': lambda: [
            {'parts': 2, 'data_source': 'Florida Bars', 'locations': 600, 'most_parts': 2},
            {'parts': 2, 'data_source': 'Federal Buildings', 'locations': 300, 'most_parts': 2},
            {'parts': 6, 'data_source': 'Florida Bars', 'locations': 4, 'most_parts': 6},
            {'parts': 7, 'data_source': 'Florida Bars', 'locations': 1, 'most_parts': 7},
            {'parts': 54, 'data_source': 'Universities and Colleges', 'locations': 1, 'most_parts': 54},
        ],
        'fetch_dq_locations_with_parent_not_child': lambda: [
            {'id': 'loc-1', 'name': 'Gift Shop', 'classification': 'location', 'data_source': 'Manual',
             'parent_id': 'loc-0', 'parent_name': 'State Fairgrounds'},
        ],
    }
    data.update(overrides)
    for name, fake in data.items():
        monkeypatch.setattr(routes, name, fake)


def test_layer_counts_show_every_layer_in_order():
    layers = routes._jurisdiction_layer_counts([
        {'type': 'county'}, {'type': 'county'}, {'type': 'city'},
    ])
    assert layers == [
        {'label': 'Federal', 'count': 0},
        {'label': 'States', 'count': 0},
        {'label': 'Counties', 'count': 2},
        {'label': 'Cities', 'count': 1},
    ]


def test_layer_counts_append_unknown_types():
    layers = routes._jurisdiction_layer_counts([{'type': 'tribal'}, {'type': None}])
    labels = [layer['label'] for layer in layers]
    assert labels[:4] == ['Federal', 'States', 'Counties', 'Cities']
    assert 'Tribal' in labels and 'Unknown' in labels


def test_layer_counts_can_leave_out_federal():
    layers = routes._jurisdiction_layer_counts([{'type': 'county'}, {'type': 'federal'}], include_federal=False)
    assert [layer['label'] for layer in layers] == ['States', 'Counties', 'Cities']
    assert layers[1]['count'] == 1


def test_join_values():
    assert routes._join_values(['a', 'b']) == 'a, b'
    assert routes._join_values([]) == '-'
    assert routes._join_values(None) == '-'


def test_status_bars_order_tone_and_width():
    bars = routes._status_bars([
        {'status': 'prohibited', 'locations': 50},
        {'status': 'pending', 'locations': 100},
        {'status': 'allowed', 'locations': 20},
        {'status': 'allowed', 'locations': 5},
        {'status': 'mystery', 'locations': 1},
    ])
    assert [b['label'] for b in bars] == ['allowed', 'prohibited', 'pending', 'mystery']
    assert bars[0] == {'label': 'allowed', 'count': 25, 'pct': 25.0, 'tone': 'good'}
    assert bars[1]['tone'] == 'critical'
    assert bars[2]['pct'] == 100.0 and bars[2]['tone'] == 'neutral'


def test_status_bars_empty():
    assert routes._status_bars([]) == []


def test_geofence_part_buckets():
    assert routes._geofence_part_bucket(2) == '2'
    assert routes._geofence_part_bucket(4) == '4'
    assert routes._geofence_part_bucket(5) == '5-9'
    assert routes._geofence_part_bucket(9) == '5-9'
    assert routes._geofence_part_bucket(10) == '10+'
    assert routes._geofence_part_bucket(54) == '10+'


def test_multipart_bars_and_rows():
    rows = [
        {'parts': 6, 'data_source': 'Florida Bars', 'locations': 4, 'most_parts': 6},
        {'parts': 7, 'data_source': 'Florida Bars', 'locations': 1, 'most_parts': 7},
        {'parts': 2, 'data_source': 'Federal Buildings', 'locations': 300, 'most_parts': 2},
        {'parts': 2, 'data_source': 'Florida Bars', 'locations': 600, 'most_parts': 2},
    ]
    bars = routes._multipart_bars(rows)
    assert [b['key'] for b in bars] == ['2', '5-9']          # empty buckets left out, in order
    assert bars[0] == {'key': '2', 'label': '2 parts', 'count': 900, 'pct': 100.0}
    assert bars[1]['count'] == 5

    drill = routes._multipart_rows(rows)
    assert [(r['key'], r['data_source']) for r in drill] == [
        ('2', 'Florida Bars'), ('2', 'Federal Buildings'), ('5-9', 'Florida Bars'),
    ]
    assert drill[2]['locations'] == 5 and drill[2]['most_parts'] == 7   # 6- and 7-part rows merged


def test_multipart_empty():
    assert routes._multipart_bars([]) == []
    assert routes._multipart_rows([]) == []


def test_tab_selection_defaults_to_locations():
    assert routes._data_quality_tab(None) == 'locations'
    assert routes._data_quality_tab('jurisdictions') == 'jurisdictions'
    assert routes._data_quality_tab('nonsense') == 'locations'


def test_locations_context_totals(monkeypatch):
    _fake_fetches(monkeypatch)
    context = routes._data_quality_context('locations')
    assert context['errors'] == {}
    assert context['total_locations'] == 1234
    assert context['duplicate_count'] == 1
    assert context['duplicate_rows'][0]['names'] == 'Lucky Break Saloon, Lucky Break Saloon'
    assert context['parent_not_child_count'] == 1
    assert context['child_no_parent_count'] == 1
    assert context['child_no_parent_rows'][0]['place_id'] == 'ChIJorphan'
    assert context['multipart_total'] == 906
    assert 'no_topics_rows' not in context


def test_each_tab_only_runs_its_own_checks(monkeypatch):
    def must_not_run():
        raise AssertionError('ran a check from the other tab')

    _fake_fetches(
        monkeypatch,
        fetch_dq_jurisdictions_without_topics=must_not_run,
        fetch_dq_jurisdictions_missing_geofence=must_not_run,
    )
    assert routes._data_quality_context('locations')['errors'] == {}

    _fake_fetches(
        monkeypatch,
        fetch_dq_locations_by_data_source=must_not_run,
        fetch_dq_duplicate_place_ids=must_not_run,
        fetch_dq_locations_with_parent_not_child=must_not_run,
        fetch_dq_locations_by_status=must_not_run,
        fetch_dq_child_locations_without_parent=must_not_run,
        fetch_dq_multipart_geofences_by_source=must_not_run,
    )
    context = routes._data_quality_context('jurisdictions')
    assert context['errors'] == {}
    assert [layer['count'] for layer in context['no_topics_layers']] == [0, 0, 2, 1]


def test_locations_tab_is_the_default(client, monkeypatch):
    _fake_fetches(monkeypatch)
    response = client.get('/data-quality')
    assert response.status_code == 200
    text = response.text
    assert 'Data Quality' in text
    assert 'href="/data-quality?tab=locations" aria-current="page"' in text
    assert '1,234' in text                        # total locations
    assert 'Texas Bars' in text                   # by-source drill-down
    assert 'ChIJabc' in text                      # duplicate drill-down
    assert 'State Fairgrounds' in text            # parent name in drill-down
    assert 'Child locations without a parent' in text
    assert 'Orphan Snack Bar' in text             # child-without-parent drill-down
    assert 'Geofences with multiple parts' in text
    assert 'data-parts="10+" role="button"' in text           # clickable parts bar
    assert '<tr data-parts="5-9">' in text                    # filterable parts row
    assert 'Universities and Colleges' in text
    assert 'Locations by status' in text
    assert 'bar-fill tone-critical' in text       # prohibited bar
    assert 'Iowa Casinos' in text                 # status drill-down
    assert 'data-status="prohibited" role="button"' in text   # clickable bar
    assert '<tr data-status="prohibited">' in text            # filterable row
    assert '/static/data_quality.js' in text
    assert 'Jurisdictions without topics' not in text


def test_jurisdictions_tab(client, monkeypatch):
    _fake_fetches(monkeypatch)
    text = client.get('/data-quality?tab=jurisdictions').text
    assert 'href="/data-quality?tab=jurisdictions" aria-current="page"' in text
    assert 'Jurisdictions without topics' in text
    assert 'Counties' in text and 'Federal' in text
    assert 'San Diego' in text                    # jurisdictions drill-down
    assert 'Jurisdictions missing a geofence' in text
    assert 'Nowhere' in text                      # missing geofence drill-down
    assert 'Duplicate place IDs' not in text


def test_unknown_tab_falls_back_to_locations(client, monkeypatch):
    _fake_fetches(monkeypatch)
    text = client.get('/data-quality?tab=bogus').text
    assert 'href="/data-quality?tab=locations" aria-current="page"' in text


def test_one_failing_check_does_not_hide_the_others(client, monkeypatch):
    def boom():
        raise RuntimeError('function missing')

    _fake_fetches(monkeypatch, fetch_dq_duplicate_place_ids=boom)
    response = client.get('/data-quality')
    assert response.status_code == 200
    assert 'Unable to load duplicate place IDs' in response.text
    assert 'function missing' in response.text
    assert '1,234' in response.text               # other sections still render


def test_empty_results(client, monkeypatch):
    _fake_fetches(
        monkeypatch,
        fetch_dq_duplicate_place_ids=lambda: [],
        fetch_dq_jurisdictions_without_topics=lambda: [],
        fetch_dq_jurisdictions_missing_geofence=lambda: [],
        fetch_dq_locations_with_parent_not_child=lambda: [],
        fetch_dq_child_locations_without_parent=lambda: [],
        fetch_dq_multipart_geofences_by_source=lambda: [],
    )
    locations_text = client.get('/data-quality').text
    assert 'No duplicated place IDs.' in locations_text
    assert 'No child locations missing a parent.' in locations_text
    assert 'No geofences with multiple parts.' in locations_text
    jurisdictions_text = client.get('/data-quality?tab=jurisdictions').text
    assert 'Every jurisdiction has topics.' in jurisdictions_text
    assert 'Every jurisdiction has a geofence.' in jurisdictions_text


def test_requires_login(monkeypatch):
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only")
    app.include_router(routes.router)
    _fake_fetches(monkeypatch)
    with TestClient(app) as anon:
        response = anon.get('/data-quality')
    assert response.status_code == 401
