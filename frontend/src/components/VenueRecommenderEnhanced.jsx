import { useEffect, useRef, useState } from 'react';
import api from '../api';

const defaults = { venue_type: 'any', open_access_only: false, medline_only: false, exclude_discontinued: true, min_coverage_year: 0, fee_status: 'any', max_apc: '', currency: 'USD' };
const safeLink = value => /^https?:\/\//i.test(value || '') ? value : null;
function FeeLabel({ fees }) {
  if (!fees || fees.status === 'unknown') return <><strong>Fee not verified</strong><small>Check the publisher’s fee policy</small></>;
  if (fees.status === 'free') return <><strong>Free to publish</strong><small>No APC or other fees reported to DOAJ</small></>;
  return <><strong>{fees.apc_prices?.length ? fees.apc_prices.map(p => `${p.currency} ${Number(p.amount).toLocaleString()}`).join(' / ') : 'Paid · amount not listed'}</strong><small>{fees.apc_prices?.length ? 'Listed article processing charge (APC)' : 'Publisher reports publication charges'}{fees.other_fees ? ' · Additional fees reported' : ''}</small></>;
}

export default function VenueRecommenderEnhanced({ jobId }) {
  const [filters, setFilters] = useState(defaults);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState(jobId ? 'recommend' : null);
  const [view, setView] = useState('list');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  const applied = useRef({ ...defaults, max_apc: null, query: '' });
  const serial = useRef(0);
  async function load(payload, selectedMode = mode) {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const id = ++serial.current;
    setBusy(true); setError(''); setResults(null);
    try {
      const { data } = await api.post(selectedMode === 'recommend' ? '/api/recommend' : '/api/venues',
        { ...payload, ...(selectedMode === 'recommend' ? { job_id: jobId } : {}) }, { timeout: 120000, signal: controller.signal });
      if (id === serial.current) setResults(data);
    } catch (err) { if (!controller.signal.aborted && id === serial.current) setError(err.response?.data?.error || 'Unable to retrieve venues. Try again.'); }
    finally { if (id === serial.current) setBusy(false); }
  }
  useEffect(() => {
    return () => { serial.current += 1; request.current?.abort(); };
    // Component remounts when its manuscript changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  function changeMode(next) {
    if (next === mode) return;
    request.current?.abort(); serial.current += 1;
    setMode(next); setResults(null); setError(''); setBusy(false);
    if (next === 'directory') load({ ...applied.current, page: 1 }, next);
  }
  function openDirectory() {
    setMode('directory');
    load({ ...defaults, max_apc: null, page: 1 }, 'directory');
  }
  function submit(event) {
    event.preventDefault();
    const payload = { ...filters, max_apc: filters.max_apc === '' ? null : Number(filters.max_apc), query, page: 1 };
    applied.current = payload; load(payload);
  }
  const change = (key, value) => setFilters(old => ({ ...old, [key]: value }));
  return <section className="venue-section" id="venues">
    <div className="workspace-heading"><div><p className="eyebrow">THE NEXT HOME FOR YOUR WORK</p><h2>Find your publication fit<span className="accent-dot">.</span></h2></div><span className="section-label">VENUE EXPLORER / 02</span></div>
    {mode === null && <div className="venue-toolbar"><button type="button" onClick={openDirectory}>Browse public directory</button><p>Explore publication venues when you are ready.</p></div>}
    {mode !== null && <><div className="venue-toolbar"><div className="segmented" aria-label="Venue discovery mode"><button type="button" aria-pressed={mode === 'directory'} onClick={() => changeMode('directory')}>Browse directory</button><button type="button" disabled={!jobId} aria-pressed={mode === 'recommend'} onClick={() => changeMode('recommend')}>Matched to your paper</button></div><p>{jobId ? 'Explore freely, or match against your manuscript.' : 'Browse now. Analyze a paper to unlock personal matches.'}</p></div>
    <div className="venue-layout">
      <form className="venue-filters" onSubmit={submit}>
        <div className="filter-heading"><h3>Refine your search</h3><span>☷</span></div>
        <fieldset disabled={busy}>
          {mode === 'directory' && <label>Search venues<input type="search" placeholder="Title, publisher, or subject" maxLength={200} value={query} onChange={e => setQuery(e.target.value)} /></label>}
          <label>Venue type<select value={filters.venue_type} onChange={e => change('venue_type', e.target.value)}><option value="any">All venue types</option><option value="journal">Journal</option><option value="conference">Conference</option><option value="book series">Book series</option></select></label>
          <label>Publication fees<select value={filters.fee_status} onChange={e => change('fee_status', e.target.value)}><option value="any">Any fee status</option><option value="free">Free to publish (reported)</option><option value="paid">Paid publication</option><option value="unknown">Fee not verified</option></select></label>
          <div className="budget-fields"><label>Maximum APC<input type="number" placeholder="No limit" min="0" max="10000000" step="0.01" value={filters.max_apc} onChange={e => change('max_apc', e.target.value)} /></label><label>Currency<select value={filters.currency} onChange={e => change('currency', e.target.value)}>{['USD', 'EUR', 'GBP', 'INR', 'CHF', 'CAD', 'AUD', 'JPY', 'BRL', 'CNY'].map(c => <option key={c}>{c}</option>)}</select></label></div>
          <small>Budget compares listed APCs in your selected currency. It excludes unknown amounts; other charges may apply.</small>
          <label>Coverage through at least<input type="number" min="0" max="2100" value={filters.min_coverage_year} onChange={e => change('min_coverage_year', Number(e.target.value))} /><small>0 means no coverage-year filter.</small></label>
          <div className="filter-checks">{Object.entries({ open_access_only: 'Open access only', medline_only: 'Medline only', exclude_discontinued: 'Exclude inactive venues' }).map(([key, label]) => <label className="check" key={key}><input type="checkbox" checked={filters[key]} onChange={e => change(key, e.target.checked)} />{label}</label>)}</div>
          <button type="submit" className="primary-action">{busy ? 'Finding venues…' : mode === 'recommend' ? 'Get recommendations' : 'Apply filters'}</button>
          <button type="button" className="subtle" onClick={() => { setFilters(defaults); setQuery(''); applied.current = { ...defaults, max_apc: null, query: '', page: 1 }; load(applied.current); }}>Reset filters</button>
        </fieldset>
      </form>
      <div className="venue-results" aria-busy={busy}>
        <div className="listing-heading"><div><h3>{mode === 'directory' ? 'Publication directory' : 'Your recommended venues'}</h3><span aria-live="polite">{results ? mode === 'directory' ? `${results.total?.toLocaleString()} venues · A–Z` : `${results.venues?.length || 0} recommendations · Ranked by relevance` : 'Discover a place for your research'}</span></div><div className="view-toggle" aria-label="Results layout"><button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}>List</button><button type="button" aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Cards</button></div></div>
        {error && <p className="error" role="alert">{error}</p>}
        {busy && <div className="venue-loading" role="status"><span className="processing-dot" /> Finding your next publication…</div>}
        {!busy && !results && !error && <div className="venue-empty"><span>↗</span><h3>Your next publication starts with a good fit.</h3><p>Choose your preferences and get recommendations for your paper.</p></div>}
        {results && <>
          {results.matching?.warning && <p className="notice">{results.matching.warning}</p>}
          {!results.venues?.length && <div className="venue-empty"><h3>No venues match these preferences.</h3><p>Try a broader subject or fee filter. Venues with unverified prices are excluded by a budget limit.</p></div>}
          <div className={`venue-items ${view}`}>{results.venues?.map((venue, i) => <article className="venue-item" key={venue.sourcerecord_id || `${venue.name}-${i}`}>
            <div className="venue-rank">{String((results.page ? (results.page - 1) * results.page_size : 0) + i + 1).padStart(2, '0')}</div>
            <div className="venue-main"><div className="venue-badges"><span>{venue.type || 'Journal'}</span>{venue.open_access && <span className="oa-badge">Open access</span>}{venue.medline_coverage && <span>Medline</span>}</div><h3>{venue.name}</h3><p>{venue.publisher || 'Publisher not recorded'}</p><div className="venue-subjects">{venue.matched_asjc_subjects?.slice(0, 3).join(' / ')}</div>{venue.match_score != null && <span className="relevance">{venue.match_score}/100 text relevance</span>}
              <details><summary>Venue details & fee sources</summary><p>{venue.reason}</p><p>Coverage: {venue.coverage_year_range || 'Unknown'} · ISSN: {venue.issn || 'Unknown'} · {venue.language || 'Language unknown'}</p>{venue.fees?.source && <p>Fee source: <a href={safeLink(venue.fees.source_url) || 'https://doaj.org'} target="_blank" rel="noopener noreferrer">DOAJ record ↗</a> · Retrieved {new Date(venue.fees.fetched_at).toLocaleDateString()}{venue.fees.source_updated_at && ` · Record updated ${venue.fees.source_updated_at.slice(0, 10)}`}</p>}{venue.fees?.other_fees && <p>Additional charges are reported. Review the publisher’s policy for the total.</p>}{venue.venue_warnings?.map(w => <p key={w}>{w}</p>)}</details>
            </div>
            <div className={`venue-cost ${venue.fees?.status || 'unknown'}`}><span className="cost-caption">PUBLICATION COST</span><FeeLabel fees={venue.fees} /><a href={safeLink(venue.fees?.fee_url) || safeLink(venue.fees?.journal_url) || `https://www.google.com/search?q=${encodeURIComponent(venue.name + ' official publication fees')}`} target="_blank" rel="noopener noreferrer">{safeLink(venue.fees?.fee_url) ? 'View fee policy' : 'Check publisher'} ↗</a></div>
          </article>)}</div>
          {mode === 'directory' && results.total > 0 && <nav className="pagination" aria-label="Venue pages"><button type="button" className="subtle" disabled={busy || results.page <= 1} onClick={() => load({ ...applied.current, page: results.page - 1 })}>← Previous</button><span>Page {results.page} of {results.pages}</span><button type="button" className="subtle" disabled={busy || results.page >= results.pages} onClick={() => load({ ...applied.current, page: results.page + 1 })}>Next →</button></nav>}
        </>}
        <p className="fee-disclaimer">Fee information comes from DOAJ’s public snapshot and may change. Amounts are advertised APCs, not a personal quote; taxes, waivers, and other charges can affect the total. Unknown never means free. Venue indexing metadata: January 2026. Relevance is not an acceptance probability.</p>
      </div>
    </div></>}
  </section>;
}
