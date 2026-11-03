"""Sourced publication charges. Missing metadata never means free."""
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


def issn_key(value):
    value = re.sub(r'[^0-9X]', '', str(value).upper())
    return value if re.fullmatch(r'\d{7}[\dX]', value) else ''


def safe_url(value):
    value = str(value or '').strip()
    parsed = urlparse(value)
    return value if parsed.scheme in ('https', 'http') and parsed.netloc and not parsed.username else None


def parse_fee_record(row, fetched_at):
    apc = row.get('APC', '').strip().lower()
    other = row.get('Has other fees', '').strip().lower()
    prices = []
    for entry in row.get('APC amount', '').split(';'):
        match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s+([A-Z]{3})\s*', entry)
        if match:
            prices.append({'amount': float(match[1]), 'currency': match[2]})
    status = 'free' if apc == 'no' and other == 'no' else 'paid' if apc == 'yes' or other == 'yes' else 'unknown'
    return {'status': status, 'apc_prices': prices if apc == 'yes' else [],
            'has_apc': {'yes': True, 'no': False}.get(apc),
            'other_fees': {'yes': True, 'no': False}.get(other),
            'source': 'DOAJ', 'source_url': safe_url(row.get('URL in DOAJ')),
            'fee_url': safe_url(row.get('APC information URL') or row.get('Other fees information URL')),
            'journal_url': safe_url(row.get('Journal URL')),
            'source_updated_at': row.get('Last updated Date') or None, 'fetched_at': fetched_at}


@lru_cache(maxsize=1)
def fee_index():
    path = Path(__file__).parent / 'datasets' / 'venue_fees.json'
    if not path.exists(): return {}
    return json.loads(path.read_text(encoding='utf-8'))['by_issn']


def fees_for(*issns):
    matches = [fee_index()[key] for value in issns if (key := issn_key(value)) in fee_index()]
    if matches and all(record == matches[0] for record in matches): return dict(matches[0])
    return {'status': 'unknown', 'apc_prices': [], 'has_apc': None, 'other_fees': None,
            'source': None, 'source_url': None, 'fee_url': None, 'journal_url': None,
            'source_updated_at': None, 'fetched_at': None}
