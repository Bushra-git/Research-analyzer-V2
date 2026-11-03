"""Run against a disposable stack. Exercises actual HTTP, PostgreSQL, Redis and RQ."""
import concurrent.futures
import os
import time
import uuid
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fitz
import requests
from psycopg2.pool import SimpleConnectionPool
from seed_life_science_data import upsert_reference_papers

base = os.getenv('TEST_API_URL', 'http://localhost:3001')
pool = SimpleConnectionPool(1, 1, dsn=os.environ['DATABASE_URL'])
try:
    assert upsert_reference_papers(pool, [{'openalex_id': 'test:crop-water', 'research_domain': 'Agriculture',
        'title': 'Controlled field experiments for irrigation and crop growth', 'abstract': 'Research on crop water use and irrigation.',
        'authors': ['Test Author'], 'venue_name': 'Test Journal', 'venue_type': 'journal', 'venue_issn': None,
        'publication_year': 2025, 'citation_count': 0, 'text_content': 'Controlled field experiments for irrigation and crop growth. Research on crop water use and irrigation.'}]) == 1
finally:
    pool.closeall()
with fitz.open() as document:
    page = document.new_page()
    text = 'Abstract\n' + 'We study irrigation and crop growth in controlled field experiments. ' * 15
    page.insert_textbox(fitz.Rect(40, 40, 550, 750), text, fontsize=11)
    pdf = document.tobytes()

def upload(client):
    return client.post(base + '/api/analyze', files={'file': ('private-paper.pdf', pdf, 'application/pdf')}, timeout=30)

owner, stranger = requests.Session(), requests.Session()
for client in (owner, stranger):
    assert client.get(base + '/api/session', timeout=10).status_code == 200
response = upload(owner)
assert response.status_code == 202, response.text
job = response.json()['job_id']
assert stranger.get(base + '/api/status/' + job, timeout=10).status_code == 404
assert stranger.delete(base + '/api/analyses/' + job, timeout=10).status_code == 404
assert stranger.get(base + '/api/history', timeout=10).json()['history'] == []
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    result = owner.get(base + '/api/status/' + job, timeout=10)
    assert result.status_code == 200, result.text
    payload = result.json()
    if payload['status'] in ('finished', 'failed'): break
    time.sleep(.5)
assert payload['status'] == 'finished', payload
assert payload['result']['score'] is None
assert '_matching_text' not in payload['result']
assert owner.get(base + '/api/history', timeout=10).json()['history'][0]['paperFilename'] == 'private-paper.pdf'
assert owner.delete(base + '/api/analyses/' + job, timeout=10).status_code == 200
assert owner.get(base + '/api/status/' + job, timeout=10).status_code == 404
# Only one guest reservation remains for this IP. Separate sessions race for it.
def attempt(_):
    with requests.Session() as client:
        client.get(base + '/api/session', timeout=10)
        return upload(client).status_code
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    statuses = list(executor.map(attempt, range(4)))
assert statuses.count(202) == 1 and statuses.count(403) == 3, statuses
print('PASS: real-stack analysis, guest isolation, deletion, and atomic quota race')
