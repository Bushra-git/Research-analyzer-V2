import pandas as pd
import pytest
from recommender_full import load_venue_database_enhanced, normalize_venue, recommend_venues_enhanced, validate_preferences
from domain_detection import get_domain_stats
from semantic_matching import rank_texts

def venue(name, **overrides):
    value = {'Source Title': name, 'Active or Inactive': 'Active', 'Source Type': 'Journal',
        'Coverage': '2010-2025', '1700\nComputer Science': 'Computer Science', 'Open Access Status': 'Unpaywall Open Access'}
    value.update(overrides)
    return normalize_venue(value)

def test_strict_filters_exclude_ineligible_venues():
    good = venue('Computer Science Algorithms', **{'Medline-sourced Title? (See additional details under separate tab.)': 'Medline'})
    closed = {**good, 'name': 'Closed', 'open_access': False}
    inactive = {**good, 'name': 'Inactive', 'active_status': False}
    not_medline = {**good, 'name': 'Not Medline', 'medline_coverage': False}
    old = {**good, 'name': 'Old', 'last_coverage_year': 2000}
    result = recommend_venues_enhanced('computer science algorithms', None, '', {
        'open_access_only': True, 'exclude_discontinued': True, 'medline_only': True, 'min_coverage_year': 2020}, pd.DataFrame([good, closed, inactive, not_medline, old]))
    assert result['eligible_venues'] == 1
    assert [r['name'] for r in result['venues']] == ['Computer Science Algorithms']

def test_actual_dataset_medline_values():
    data = load_venue_database_enhanced()
    assert len(data) == 48151
    assert int(data.medline_coverage.sum()) == 5009
    assert int(data.open_access.sum()) == 8952

@pytest.mark.parametrize('payload', [{'medline_only': 'false'}, {'min_coverage_year': '2020'}, {'venue_type': 'bogus'}, {'acceptance': 'high'}, {'selected_subjects': ['bogus']}])
def test_invalid_preferences_rejected(payload):
    with pytest.raises(ValueError): validate_preferences(payload)

def test_unknown_domain_is_not_medicine():
    assert get_domain_stats('an entirely unclassified topic')['domain'] == 'General Research'

def test_statistics_count_matches_not_rows():
    data = pd.DataFrame({'Open Access Status': ['Open Access', ''], 'Active or Inactive': ['Active', 'Inactive']})
    stats = get_domain_stats('unknown', data)
    assert stats['oa_count'] == 1
    assert stats['active_count'] == 1

def test_retrieval_fallback_is_explicit():
    scores, details = rank_texts('quantum optics', ['quantum optical science', 'crop farming'])
    assert scores[0] > scores[1]
    assert details['method'] == 'tfidf'
    assert details['warning']
