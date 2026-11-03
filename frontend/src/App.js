import { useCallback, useEffect, useState } from 'react';
import api from './api';
import AuthPanel from './components/AuthPanel';
import VenueRecommenderEnhanced from './components/VenueRecommenderEnhanced';
import ResearchScene from './components/ResearchScene';
import './App.css';

export default function App() {
  const [session, setSession] = useState(null);
  const [file, setFile] = useState(null);
  const [external, setExternal] = useState(false);
  const [jobId, setJobId] = useState(() => sessionStorage.getItem('active_analysis') || '');
  const [polling, setPolling] = useState(Boolean(jobId));
  const [submitting, setSubmitting] = useState(false);
  const [stage, setStage] = useState('queued');
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [dragging, setDragging] = useState(false);
  function selectFile(next) {
    setError('');
    if (next && (!/\.pdf$/i.test(next.name) || next.size > 15 * 1024 * 1024 || next.size === 0)) {
      setFile(null); setError('Choose a non-empty PDF that is 15MB or smaller.'); return;
    }
    setFile(next || null);
  }
  const refreshHistory = useCallback(async () => {
    const response = await api.get('/api/history'); setHistory(response.data.history);
  }, []);
  const refreshSession = useCallback(async () => {
    const response = await api.get('/api/session'); setSession(response.data);
    await refreshHistory();
  }, [refreshHistory]);
  useEffect(() => {
    // Retire legacy bearer credentials; only HttpOnly session cookies authenticate requests.
    localStorage.removeItem('research_analyzer_token'); localStorage.removeItem('research_analyzer_user');
    refreshSession().catch(() => setError('Unable to load your session. Refresh to try again.'));
  }, [refreshSession]);
  useEffect(() => {
    if (!jobId || !polling || !session) return;
    let cancelled = false, timer, failures = 0;
    const controller = new AbortController();
    const started = Date.now();
    sessionStorage.setItem('active_analysis', jobId);
    async function poll() {
      if (cancelled) return;
      if (Date.now() - started > 360000) { setPolling(false); setError('This is taking longer than expected. Resume checking or cancel the analysis.'); return; }
      try {
        const response = await api.get(`/api/status/${jobId}`, { signal: controller.signal });
        if (cancelled) return;
        failures = 0;
        const result = response.data;
        setStage(result.stage || result.status);
        if (result.status === 'finished') {
          setData(result.result); setPolling(false); sessionStorage.removeItem('active_analysis');
          refreshHistory().catch(() => {}); return;
        }
        if (['failed', 'cancelled'].includes(result.status)) {
          setPolling(false); setError(result.error || 'Analysis could not complete. Try an unlocked PDF containing selectable text.'); sessionStorage.removeItem('active_analysis'); return;
        }
      } catch (err) {
        if (cancelled) return;
        failures += 1;
        if ([401, 404].includes(err.response?.status) || failures >= 3) {
          setPolling(false); setError(err.response?.data?.error || 'Connection interrupted. You can resume checking.'); return;
        }
      }
      timer = setTimeout(poll, Math.min(1000 * (failures + 1), 5000));
    }
    poll();
    return () => { cancelled = true; clearTimeout(timer); controller.abort(); };
  }, [jobId, polling, session, refreshHistory]);
  async function analyze(event) {
    event.preventDefault(); setError('');
    if (!file) { setError('Please select a PDF to analyze'); return; }
    if (file.size > 15 * 1024 * 1024) { setError('PDF must be 15MB or smaller'); return; }
    setSubmitting(true); setData(null);
    try {
      const form = new FormData(); form.append('file', file); form.append('external_search', String(external));
      const response = await api.post('/api/analyze', form);
      setJobId(response.data.job_id); setStage('queued'); setPolling(true);
      refreshSession().catch(() => setError('Your paper was submitted, but account usage could not refresh.'));
    } catch (err) { setError(err.response?.data?.error || 'Unable to submit the PDF. Check your connection and try again.'); }
    finally { setSubmitting(false); }
  }
  async function remove(id) {
    setDeleting(true); setError('');
    try {
      await api.delete(`/api/analyses/${id}`);
      if (id === jobId) { setPolling(false); setJobId(''); setData(null); sessionStorage.removeItem('active_analysis'); }
      await refreshHistory();
    } catch (err) { setError(err.response?.data?.error || 'Could not delete the analysis. Please retry.'); }
    finally { setDeleting(false); }
  }
  async function accountChanged() {
    setPolling(false); setJobId(''); setData(null); setHistory([]); sessionStorage.removeItem('active_analysis'); await refreshSession();
  }
  const limited = session && !session.user && session.guestUsed >= session.guestLimit;
  return <main id="top">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <nav className="topbar" aria-label="Main navigation"><a className="brand" href="#top"><span className="brand-mark">↗</span> paperlane<span className="brand-light">RESEARCH, IN MOTION.</span></a><div className="nav-links"><a href="#workspace">Workspace</a><a href="#venues">Venue explorer</a><a href="#history">My library</a></div></nav>
    <header className="hero"><div className="hero-copy"><p className="eyebrow">YOUR RESEARCH DASHBOARD</p><h1>Understand your paper.<br />Move your research <em>forward.</em></h1>
      <p className="hero-description">Analyze your manuscript, discover meaningful research connections, and find publication venues that align with your subject and goals.</p><a className="hero-link" href="#workspace">Open workspace <span>↗</span></a><div className="hero-notes"><span>01 / Analyze</span><span>02 / Discover</span><span>03 / Decide</span></div></div><ResearchScene /></header>
    <div className="workspace-heading" id="workspace"><div><p className="eyebrow">YOUR RESEARCH WORKSPACE</p><h2>Your next breakthrough starts here.</h2></div><span className="workspace-caption">One paper. A more informed next step.</span></div>
    <AuthPanel user={session?.user} onAuthenticated={accountChanged} />
    <div className="workspace-grid"><section className="card upload-card">
      <div className="section-heading"><span className="step-number">01</span><div><h2>Analyze a paper</h2><p className="muted">Bring your ideas. We’ll help you see the connections.</p></div></div>
      <form onSubmit={analyze}>
        <div className={`upload-zone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`} onDragOver={e => { e.preventDefault(); if (!polling && !submitting) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!polling && !submitting) selectFile(e.dataTransfer.files?.[0]); }}>
          <span className="upload-symbol" aria-hidden="true">↥</span><strong>{file ? file.name : 'Your next discovery starts here'}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready to analyze` : 'Drop your manuscript here, or browse your files'}</span>
          <label className="file-label">Upload research paper<input type="file" accept=".pdf,application/pdf" disabled={polling || submitting} onChange={e => selectFile(e.target.files?.[0])} /></label><small>PDF · Up to 15MB · Maximum 100 pages</small>
        </div>
        <label className="check"><input type="checkbox" checked={external} onChange={e => setExternal(e.target.checked)} disabled={polling || submitting} />Allow external OpenAlex search for this paper</label>
        <p className="muted">Off by default. If enabled, selected manuscript keywords are sent to OpenAlex. Local analysis and model inference stay on this server.</p>
        <p className="muted">PDF bytes are removed after processing (or expire within 15 minutes). Results and matching excerpts expire after {session?.retentionHours || 24} hours and can be deleted sooner. Guest history is private to this browser session.</p>
        {session && !session.user && <p>Guest analyses used: {session.guestUsed}/{session.guestLimit}. {limited && 'Sign in to continue.'}</p>}
        <button type="submit" disabled={!session || submitting || polling || limited}>{submitting ? 'Uploading…' : 'Analyze paper'}</button>
      </form>
      {polling && <div className="processing" role="status"><span className="processing-dot" /> Processing: {stage.replaceAll('_', ' ')}…<small>You can close this page and resume from history.</small></div>}
      {jobId && !data && <div className="actions">
        {!polling && <button onClick={() => { setError(''); setPolling(true); }}>Resume checking</button>}
        <button disabled={deleting} onClick={() => remove(jobId)}>Cancel and delete analysis</button>
      </div>}
      {error && <p role="alert" className="error">{error}</p>}
      {!session && error && <button type="button" className="subtle" onClick={() => { setError(''); refreshSession().catch(() => setError('Unable to load your session. Retry when your connection is available.')); }}>Retry connection</button>}
    </section><aside className="workspace-aside"><p className="eyebrow">LESS GUESSWORK. MORE MOMENTUM.</p><h2>Research with<br /><em>a clearer direction.</em></h2><div className="feature-item"><span>↗</span><div><h3>See your writing clearly</h3><p>Structure, readability, and an extractive summary to guide your next revision.</p></div></div><div className="feature-item"><span>⌘</span><div><h3>Find the connections</h3><p>Discover related literature through local semantic and keyword matching.</p></div></div><div className="feature-item"><span>◎</span><div><h3>Explore the right venues</h3><p>Filter publication venues around your subject and publishing preferences.</p></div></div><div className="aside-note">Built to inform your judgment.<br />Writing observations are not peer review or an acceptance prediction.</div></aside></div>
    {data && <>
      <section className="card"><h2>Writing and structure observations</h2><p className="notice">{data.disclaimer}</p>
        <div className="metrics">
          <div><strong>{data.features.word_count.toLocaleString()}</strong><span>English word tokens</span></div>
          <div><strong>{data.features.sentence_count}</strong><span>Estimated sentences</span></div>
          <div><strong>{data.features.readability ?? 'Unavailable'}</strong><span>Approximate Flesch Reading Ease</span></div>
          <div><strong>{data.features.citation_markers}</strong><span>Detected citation markers</span></div>
        </div>
        <p>Readability uses an English syllable estimate. Technical vocabulary, formulas, PDF extraction, and other languages can distort it. Citation markers do not verify sources.</p>
        <p><strong>Detected headings:</strong> {data.detected_sections.join(', ') || 'None recognized'}</p>
        <p><strong>Keyword-based domain:</strong> {data.domain_stats.domain}. This is a heuristic label, not a calibrated prediction.</p>
        {data.recommendations.map(tip => <article key={tip.title}><h3>{tip.title}</h3><p>{tip.description}</p></article>)}
      </section>
      <section className="card"><h2>Extractive summary</h2><p>{data.summary}</p><small>Selected text from the manuscript; review it against the original.</small></section>
      <section className="card"><h2>Related papers</h2>
        <p>Matching method: {data.reference_search?.method}. Similarity measures textual relevance, not support for your conclusions.</p>
        {data.reference_search?.warning && <p className="notice">{data.reference_search.warning}</p>}
        {data.reference_search?.warnings?.map(w => <p className="notice" key={w}>{w}</p>)}
        {!data.reference_papers.length && <p>No related papers are available for this analysis.</p>}
        {data.reference_papers.map((paper, i) => <article className="result" key={paper.openalex_id || i}>
          <h3>{paper.title}</h3><p>{paper.venue_name} · {paper.publication_year} · Similarity {(paper.similarity_score * 100).toFixed(1)}/100</p>
          <p>{paper.abstract}</p>
          {/^(https:\/\/openalex\.org\/|https:\/\/doi\.org\/)/.test(paper.doi || paper.openalex_id || '') && <a href={paper.doi || paper.openalex_id} target="_blank" rel="noopener noreferrer">View source</a>}
        </article>)}
      </section>

    </>}
    {session && <VenueRecommenderEnhanced key={data ? jobId : "directory"} jobId={data ? jobId : null} />}
    <section className="card" id="history"><p className="eyebrow">PICK UP WHERE YOU LEFT OFF</p><h2>Your recent analyses</h2><p>Only this session’s or signed-in account’s records appear here. Signing in starts account history; it does not transfer guest records.</p>
      <button className="subtle" onClick={() => refreshHistory().catch(() => setError('History is unavailable.'))}>Refresh history</button>
      {!history.length && <div className="empty-history"><span aria-hidden="true">▤</span><div><strong>A clean slate for your next idea.</strong><p>No saved analyses. Upload a paper to begin your research journey.</p></div></div>}
      {history.map(item => <article className="history" key={item.jobId}><div><strong>{item.paperFilename}</strong><p>{item.status} · Expires {new Date(item.expiresAt).toLocaleString()}</p></div>
        <div className="actions"><button onClick={() => { setData(null); setError(''); setJobId(item.jobId); setPolling(true); }}>Open</button><button disabled={deleting} onClick={() => remove(item.jobId)}>Delete</button></div>
      </article>)}
    </section><footer><a className="brand" href="#top">paperlane ↗</a><span>Made for curious minds. Built around your privacy.</span></footer>
  </main>;
}
