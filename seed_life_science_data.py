import os
import time
from typing import Dict, List

import requests
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_values

OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_FILTER = "concepts.id:c13181464,has_abstract:true"

PER_PAGE = int(os.getenv("OPENALEX_PER_PAGE", "200"))
MAX_RECORDS = int(os.getenv("OPENALEX_MAX_RECORDS", "1500"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("OPENALEX_TIMEOUT_SECONDS", "30"))
POOL_MAX_CONN = int(os.getenv("SEED_POOL_MAX_CONN", "4"))
FALLBACK_SEARCH = os.getenv("OPENALEX_FALLBACK_SEARCH", "life science")
DOMAIN_SEARCHES = {
    "Life Sciences": "life science",
    "Medicine": "medicine clinical disease treatment",
    "Computer Science": "computer science algorithms software artificial intelligence",
    "Engineering": "engineering materials systems design",
    "Physics": "physics quantum energy matter",
    "Chemistry": "chemistry molecules chemical reactions",
    "Mathematics": "mathematics theorem statistics computation",
    "Environmental Science": "environmental science climate ecology conservation",
    "Social Sciences": "social science society psychology economics",
    "Agricultural Sciences": "agriculture crops soil food production",
}


def safe_text(value, max_length=200000):
    if value is None:
        return ""
    cleaned = str(value).replace("\x00", " ").strip()
    return cleaned[:max_length]


def reconstruct_abstract(abstract_inverted_index: Dict[str, List[int]]) -> str:
    if not abstract_inverted_index:
        return ""

    max_position = -1
    for positions in abstract_inverted_index.values():
        if positions:
            max_position = max(max_position, max(positions))

    if max_position < 0:
        return ""

    tokens = [""] * (max_position + 1)
    for token, positions in abstract_inverted_index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int) and 0 <= pos <= max_position:
                tokens[pos] = token

    return " ".join(tok for tok in tokens if tok).strip()


def fetch_openalex_records(max_records: int, search: str = "") -> List[Dict]:
    results: List[Dict] = []
    cursor = "*"
    used_fallback = False

    while len(results) < max_records:
        if search or used_fallback:
            params = {
            "search": search or FALLBACK_SEARCH,
                "filter": "has_abstract:true",
                "per-page": min(PER_PAGE, max_records - len(results)),
                "cursor": cursor,
                "sort": "cited_by_count:desc",
            }
        else:
            params = {
                "filter": OPENALEX_FILTER,
                "per-page": min(PER_PAGE, max_records - len(results)),
                "cursor": cursor,
                "sort": "cited_by_count:desc",
            }

        response = requests.get(OPENALEX_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()

        payload = response.json()
        page_results = payload.get("results", [])
        if not page_results:
            if not results and not used_fallback and not search:
                print(
                    f"[WARN] OpenAlex returned no works for {OPENALEX_FILTER!r}; "
                    f"falling back to search={FALLBACK_SEARCH!r} with has_abstract:true"
                )
                params = {
                    "search": FALLBACK_SEARCH,
                    "filter": "has_abstract:true",
                    "per-page": min(PER_PAGE, max_records),
                    "cursor": "*",
                    "sort": "cited_by_count:desc",
                }
                fallback_response = requests.get(
                    OPENALEX_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                fallback_response.raise_for_status()
                fallback_payload = fallback_response.json()
                page_results = fallback_payload.get("results", [])
                cursor = fallback_payload.get("meta", {}).get("next_cursor")
                used_fallback = True

            if not page_results:
                break

        results.extend(page_results)
        cursor = payload.get("meta", {}).get("next_cursor")
        if not cursor:
            break

        time.sleep(0.1)

    return results[:max_records]


def map_openalex_work(work: Dict, research_domain: str = "General") -> Dict:
    openalex_id = safe_text(work.get("id"), max_length=500)
    title = safe_text(work.get("title"), max_length=2000)
    abstract = reconstruct_abstract(work.get("abstract_inverted_index") or {})
    abstract = safe_text(abstract, max_length=200000)

    authorships = work.get("authorships") or []
    authors = []
    for authorship in authorships:
        author_obj = authorship.get("author") or {}
        display_name = safe_text(author_obj.get("display_name"), max_length=300)
        if display_name:
            authors.append(display_name)

    source = ((work.get("primary_location") or {}).get("source") or {})
    venue_name = safe_text(source.get("display_name"), max_length=500)
    venue_type = safe_text(source.get("type"), max_length=100)

    issn_value = ""
    issn_l = source.get("issn_l")
    issn_list = source.get("issn")
    if isinstance(issn_l, str) and issn_l.strip():
        issn_value = issn_l.strip()
    elif isinstance(issn_list, list) and issn_list:
        first_issn = issn_list[0]
        if isinstance(first_issn, str):
            issn_value = first_issn.strip()

    publication_year = work.get("publication_year")
    try:
        publication_year = int(publication_year) if publication_year is not None else None
    except Exception:
        publication_year = None

    citation_count = work.get("cited_by_count")
    try:
        citation_count = int(citation_count) if citation_count is not None else 0
    except Exception:
        citation_count = 0

    text_content = safe_text(f"{title}\n\n{abstract}", max_length=220000)

    return {
        "openalex_id": openalex_id,
        "research_domain": research_domain,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "venue_name": venue_name,
        "venue_type": venue_type,
        "venue_issn": issn_value,
        "publication_year": publication_year,
        "citation_count": citation_count,
        "text_content": text_content,
    }


def upsert_reference_papers(pool: SimpleConnectionPool, records: List[Dict]) -> int:
    if not records:
        return 0

    connection = None
    cursor = None
    try:
        connection = pool.getconn()
        cursor = connection.cursor()

        values = [
            (
                rec["openalex_id"],
                rec["research_domain"],
                rec["title"],
                rec["abstract"],
                rec["authors"],
                rec["venue_name"],
                rec["venue_type"],
                rec["venue_issn"],
                rec["publication_year"],
                rec["citation_count"],
                rec["text_content"],
            )
            for rec in records
            if rec.get("openalex_id") and rec.get("title") and rec.get("abstract")
        ]

        if not values:
            return 0

        execute_values(
            cursor,
            """
            INSERT INTO reference_papers (
                openalex_id,
                research_domain,
                title,
                abstract,
                authors,
                venue_name,
                venue_type,
                venue_issn,
                publication_year,
                citation_count,
                text_content
            )
            VALUES %s
            ON CONFLICT (openalex_id)
            DO UPDATE SET
                abstract = EXCLUDED.abstract,
                research_domain = EXCLUDED.research_domain,
                authors = EXCLUDED.authors,
                venue_type = EXCLUDED.venue_type,
                venue_issn = EXCLUDED.venue_issn,
                citation_count = EXCLUDED.citation_count,
                text_content = EXCLUDED.text_content,
                updated_at = CURRENT_TIMESTAMP
            """,
            values,
        )

        connection.commit()
        return len(values)
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            pool.putconn(connection)


def main():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    pool = SimpleConnectionPool(minconn=1, maxconn=POOL_MAX_CONN, dsn=database_url)

    try:
        per_domain_limit = max(1, MAX_RECORDS // len(DOMAIN_SEARCHES))
        unique_records = {}

        for domain, search in DOMAIN_SEARCHES.items():
            print(f"Fetching up to {per_domain_limit} works for {domain}...")
            works = fetch_openalex_records(per_domain_limit, search=search)
            for work in works:
                work_id = work.get("id")
                if work_id and work_id not in unique_records:
                    unique_records[work_id] = map_openalex_work(work, domain)

        mapped_records = list(unique_records.values())
        print(f"Fetched {len(mapped_records)} unique works across {len(DOMAIN_SEARCHES)} domains")
        inserted_count = upsert_reference_papers(pool, mapped_records)

        print(f"Upserted {inserted_count} records into reference_papers")
    finally:
        pool.closeall()


if __name__ == "__main__":
    main()
