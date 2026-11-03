"""Reproducible retrieval smoke evaluation, not a scientific-quality benchmark."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from semantic_matching import rank_texts

parser = argparse.ArgumentParser()
parser.add_argument('--dataset', default='tests/fixtures/retrieval_cases.json')
parser.add_argument('--output', default='docs/retrieval-evaluation.json')
args = parser.parse_args()
dataset = json.loads(Path(args.dataset).read_text())
results = []
for semantic in (False, True):
    reciprocal, hits, cases = [], [], []
    for item in dataset:
        scores, diagnostics = rank_texts(item['query'], item['documents'], semantic=semantic)
        order = [int(i) for i in scores.argsort()[::-1]]
        rank = order.index(item['relevant_index']) + 1
        reciprocal.append(1 / rank); hits.append(rank <= 3)
        cases.append({'id': item['id'], 'rank': rank, 'method': diagnostics['method'], 'warning': diagnostics.get('warning')})
    results.append({'requested_method': 'hybrid' if semantic else 'tfidf', 'mrr': sum(reciprocal)/len(reciprocal),
                    'recall_at_3': sum(hits)/len(hits), 'cases': cases})
report = {'limitations': 'Small authored smoke set. Not independent expert evaluation or evidence of scientific quality.', 'results': results}
output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
