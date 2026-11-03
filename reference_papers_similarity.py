"""Private-by-default corpus search with optional, explicitly requested OpenAlex lookup."""
import os
import re
import time
from collections import Counter
from threading import RLock
import requests
from psycopg2.pool import ThreadedConnectionPool
from semantic_matching import rank_texts

_POOL = None
_LOCK = RLock()
_CACHE = {'loaded_at': 0, 'rows': []}
MAX_ROWS = int(os.getenv('REFERENCE_MAX_ROWS', '4000'))

def _get_pool():
    global _POOL
    with _LOCK:
        if _POOL is None and os.getenv('DATABASE_URL'):
            _POOL = ThreadedConnectionPool(1, 5, dsn=os.environ['DATABASE_URL'], connect_timeout=5)
        return _POOL

def _load_reference_rows(limit=MAX_ROWS):
    with _LOCK:
        if _CACHE['rows'] and time.time() - _CACHE['loaded_at'] < 600: return _CACHE['rows']
        pool = _get_pool()
        if not pool: return []
        connection = pool.getconn()
        try:
            with connection.cursor() as cursor:
                cursor.execute('''SELECT title, abstract, authors, research_domain, venue_name, venue_type,
                    venue_issn, publication_year, citation_count, text_content, openalex_id FROM (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY research_domain ORDER BY publication_year DESC, id DESC) AS domain_rank
                    FROM reference_papers WHERE LENGTH(TRIM(text_content)) > 0
                    ) ranked ORDER BY domain_rank, research_domain LIMIT %s''', (limit,))
                names = ['title', 'abstract', 'authors', 'research_domain', 'venue_name', 'venue_type', 'venue_issn', 'publication_year', 'citation_count', 'text_content', 'openalex_id']
                rows = [dict(zip(names, values), source='postgresql_seed') for values in cursor.fetchall()]
            _CACHE.update(rows=rows, loaded_at=time.time())
            return rows
        finally:
            connection.rollback()
            pool.putconn(connection)

def _external_rows(text):
    words = re.findall(r'\b[a-z][a-z-]{4,}\b', text.lower())
    stop = {'these', 'their', 'there', 'which', 'using', 'paper', 'results', 'study', 'about', 'other', 'would'}
    query = ' '.join(w for w, _ in Counter(w for w in words if w not in stop).most_common(12))
    if not query: return []
    params = {'search': query, 'filter': 'has_abstract:true', 'per-page': 40}
    if os.getenv('OPENALEX_API_KEY'): params['api_key'] = os.environ['OPENALEX_API_KEY']
    with requests.Session() as session:
        response = session.get('https://api.openalex.org/works', params=params, timeout=(3, 8))
        response.raise_for_status()
        works = response.json().get('results', [])
    rows = []
    for work in works:
        index = work.get('abstract_inverted_index') or {}
        positions = {p: word for word, places in index.items() for p in places if isinstance(p, int)}
        abstract = ' '.join(positions[p] for p in sorted(positions))[:20000]
        source = (work.get('primary_location') or {}).get('source') or {}
        if not abstract or not work.get('title'): continue
        rows.append({'title': work['title'], 'abstract': abstract, 'text_content': work['title'] + '\n' + abstract,
            'authors': [(a.get('author') or {}).get('display_name', '') for a in work.get('authorships', [])],
            'research_domain': 'OpenAlex', 'venue_name': source.get('display_name'), 'venue_type': source.get('type'),
            'venue_issn': source.get('issn_l'), 'publication_year': work.get('publication_year'),
            'citation_count': work.get('cited_by_count', 0), 'openalex_id': work.get('id'), 'doi': work.get('doi'), 'source': 'openalex_realtime'})
    return rows

def find_reference_papers(paper_text, top_k=5, external_search=False):
    warnings = []
    try: rows = list(_load_reference_rows())
    except Exception:
        rows = []; warnings.append('Local reference corpus is unavailable')
    if external_search:
        try: rows += _external_rows(paper_text)
        except Exception: warnings.append('External search failed; local results are shown when available')
    if not rows:
        return {'papers': [], 'diagnostics': {'method': 'none', 'external_search': external_search,
            'warnings': warnings + ['No reference papers available. Seed the local corpus or opt into external search.']}}
    rows = list({row.get('openalex_id') or row['title'].casefold(): row for row in rows}.values())
    # Use a cheap lexical shortlist before semantic reranking. This keeps
    # per-upload inference bounded while retaining semantic ranking among the
    # strongest textual candidates.
    docs = [str(row.get('text_content') or '')[:20000] for row in rows]
    lexical_scores, _ = rank_texts(paper_text, docs, semantic=False)
    candidate_count = min(len(rows), int(os.getenv('REFERENCE_SEMANTIC_CANDIDATES', '200')))
    indices = lexical_scores.argsort()[::-1][:candidate_count]
    shortlist = [rows[int(i)] for i in indices]
    shortlist_docs = [docs[int(i)] for i in indices]
    scores, diagnostics = rank_texts(paper_text, shortlist_docs)
    papers = []
    for i in scores.argsort()[::-1][:max(1, min(int(top_k), 20))]:
        if float(scores[int(i)]) <= .02: continue
        row = {k: v for k, v in shortlist[int(i)].items() if k != 'text_content'}
        row.update(similarity_score=float(scores[int(i)]), similarity_method=diagnostics['method'])
        papers.append(row)
    diagnostics.update(external_search=external_search, warnings=warnings,
                       candidate_count=len(rows), semantic_candidate_count=len(shortlist))
    return {'papers': papers, 'diagnostics': diagnostics}

def get_reference_similar_papers(paper_text, top_k=5):
    return find_reference_papers(paper_text, top_k, external_search=False)['papers']
