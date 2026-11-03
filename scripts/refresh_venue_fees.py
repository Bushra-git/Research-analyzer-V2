"""Refresh public DOAJ fee metadata by exact ISSN. Never sends manuscript text."""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from venue_fees import issn_key, parse_fee_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', help='Use an already downloaded DOAJ CSV')
    args = parser.parse_args()
    if args.csv:
        content = Path(args.csv).read_text(encoding='utf-8-sig')
    else:
        response = requests.get('https://doaj.org/csv', timeout=(10, 120))
        response.raise_for_status()
        content = response.content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    required = {'Journal ISSN (print version)', 'Journal EISSN (online version)', 'APC', 'Has other fees', 'APC amount'}
    if not required.issubset(reader.fieldnames or []): raise ValueError('Unexpected DOAJ CSV schema; prior snapshot preserved')
    fetched = datetime.now(timezone.utc).isoformat()
    index, conflicts = {}, set()
    for row in reader:
        record = parse_fee_record(row, fetched)
        for field in ('Journal ISSN (print version)', 'Journal EISSN (online version)'):
            key = issn_key(row[field])
            if not key or key in conflicts: continue
            if key in index and index[key] != record:
                conflicts.add(key); index.pop(key); continue
            index[key] = record
    if len(index) < 1000: raise ValueError('Incomplete DOAJ download; prior snapshot preserved')
    path = Path(__file__).resolve().parents[1] / 'datasets' / 'venue_fees.json'
    payload = {'source': 'https://doaj.org/csv', 'documentation': 'https://doaj.org/docs/journal-csv',
               'fetched_at': fetched, 'ambiguous_issns_excluded': len(conflicts), 'by_issn': index}
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
    print(f'Saved {len(index)} ISSN fee records; {len(conflicts)} ambiguous ISSNs excluded.')


if __name__ == '__main__': main()
