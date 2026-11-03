"""Synthetic stress test for keyword-gate recall, not general accuracy evidence."""
import json
import sys
from pathlib import Path
from time import perf_counter
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from semantic_matching import rank_texts, model_status

query = 'How warming changes the distribution of animals and plants'
target = 'Climate change alters species ranges and ecosystem biodiversity.'
# Distinct metadata rows that share query words but discuss unrelated chemistry.
documents = [f'Warming metal catalysts: changes in surface chemistry and particle distribution. Experiment {i}.' for i in range(220)] + [target]
lexical, _ = rank_texts(query, documents, semantic=False)
shortlist = np.argsort(-lexical, kind='stable')[:200]
started = perf_counter()
scores, diagnostics = rank_texts(query, documents)
elapsed = perf_counter() - started
rank = list(np.argsort(-scores, kind='stable')).index(len(documents) - 1) + 1
report = {
    'limitations': 'Synthetic keyword-gate regression with repeated chemistry distractors. Not a held-out benchmark or evidence of general model accuracy.',
    'candidate_count': len(documents),
    'old_lexical_gate_retains_relevant_paper': bool(len(documents) - 1 in shortlist),
    'full_corpus_relevant_rank': rank,
    'full_corpus_recall_at_5': int(rank <= 5),
    'cold_seconds': round(elapsed, 3),
    'diagnostics': diagnostics,
    'model': model_status(),
}
Path('docs/candidate-recall-evaluation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
