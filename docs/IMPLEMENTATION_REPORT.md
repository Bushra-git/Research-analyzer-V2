# Implementation report — 3 November 2026

## Changes

1. **Ownership and privacy:** ownership established before enqueueing; owner-scoped history/status/recommendation/deletion; no ownership changes during reads; isolated signed guest sessions; HttpOnly cookies; no browser bearer-token storage; external-search opt-in.
2. **Guest limits:** PostgreSQL conditional UPSERT reserves usage atomically. Only Express's configured trusted proxy chain determines the IP; client-supplied forwarding headers are not parsed manually. Original filenames are preserved safely.
3. **Deployment:** internal services no longer publish host ports; development JWT secret removed; secret generator added; same-origin Nginx API proxy; startup migrations; one dedicated RQ worker; Redis persistence disabled; production HTTPS cookies; Docker build contexts exclude caches and secrets.
4. **Analysis:** one shared pipeline, legacy synchronous route retired, unvalidated pickle score removed, real approximate readability, meaningful section/citation observations, clear invalid/encrypted/scanned-PDF errors, PDF page/text limits, optional OCR.
5. **ML retrieval:** installed and exercised local MiniLM; pinned model revision; chunked text; hybrid lexical/semantic ranking; bounded candidate reranking and public-corpus embedding cache; explicit fallback diagnostics; evaluation fixtures and report.
6. **Venues:** normalized raw metadata; verified 48,151 rows, 5,009 Medline records and 8,952 open-access records; strict filters; no arbitrary Medicine default or publisher-prestige weighting; unsupported preferences rejected; language read from the correct source field.
7. **Queue and retention:** timeout-enforced dedicated worker; upload TTL and cleanup; private content cache used by the live queue path; cancellation/deletion tombstones; owner-preserving completion persistence even after browser closure; expiring results and scheduled database cleanup.
8. **UI:** removed unsupported scientific-quality labels; explained writing metrics and matching scores; longer private matching excerpt referenced by job ID; opt-in external search; history/open/delete; cancellable/resumable polling with deadline, network retries and cleanup; accessible form labels and responsive layout.
9. **Testing and docs:** security, filter, lifecycle and UI regressions; model smoke evaluation; CI coverage for Node and a disposable full-stack workflow; current setup, privacy, migration and model documentation.
10. **Corpus seeding:** fixed Python inserts to supply `updated_at`, whose database default had been removed by an existing migration; refreshed title/venue/year on upsert; added API-key support and a regression test.

## Verification

- 25 Python tests passed, covering analysis, real source-dataset normalization, filters, private API, cache/upload cleanup, cancellation and corpus seeding.
- 8 Node security tests passed.
- 5 React tests and production build passed.
- Prisma schema validated and Prisma Client generated.
- Actual pretrained MiniLM inference ran successfully; six-case retrieval evaluation saved separately.
- An actual full-dataset hybrid venue query returned diabetes-related venues from 921 strictly eligible active, open-access, Medline records; every returned venue satisfied all three filters.
- Python source compilation passed.

## Limits and unfinished external validation

- Docker is unavailable on this machine. The installed PostgreSQL initializer was blocked by Windows as potentially unwanted software. That protection was not bypassed. No existing user database was modified. Actual migration execution, Linux RQ timeout behavior and the full-stack CI job still need to run in a Docker/CI environment.
- OCR implementation is optional and was not evaluated against a scanned-PDF corpus here.
- No researcher-labeled evaluation/training dataset was supplied. The small smoke benchmark does not establish domain-wide accuracy, and the model is not a peer reviewer.
- Public hosting, TLS, backups, real-IP configuration and multi-instance distributed rate limiting require deployment-specific configuration. No production deployment was performed.
- Source venue metadata is dated January 2026; live indexing/fees/scope must be verified with the venue. No fabricated fee, acceptance or impact-factor data is shown.
- Existing history expires under the migration because legacy job ownership was not trustworthy. Review and back up an existing database before upgrade.

The original datasets and `model.pkl` remain. The legacy model is no longer loaded. Package downloads and a Python environment were kept under ignored workspace directories.
