import json
from types import SimpleNamespace
import pytest
import analysis_tasks as tasks
import queue_resources
import rq

class FakeRedis:
    def __init__(self, values): self.values = dict(values)
    def get(self, key): return self.values.get(key)
    def exists(self, key): return key in self.values
    def delete(self, key): self.values.pop(key, None)
    def eval(self, script, count, key, tombstone, ttl, value):
        if tombstone not in self.values: self.values[key] = value

def test_private_cache_hit_removes_uploaded_bytes(monkeypatch):
    cache = FakeRedis({'upload:job': b'%PDF', 'private-cache': json.dumps({'features': {}, 'summary': 'cached'})})
    monkeypatch.setattr(queue_resources, 'redis_connection', cache)
    monkeypatch.setattr(rq, 'get_current_job', lambda: SimpleNamespace(meta={'cache_key': 'private-cache', 'owner_key': 'guest:a'}))
    monkeypatch.setattr(tasks, 'persist_completion', lambda *a: None)
    result = tasks.process_uploaded_paper('job', 'renamed.pdf')
    assert result['cached'] is True and result['file_name'] == 'renamed.pdf'
    assert 'upload:job' not in cache.values

def test_failed_analysis_removes_bytes_and_reports_safe_error(monkeypatch):
    cache = FakeRedis({'upload:job': b'%PDF'})
    job = SimpleNamespace(meta={}, save_meta=lambda: None)
    monkeypatch.setattr(queue_resources, 'redis_connection', cache)
    monkeypatch.setattr(rq, 'get_current_job', lambda: job)
    def fail(*args): raise ValueError('Scanned PDF needs OCR')
    monkeypatch.setattr(tasks, 'process_paper_analysis', fail)
    with pytest.raises(ValueError): tasks.process_uploaded_paper('job', 'paper.pdf')
    assert 'upload:job' not in cache.values
    assert job.meta['safe_error'] == 'Scanned PDF needs OCR'

def test_cancelled_job_does_not_recreate_result_cache(monkeypatch):
    cache = FakeRedis({'upload:job': b'%PDF', 'deleted:job': '1'})
    monkeypatch.setattr(queue_resources, 'redis_connection', cache)
    monkeypatch.setattr(rq, 'get_current_job', lambda: SimpleNamespace(meta={'cache_key': 'private-cache'}))
    assert tasks.process_uploaded_paper('job', 'paper.pdf')['error'] == 'Analysis cancelled'
    assert 'private-cache' not in cache.values
    assert 'upload:job' not in cache.values
