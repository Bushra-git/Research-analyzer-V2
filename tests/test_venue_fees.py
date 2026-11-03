import pandas as pd
import pytest
from venue_fees import parse_fee_record, fees_for
from recommender_full import normalize_venue, list_venues, recommend_venues_enhanced, validate_preferences


def row(name, status='unknown', prices=None):
    item = normalize_venue({'Source Title': name, 'Source Type': 'Journal', 'Active or Inactive': 'Active', '1700\nComputer Science': 'Computer Science'})
    item['fees'] = {'status': status, 'apc_prices': prices or []}
    return item


def test_free_requires_explicit_absence_of_all_charges():
    assert parse_fee_record({'APC': 'No', 'Has other fees': 'No'}, 'today')['status'] == 'free'
    assert parse_fee_record({'APC': 'No'}, 'today')['status'] == 'unknown'
    assert parse_fee_record({'APC': 'No', 'Has other fees': 'Yes'}, 'today')['status'] == 'paid'
    assert fees_for('invalid')['status'] == 'unknown'


def test_original_currencies_and_safe_links_preserved():
    fees = parse_fee_record({'APC': 'Yes', 'APC amount': '7000 UAH; 165 USD; 155 EUR', 'Journal URL': 'javascript:alert(1)'}, 'today')
    assert fees['apc_prices'] == [{'amount': 7000, 'currency': 'UAH'}, {'amount': 165, 'currency': 'USD'}, {'amount': 155, 'currency': 'EUR'}]
    assert fees['journal_url'] is None
    assert not parse_fee_record({'APC': 'Yes', 'APC amount': '1,500 USD'}, 'today')['apc_prices']


def test_budget_never_treats_unknown_or_other_currency_as_free():
    db = pd.DataFrame([row('A free', 'free'), row('B paid', 'paid', [{'amount': 100, 'currency': 'USD'}]), row('C euro', 'paid', [{'amount': 50, 'currency': 'EUR'}]), row('D unknown'), row('E expensive', 'paid', [{'amount': 500, 'currency': 'USD'}])])
    result = list_venues({'max_apc': 200, 'currency': 'USD'}, db)
    assert [r['name'] for r in result['venues']] == ['A free', 'B paid']
    assert list_venues({'fee_status': 'free'}, db)['total'] == 1
    assert list_venues({'fee_status': 'unknown'}, db)['total'] == 1


def test_same_fee_filter_applies_to_recommendations():
    db = pd.DataFrame([row('Computer Science Free', 'free'), row('Computer Science Paid', 'paid')])
    result = recommend_venues_enhanced('computer science', None, '', {'fee_status': 'free'}, db)
    assert result['eligible_venues'] == 1
    assert result['venues'][0]['fees']['status'] == 'free'


def test_directory_search_and_pagination_are_stable():
    db = pd.DataFrame([row('C Journal'), row('A Journal'), row('B Journal')])
    result = list_venues({'query': 'computer', 'page': 2, 'page_size': 1}, db)
    assert result['total'] == 3 and result['pages'] == 3
    assert result['venues'][0]['name'] == 'B Journal'
    assert not list_venues({'query': 'no match'}, db)['venues']


@pytest.mark.parametrize('data', [{'fee_status': 'cheap'}, {'max_apc': -1}, {'max_apc': True}, {'max_apc': float('nan')}, {'currency': 'usd'}])
def test_invalid_fee_filters_rejected(data):
    with pytest.raises(ValueError): validate_preferences(data)


@pytest.mark.parametrize('data', [{'page': 0}, {'page_size': 100}, {'page': True}, {'query': ['bad']}])
def test_invalid_directory_query_rejected(data):
    with pytest.raises(ValueError): list_venues(data, pd.DataFrame([row('A')]))
