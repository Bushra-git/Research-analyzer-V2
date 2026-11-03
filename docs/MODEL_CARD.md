# Matching model and evidence

## Intended use

Find textually related research papers and publication venues from available metadata. This is retrieval, not scientific assessment or peer review.

## Implementation

- Pretrained encoder: `sentence-transformers/all-MiniLM-L6-v2`.
- Exact revision: see `models/manifest.json`.
- Local CPU inference, safetensors, `trust_remote_code=False`, `local_files_only=True`.
- Overlapping passages use the installed tokenizer and model sequence budget, reserving special-token space. At most 8,192 tokens per document are considered. Passages are normalized and mean-pooled. Processing batches contain at most 32 documents to bound transient memory.
- Ranking: 70% nonnegative semantic cosine similarity + 30% TF-IDF cosine similarity. Weights are engineering defaults, not learned or calibrated probabilities.
- Related-paper retrieval first ranks the bounded corpus with cheap TF-IDF, then semantically reranks a configurable shortlist (default 200 candidates from up to 4,000 local records plus up to 40 opt-in external results). This bounds per-job MiniLM work while retaining lexical candidates for paraphrase matching. Venue retrieval retains its separate lexical shortlist; this change does not demonstrate improved venue accuracy.
- Corpus embeddings have a four-entry process-local LRU cache; manuscript embeddings are never cached globally. RQ's fork-per-job workers do not retain newly computed embeddings across jobs. The shortlist size is controlled by `REFERENCE_SEMANTIC_CANDIDATES` and should be measured against the job timeout when the corpus or hardware changes.
- Reference candidates mix the local corpus with OpenAlex only when the user opts in. Public metadata is deduplicated by OpenAlex ID/title.
- Venue embeddings represent titles and ASJC subject metadata, not verified full journal scope statements. Strict filters run first.

## Evaluation completed

`scripts/evaluate_retrieval.py` compares TF-IDF and hybrid retrieval on six authored fixtures across clinical research, software, ecology, energy, education and agriculture.

Observed on this workspace:

| Method | First-ranked relevant item | Mean reciprocal rank | Recall at 3 |
| --- | --- | --- | --- |
| TF-IDF | 5/6 | 0.8889 | 1.0 |
| Hybrid MiniLM + TF-IDF | 6/6 | 1.0 | 1.0 |

This is a small smoke test written alongside the implementation. It is not an independent benchmark, statistical evidence of general improvement, or a measure of scientific quality. Preserve the fixtures; do not tune against them and then describe them as held-out validation.

The original results are preserved in `retrieval-baseline.json`. After token-aware chunking and shortlist reranking, hybrid retrieval still ranks the relevant document first on all six examples. `scripts/evaluate_candidate_recall.py` additionally tests a synthetic 221-document corpus: the old keyword gate excludes the relevant ecology paper, while the shortlist pipeline preserves it when lexical ranking selects it. Repeated chemistry distractors intentionally expose candidate-selection failure modes; this is a regression stress test, not an independent accuracy benchmark. See `candidate-recall-evaluation.json` for timing and actual model diagnostics.

MiniLM remains the installed CPU baseline. A larger encoder or cross-encoder should only replace it after manuscript-specific held-out relevance judgments and latency measurements justify that choice. No fine-tuning data was supplied and no claim of a universally best model is made.

For a defensible accuracy claim, obtain researcher-labeled paper/venue relevance judgments across disciplines and languages. Split by manuscript and venue, compare against lexical baselines on a held-out set, and report Recall@k, nDCG@k, MRR, latency and error examples. No such labeled training/evaluation corpus was supplied, so no accuracy claim or custom trained quality classifier was invented.

## Writing metrics

The previous Random Forest quality score is retired. Flesch Reading Ease uses estimated English syllables and sentence splitting; PDFs, abbreviations, formulas and technical vocabulary can distort it. Heading detection and citation-marker counting are observations, not proof of completeness or correctness. A null `score` is intentional and displayed without a numeric quality rating.

## Sources

- [Model publisher's card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [Sentence Transformers semantic search documentation](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html)
- [SentenceTransformer loading options](https://sbert.net/docs/package_reference/sentence_transformer/model.html)
