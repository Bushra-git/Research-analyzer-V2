# Research workspace upgrade — 3 November 2026

## Delivered

- Responsive ivory/teal research workspace, dimensional CSS manuscript illustration with pointer tilt, pause control and reduced-motion support. No WebGL dependency or external font requests.
- Keyboard-accessible file selection, drag/drop, filename and size feedback, non-empty PDF validation, connection retry, clearer processing and empty-history states.
- Existing private sessions, external-search consent, ownership checks, retention, results, venue filters and account flows remain connected to the original API.
- Submission success is no longer misreported as an upload failure when the subsequent session/history refresh fails.
- Reference search considers the entire bounded corpus before ranking, preserving semantically related candidates without keyword overlap.
- Token-aware chunking, bounded transient embedding batches, true LRU access updates, unambiguous corpus cache keys and empty-query abstention.

## Architecture and tradeoffs

The existing React → Express → private Flask → Redis/RQ → PostgreSQL architecture remains appropriate for this local CPU application. No additional service is needed for the visual redesign. Public corpus embeddings may be cached, but manuscript vectors remain request-local.

Removing the 200-item keyword gate improves candidate recall at the cost of more cold inference work. RQ forks for jobs: its child-process embedding cache is not a cross-job index. Before growing the corpus, measure latency on actual paper lengths, then introduce a versioned public-corpus vector index keyed by model revision and content hash. Preserve owner-scoped manuscript storage and avoid placing private queries in that index. The current default corpus cap, batch allocation limits, worker timeout and explicit lexical fallback remain operational limits.

MiniLM is retained as the working CPU baseline. Larger models and cross-encoder reranking are candidates for future measured comparisons, not automatically superior choices. Relevant technical reference: https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html

## Evidence and limits

The six existing smoke cases remain first-ranked under hybrid retrieval. A new synthetic 221-candidate regression shows the relevant item excluded by the old lexical gate and ranked first by full-corpus hybrid retrieval. Neither test establishes general accuracy or venue recommendation quality. No researcher-labeled training set was supplied.

Python, Node security, React tests and production build are run locally; see the final task report for counts. The static preview returns HTTP 200, but the browser automation host is unavailable, so desktop/mobile screenshot inspection is unverified. This pass does not verify a complete database/Redis/RQ deployment, OCR quality, production scaling or a comprehensive dependency/security audit. No production deployment or database migration was performed.
