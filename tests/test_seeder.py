from types import SimpleNamespace
from datetime import datetime
import seed_life_science_data as seeder

def test_seed_insert_supplies_updated_at_without_database_default(monkeypatch):
    calls = []
    cursor = SimpleNamespace(close=lambda: None)
    connection = SimpleNamespace(cursor=lambda: cursor, commit=lambda: None, rollback=lambda: None)
    pool = SimpleNamespace(getconn=lambda: connection, putconn=lambda c: None)
    monkeypatch.setattr(seeder, 'execute_values', lambda cursor, sql, values: calls.append((sql, values)))
    record = dict(openalex_id='test:id', research_domain='Test', title='Title', abstract='Abstract', authors=[],
                  venue_name='Venue', venue_type='journal', venue_issn=None, publication_year=2025, citation_count=0, text_content='Text')
    assert seeder.upsert_reference_papers(pool, [record]) == 1
    sql, values = calls[0]
    assert 'updated_at' in sql.split('VALUES')[0]
    assert isinstance(values[0][-1], datetime)
