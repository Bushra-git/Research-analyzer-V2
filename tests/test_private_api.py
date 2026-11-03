import os
from types import SimpleNamespace
import app as api

OWNER = 'guest:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
HEADERS = {'X-Internal-Token': os.environ['INTERNAL_API_TOKEN'], 'X-Owner-Key': OWNER}
JOB = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

def test_direct_flask_access_denied():
    assert api.app.test_client().get('/status/' + JOB).status_code == 401
    assert api.app.test_client().post('/analyze').status_code == 401

def test_job_owner_is_enforced(monkeypatch):
    job = SimpleNamespace(meta={'owner_key': 'guest:someoneelse'})
    monkeypatch.setattr(api.Job, 'fetch', lambda *a, **k: job)
    response = api.app.test_client().get('/status/' + JOB, headers=HEADERS)
    assert response.status_code == 404

def test_matching_excerpt_never_leaves_private_service(monkeypatch):
    job = SimpleNamespace(id=JOB, meta={'owner_key': OWNER}, is_finished=True, is_failed=False,
        get_status=lambda: 'finished', result={'summary': 'public to owner', '_matching_text': 'private manuscript'})
    monkeypatch.setattr(api.Job, 'fetch', lambda *a, **k: job)
    monkeypatch.setattr(api.redis_connection, 'exists', lambda *a: False)
    response = api.app.test_client().get('/status/' + JOB, headers=HEADERS)
    assert response.status_code == 200
    assert response.json['result'] == {'summary': 'public to owner'}

def test_legacy_sync_route_is_retired():
    assert api.app.test_client().post('/predict', headers=HEADERS).status_code == 410

def test_local_mode_never_calls_external_search(monkeypatch):
    import reference_papers_similarity as references
    monkeypatch.setattr(references, '_load_reference_rows', lambda: [])
    def external(*a): raise AssertionError('External search must not run')
    monkeypatch.setattr(references, '_external_rows', external)
    assert references.find_reference_papers('private research', external_search=False)['papers'] == []
