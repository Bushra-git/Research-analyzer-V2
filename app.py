"""Private HTTP boundary. Only the authenticated Node gateway may access jobs."""
import hashlib
import hmac
import json
import os
import re
import uuid
from functools import lru_cache

from dotenv import load_dotenv
load_dotenv()
from flask import Flask, jsonify, request
from redis.exceptions import RedisError
from rq import Worker
from rq.job import Job
from rq.exceptions import NoSuchJobError
from rq.command import send_stop_job_command
from queue_resources import analysis_queue, redis_connection
from analysis_tasks import ANALYSIS_VERSION, process_uploaded_paper

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
TTL = int(os.getenv('RETENTION_HOURS', '24')) * 3600

@app.before_request
def authenticate_gateway():
    secret = os.getenv('INTERNAL_API_TOKEN', '')
    if len(secret) < 32:
        return jsonify(error='Internal authentication is not configured'), 503
    if not hmac.compare_digest(request.headers.get('X-Internal-Token', ''), secret):
        return jsonify(error='Unauthorized'), 401
    if request.path != '/health' and not re.fullmatch(r'(user|guest):[A-Za-z0-9_-]{1,100}', request.headers.get('X-Owner-Key', '')):
        return jsonify(error='Owner identity required'), 401

@app.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

def owned_job(job_id):
    try:
        uuid.UUID(job_id)
        job = Job.fetch(job_id, connection=redis_connection)
    except (ValueError, NoSuchJobError):
        return None
    if job.meta.get('owner_key') != request.headers.get('X-Owner-Key') or redis_connection.exists(f'deleted:{job_id}'):
        return None
    return job

def public_result(result):
    return {k: v for k, v in (result or {}).items() if not k.startswith('_')}

@app.get('/health')
def health():
    from reference_papers_similarity import _get_pool
    from semantic_matching import model_status
    workers = Worker.all(connection=redis_connection)
    pool = _get_pool()
    database = False
    if pool:
        connection = pool.getconn()
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            database = True
        finally:
            connection.rollback()
            pool.putconn(connection)
    ready = bool(workers) and database
    return jsonify(status='ok' if ready else 'degraded', redis=bool(redis_connection.ping()), database=database,
                   workers=len(workers), queue=analysis_queue.count, model=model_status()), 200 if ready else 503

@app.post('/analyze')
def analyze():
    file = request.files.get('file')
    if not file:
        return jsonify(error='No file uploaded'), 400
    blob = file.read()
    if not blob.startswith(b'%PDF-'):
        return jsonify(error='Upload a valid PDF file'), 400
    if len(blob) > 15 * 1024 * 1024:
        return jsonify(error='PDF must be 15MB or smaller'), 413
    job_id = request.headers.get('X-Job-Id', '')
    try: uuid.UUID(job_id)
    except ValueError: return jsonify(error='Valid job ID required'), 400
    if analysis_queue.count >= int(os.getenv('MAX_QUEUED_JOBS', '100')):
        return jsonify(error='Analysis queue is full. Try again later.'), 503
    owner = request.headers['X-Owner-Key']
    external = request.form.get('external_search') == 'true'
    digest = hashlib.sha256(blob).hexdigest()
    cache_key = 'analysis:' + hashlib.sha256(f'{ANALYSIS_VERSION}:{owner}:{digest}:{external}'.encode()).hexdigest()
    redis_connection.setex(f'upload:{job_id}', 900, blob)
    try:
        # Cached jobs still use the same queue/status contract and ownership checks.
        job = analysis_queue.enqueue(process_uploaded_paper, job_id, file.filename, external,
            job_id=job_id, job_timeout=int(os.getenv('ANALYSIS_JOB_TIMEOUT_SECONDS', '300')),
            ttl=600, result_ttl=TTL, failure_ttl=3600,
            meta={'owner_key': owner, 'file_name': file.filename, 'cache_key': cache_key, 'file_hash': digest})
    except Exception:
        redis_connection.delete(f'upload:{job_id}')
        raise
    return jsonify(job_id=job.id, status=job.get_status()), 202

@app.get('/status/<job_id>')
def status(job_id):
    job = owned_job(job_id)
    if not job: return jsonify(error='Analysis not found or expired'), 404
    state = job.get_status()
    if state in ('stopped', 'canceled'): state = 'cancelled'
    payload = {'job_id': job.id, 'status': state, 'stage': job.meta.get('stage'), 'file_name': job.meta.get('file_name')}
    if job.is_finished:
        payload['result'] = public_result(job.result)
    if job.is_failed:
        payload['error'] = job.meta.get('safe_error', 'Analysis failed or timed out. Check that the PDF contains readable text and try again.')
    return jsonify(payload)

@app.delete('/jobs/<job_id>')
def delete_job(job_id):
    job = owned_job(job_id)
    if not job:
        # Gateway has already checked database ownership; deletion is idempotent after expiry.
        return jsonify(ok=True)
    redis_connection.setex(f'deleted:{job_id}', TTL, '1')
    if job.get_status() == 'started':
        try: send_stop_job_command(redis_connection, job.id)
        except Exception: pass
    else:
        job.cancel()
    keys = [f'upload:{job_id}', job.meta.get('cache_key', '')]
    redis_connection.delete(*[k for k in keys if k])
    job.delete()
    return jsonify(ok=True)

@lru_cache(maxsize=1)
def venue_database():
    from recommender_full import load_venue_database_enhanced
    return load_venue_database_enhanced()

@app.post('/recommend')
def recommend():
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify(error='JSON object required'), 400
    job = owned_job(str(data.get('job_id', '')))
    if not job or not job.is_finished: return jsonify(error='Completed analysis not found'), 404
    text = (job.result or {}).get('_matching_text')
    if not text: return jsonify(error='Matching text expired. Analyze the PDF again.'), 410
    from recommender_full import recommend_venues_enhanced, validate_preferences
    prefs = validate_preferences(data)
    result = recommend_venues_enhanced(text, None, '', prefs, venue_database())
    return jsonify(result)

@app.post('/venues')
def venue_directory():
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify(error='JSON object required'), 400
    from recommender_full import list_venues
    return jsonify(list_venues(data, venue_database()))

@app.post('/predict')
def retired_predict():
    return jsonify(error='Use the asynchronous /api/analyze endpoint'), 410

@app.errorhandler(ValueError)
def invalid_request(error):
    return jsonify(error=str(error)), 400

@app.errorhandler(RedisError)
def redis_unavailable(error):
    return jsonify(error='Queue service unavailable'), 503

@app.errorhandler(500)
def internal_error(error):
    return jsonify(error='Analysis service unavailable'), 500
