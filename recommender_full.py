"""Venue retrieval: normalize source data, enforce constraints, then rank relevance."""
from pathlib import Path
import re
import math
import pandas as pd
from venue_taxonomy import ASJC_CODES_IN_DATASET
from semantic_matching import rank_texts
from domain_detection import get_domain_stats
from venue_fees import fees_for

def clean(value):
    return '' if pd.isna(value) else str(value).strip()

def normalize_venue(row):
    subjects = [name for code, name in ASJC_CODES_IN_DATASET.items() if clean(row.get(f'{code}\n{name}', ''))]
    status = clean(row.get('Active or Inactive', '')).lower()
    medline = clean(row.get('Medline-sourced Title? (See additional details under separate tab.)', '')).lower()
    coverage = clean(row.get('Coverage', ''))
    years = [int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b', coverage)]
    return {'name': clean(row.get('Source Title', '')), 'type': clean(row.get('Source Type', '')).lower(),
        'publisher': clean(row.get('Publisher', '')), 'active_status': status == 'active',
        'open_access': 'open access' in clean(row.get('Open Access Status', '')).lower(),
        'medline_coverage': medline in ('medline', 'medline-unique', 'yes', 'true', '1'),
        'coverage_year_range': coverage, 'last_coverage_year': max(years) if years else None,
        'language': clean(row.get('Article Language in Source (Three-Letter ISO Language Codes)', '')) or 'Unknown',
        'issn': clean(row.get('ISSN', '')) or clean(row.get('EISSN', '')) or None,
        'sourcerecord_id': clean(row.get('Sourcerecord ID', '')) or None,
        'fees': fees_for(clean(row.get('ISSN', '')), clean(row.get('EISSN', ''))),
        'matched_asjc_subjects': subjects,
        'verification_status': 'Source dataset, January 2026; not live verification',
        'venue_warnings': ([] if status == 'active' else ['Not marked active in the source dataset'])}

def load_venue_database_enhanced():
    root = Path(__file__).parent / 'datasets'
    path = next((root / name for name in ('ext_venues_enhanced.csv', 'ext_venues_active.csv') if (root / name).is_file()), None)
    if path is None: raise RuntimeError('Venue dataset is missing')
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows = [normalize_venue(row) for row in frame.to_dict('records')]
    return pd.DataFrame([row for row in rows if row['name']])

def validate_preferences(data):
    prefs = {}
    for key, default in [('open_access_only', False), ('medline_only', False), ('exclude_discontinued', True)]:
        value = data.get(key, default)
        if type(value) is not bool: raise ValueError(f'{key} must be a boolean')
        prefs[key] = value
    venue_type = data.get('venue_type', 'any')
    if venue_type not in ('any', 'journal', 'conference', 'conference proceeding', 'book series', 'trade journal'):
        raise ValueError('Unsupported venue_type')
    prefs['venue_type'] = venue_type
    year = data.get('min_coverage_year', 0)
    if type(year) is not int or not 0 <= year <= 2100: raise ValueError('min_coverage_year must be an integer between 0 and 2100')
    prefs['min_coverage_year'] = year
    publisher = data.get('publisher', 'any')
    if not isinstance(publisher, str) or len(publisher) > 200: raise ValueError('Invalid publisher')
    prefs['publisher'] = publisher
    subjects = data.get('selected_subjects', [])
    if not isinstance(subjects, list) or any(s not in ASJC_CODES_IN_DATASET.values() for s in subjects): raise ValueError('Unsupported selected_subjects')
    prefs['selected_subjects'] = subjects
    fee_status = data.get('fee_status', 'any')
    if fee_status not in ('any', 'free', 'paid', 'unknown'): raise ValueError('Invalid fee_status')
    prefs['fee_status'] = fee_status
    budget = data.get('max_apc')
    if budget is not None and (type(budget) not in (int, float) or not math.isfinite(budget) or not 0 <= budget <= 10000000):
        raise ValueError('max_apc must be a finite nonnegative number')
    currency = data.get('currency', 'USD')
    if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency): raise ValueError('Invalid currency')
    prefs.update(max_apc=budget, currency=currency)
    for key in ('fee_pref', 'acceptance', 'indexing'):
        if key in data and data[key] not in (None, 'Any', ['Any']): raise ValueError(f'{key} is not supported by the available dataset')
    return prefs

def filter_venues(venue_db, prefs):
    if venue_db is None or venue_db.empty: raise ValueError('Venue database is empty')
    rows = venue_db.to_dict('records')
    if 'active_status' not in rows[0]: rows = [normalize_venue(row) for row in rows]
    candidates = []
    for row in rows:
        if prefs['exclude_discontinued'] and not row['active_status']: continue
        if prefs['open_access_only'] and not row['open_access']: continue
        if prefs['medline_only'] and not row['medline_coverage']: continue
        kind = prefs['venue_type']
        if kind != 'any' and (('conference' not in row['type']) if kind == 'conference' else row['type'] != kind): continue
        if prefs['min_coverage_year'] and (row['last_coverage_year'] or 0) < prefs['min_coverage_year']: continue
        if prefs['publisher'] != 'any' and prefs['publisher'].casefold() != row['publisher'].casefold(): continue
        if prefs['selected_subjects'] and not set(prefs['selected_subjects']).intersection(row['matched_asjc_subjects']): continue
        fees = row.get('fees') or {'status': 'unknown', 'apc_prices': []}
        if prefs['fee_status'] != 'any' and fees['status'] != prefs['fee_status']: continue
        if prefs['max_apc'] is not None and fees['status'] != 'free':
            # Do not compare different currencies or silently admit unknown prices.
            prices = [p['amount'] for p in fees['apc_prices'] if p['currency'] == prefs['currency']]
            if not prices or max(prices) > prefs['max_apc']: continue
        candidates.append(row)
    return rows, candidates


def list_venues(data, venue_db):
    prefs = validate_preferences(data)
    query = data.get('query', '')
    if not isinstance(query, str) or len(query) > 200: raise ValueError('Search must be at most 200 characters')
    page, size = data.get('page', 1), data.get('page_size', 12)
    if type(page) is not int or not 1 <= page <= 10000 or type(size) is not int or not 1 <= size <= 50:
        raise ValueError('Invalid page or page_size')
    _, candidates = filter_venues(venue_db, prefs)
    terms = query.casefold().split()
    candidates = [r for r in candidates if all(t in ' '.join([r['name'], r['publisher'], *r['matched_asjc_subjects']]).casefold() for t in terms)]
    candidates.sort(key=lambda r: (r['name'].casefold(), r.get('sourcerecord_id') or ''))
    return {'venues': candidates[(page - 1) * size:page * size], 'total': len(candidates),
            'page': page, 'page_size': size, 'pages': max(1, math.ceil(len(candidates) / size))}


def recommend_venues_enhanced(paper_text, paper_score, paper_topic, preferences, venue_db, top_n=10):
    prefs = validate_preferences(preferences)
    rows, candidates = filter_venues(venue_db, prefs)
    query = paper_text or paper_topic
    # Cheap broad retrieval before semantic reranking avoids embedding 48k venues per request.
    documents = [row['name'] + '. ' + '. '.join(row['matched_asjc_subjects']) for row in candidates]
    lexical, _ = rank_texts(query, documents, semantic=False)
    indices = lexical.argsort()[::-1][:200]
    shortlist = [candidates[int(i)] for i in indices]
    shortlist_docs = [documents[int(i)] for i in indices]
    scores, diagnostics = rank_texts(query, shortlist_docs)
    recommendations = []
    for index in scores.argsort()[::-1]:
        score = float(scores[int(index)])
        if score <= .02: continue
        row = dict(shortlist[int(index)])
        row['match_score'] = round(score * 100, 1)
        row['reason'] = 'Text similarity to venue title and subject metadata: ' + ', '.join(row['matched_asjc_subjects'][:4])
        row['score_label'] = 'Relative text relevance; not acceptance probability'
        recommendations.append(row)
    domain = get_domain_stats(query)
    return {'venues': recommendations[:top_n], 'paper_domain': domain['domain'],
        'paper_subjects': prefs['selected_subjects'], 'total_venues_evaluated': len(rows),
        'eligible_venues': len(candidates), 'matches_found': len(recommendations), 'matching': diagnostics,
        'limitations': ['Ranking uses venue titles and broad subject metadata, not full aims and scope.',
                       'Check the venue website for current indexing, fees, scope, and submission rules.']}
