import os
import re
import time
import hashlib
import json
from collections import Counter
from threading import Lock

import requests
from redis import Redis
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool
except Exception:  # pragma: no cover
    psycopg2 = None
    SimpleConnectionPool = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover
    TfidfVectorizer = None
    cosine_similarity = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None

_POOL = None
_POOL_LOCK = Lock()
_CACHE = {
    "loaded_at": 0.0,
    "rows": [],
}
_VECTORIZER = None
_TFIDF_MATRIX = None
_EMBEDDING_MODEL = None

REFERENCE_CACHE_TTL_SECONDS = int(os.getenv("REFERENCE_CACHE_TTL_SECONDS", "600"))
REFERENCE_MAX_ROWS = int(os.getenv("REFERENCE_MAX_ROWS", "4000"))
OPENALEX_REALTIME_ENABLED = os.getenv("OPENALEX_REALTIME_ENABLED", "true").lower() == "true"
OPENALEX_REALTIME_RESULTS = int(os.getenv("OPENALEX_REALTIME_RESULTS", "10"))
OPENALEX_REALTIME_TIMEOUT = int(os.getenv("OPENALEX_REALTIME_TIMEOUT_SECONDS", "8"))
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_CACHE_TTL = int(os.getenv("OPENALEX_CACHE_TTL_SECONDS", "3600"))
_OPENALEX_CACHE = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
SEMANTIC_SIMILARITY_ENABLED = os.getenv("SEMANTIC_SIMILARITY_ENABLED", "false").lower() == "true"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")


def _openalex_session():
    retry_policy = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry_policy))
    return session


def _build_openalex_query(paper_text):
    words = re.findall(r"[A-Za-z][A-Za-z-]{4,}", str(paper_text).lower())
    stop_words = {
        "about", "after", "among", "could", "first", "from", "have",
        "into", "more", "other", "paper", "results", "their", "these",
        "there", "this", "using", "which", "with", "would",
    }
    counts = Counter(word for word in words if word not in stop_words)
    return " ".join(word for word, _count in counts.most_common(12))


def _reconstruct_openalex_abstract(index):
    if not isinstance(index, dict):
        return ""
    tokens = {}
    for token, positions in index.items():
        if isinstance(positions, list):
            for position in positions:
                if isinstance(position, int):
                    tokens[position] = token
    return " ".join(tokens[position] for position in sorted(tokens))


def _fetch_realtime_openalex_papers(paper_text, top_k):
    if not OPENALEX_REALTIME_ENABLED:
        return []

    query = _build_openalex_query(paper_text)
    if not query:
        return []

    cache_key = "openalex:works:" + hashlib.sha256(query.encode("utf-8")).hexdigest()
    try:
        cached = _OPENALEX_CACHE.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    try:
        response = _openalex_session().get(
            OPENALEX_WORKS_URL,
            params={
                "search": query,
                "filter": "has_abstract:true",
                "per-page": max(1, min(OPENALEX_REALTIME_RESULTS, 20)),
                "sort": "relevance_score:desc",
            },
            timeout=OPENALEX_REALTIME_TIMEOUT,
        )
        response.raise_for_status()
        works = response.json().get("results", [])
    except Exception as exc:
        print(f"[WARN] real-time OpenAlex lookup failed: {exc}")
        return []

    records = []
    for work in works[: max(1, min(int(top_k), 20))]:
        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        abstract = _reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        title = _safe_text(work.get("title"), max_length=500)
        if not title or not abstract:
            continue

        records.append(
            {
                "title": title,
                "abstract": _safe_text(abstract, max_length=20000),
                "authors": [
                    _safe_text((authorship.get("author") or {}).get("display_name"), max_length=300)
                    for authorship in (work.get("authorships") or [])
                    if (authorship.get("author") or {}).get("display_name")
                ],
                "research_domain": "OpenAlex realtime",
                "venue_name": _safe_text(source.get("display_name"), max_length=500),
                "venue_type": _safe_text(source.get("type"), max_length=100),
                "venue_issn": _safe_text(source.get("issn_l"), max_length=100),
                "publication_year": work.get("publication_year"),
                "citation_count": int(work.get("cited_by_count") or 0),
                "text_content": _safe_text(f"{title}\n\n{abstract}"),
            }
        )

    try:
        _OPENALEX_CACHE.setex(cache_key, OPENALEX_CACHE_TTL, json.dumps(records))
    except Exception:
        pass

    return records


def _get_pool():
    global _POOL

    if _POOL is not None:
        return _POOL

    if psycopg2 is None or SimpleConnectionPool is None:
        return None

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return None

    with _POOL_LOCK:
        if _POOL is None:
            _POOL = SimpleConnectionPool(minconn=1, maxconn=5, dsn=database_url)

    return _POOL


def _safe_text(value, max_length=200000):
    if value is None:
        return ""
    cleaned = str(value).replace("\x00", " ").strip()
    return cleaned[:max_length]


def _semantic_scores(query_text, rows):
    global _EMBEDDING_MODEL

    if not SEMANTIC_SIMILARITY_ENABLED or SentenceTransformer is None:
        return None

    try:
        if _EMBEDDING_MODEL is None:
            _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)

        texts = [row["text_content"][:30000] for row in rows]
        embeddings = _EMBEDDING_MODEL.encode(
            [query_text[:30000]] + texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings[1:] @ embeddings[0]
    except Exception as exc:
        print(f"[WARN] semantic similarity unavailable; using TF-IDF: {exc}")
        return None


def _load_reference_rows(limit=REFERENCE_MAX_ROWS):
    global _VECTORIZER, _TFIDF_MATRIX
    now = time.time()
    if _CACHE["rows"] and (now - _CACHE["loaded_at"] < REFERENCE_CACHE_TTL_SECONDS):
        return _CACHE["rows"]

    pool = _get_pool()
    if pool is None:
        return []

    connection = None
    cursor = None

    try:
        connection = pool.getconn()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                title,
                abstract,
                authors,
                research_domain,
                venue_name,
                venue_type,
                venue_issn,
                publication_year,
                citation_count,
                text_content
            FROM reference_papers
            WHERE text_content IS NOT NULL
              AND LENGTH(TRIM(text_content)) > 0
            ORDER BY citation_count DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )

        rows = cursor.fetchall()
        records = []
        for row in rows:
            records.append(
                {
                    "title": _safe_text(row[0], max_length=500),
                    "abstract": _safe_text(row[1], max_length=20000),
                    "authors": row[2] if isinstance(row[2], list) else [],
                    "research_domain": _safe_text(row[3], max_length=100),
                    "venue_name": _safe_text(row[4], max_length=500),
                    "venue_type": _safe_text(row[5], max_length=100),
                    "venue_issn": _safe_text(row[6], max_length=100),
                    "publication_year": row[7],
                    "citation_count": int(row[8] or 0),
                    "text_content": _safe_text(row[9], max_length=200000),
                }
            )

        _CACHE["rows"] = records
        _CACHE["loaded_at"] = now
        _VECTORIZER = None
        _TFIDF_MATRIX = None
        return records
    except Exception as exc:
        print(f"[WARN] reference_papers load failed: {exc}")
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            pool.putconn(connection)


def get_reference_similar_papers(paper_text, top_k=5):
    global _VECTORIZER, _TFIDF_MATRIX
    if not paper_text or len(str(paper_text).strip()) < 50:
        return []

    if SentenceTransformer is None and (TfidfVectorizer is None or cosine_similarity is None):
        return []

    realtime_rows = _fetch_realtime_openalex_papers(paper_text, top_k)
    if realtime_rows:
        rows = realtime_rows
        realtime = True
    else:
        rows = _load_reference_rows(limit=REFERENCE_MAX_ROWS)
        realtime = False
    if not rows:
        return []

    query_text = _safe_text(paper_text, max_length=200000)
    similarity_method = "tfidf"
    try:
        semantic_scores = _semantic_scores(query_text, rows)
        if semantic_scores is not None:
            scores = semantic_scores
            similarity_method = "sentence_transformer"
        elif realtime:
            vectorizer = TfidfVectorizer(
                stop_words="english",
                max_features=12000,
                ngram_range=(1, 2),
            )
            tfidf_matrix = vectorizer.fit_transform(
                [row["text_content"] for row in rows]
            )
        elif _VECTORIZER is None or _TFIDF_MATRIX is None:
            _VECTORIZER = TfidfVectorizer(
                stop_words="english",
                max_features=12000,
                ngram_range=(1, 2),
            )
            _TFIDF_MATRIX = _VECTORIZER.fit_transform(
                [row["text_content"] for row in rows]
            )

            tfidf_matrix = _TFIDF_MATRIX
            vectorizer = _VECTORIZER
        else:
            tfidf_matrix = _TFIDF_MATRIX
            vectorizer = _VECTORIZER

        if semantic_scores is None:
            query_vector = vectorizer.transform([query_text])
            scores = cosine_similarity(query_vector, tfidf_matrix).flatten()
            similarity_method = "tfidf"

        max_items = max(1, min(int(top_k), 20))
        ranked_indices = scores.argsort()[::-1][:max_items]

        matches = []
        for idx in ranked_indices:
            record = rows[int(idx)]
            matches.append(
                {
                    "title": record["title"],
                    "abstract": record["abstract"],
                    "authors": record["authors"],
                    "research_domain": record["research_domain"],
                    "source": "openalex_realtime" if realtime else "postgresql_seed",
                    "similarity_method": similarity_method,
                    "venue_name": record["venue_name"],
                    "venue_type": record["venue_type"],
                    "venue_issn": record["venue_issn"],
                    "publication_year": record["publication_year"],
                    "citation_count": record["citation_count"],
                    "similarity_score": float(scores[int(idx)]),
                }
            )

        return matches
    except Exception as exc:
        print(f"[WARN] reference_papers similarity failed: {exc}")
        return []
