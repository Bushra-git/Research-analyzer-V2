"""One analysis pipeline shared by the queue and tests. No model pickle loading."""
import hashlib
import json
import os
import re
from collections import Counter

import fitz

ANALYSIS_VERSION = 'writing-v3'
DISCLAIMER = ('These are English writing and document-structure observations, not peer review. '
              'They do not measure originality, correctness, research rigor, or acceptance probability.')
SECTION_PATTERN = re.compile(
    r'^\s*(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?'
    r'(abstract|introduction|related work|literature review|background|methods?|methodology|'
    r'materials and methods|results?|discussion|conclusions?|references|bibliography)\s*[:.]?\s*$', re.I | re.M)
ALIASES = {'method': 'Methods', 'methodology': 'Methods', 'materials and methods': 'Methods',
           'result': 'Results', 'conclusions': 'Conclusion', 'bibliography': 'References',
           'literature review': 'Related Work', 'background': 'Related Work'}

def extract_text_from_pdf(file):
    blob = file.read() if hasattr(file, 'read') else file
    if not blob.startswith(b'%PDF-'):
        raise ValueError('Upload a valid PDF file')
    try:
        with fitz.open(stream=blob, filetype='pdf') as doc:
            if doc.needs_pass:
                raise ValueError('Password-protected PDFs are not supported. Upload an unlocked copy.')
            if len(doc) > int(os.getenv('MAX_PDF_PAGES', '100')):
                raise ValueError('PDF exceeds the 100-page analysis limit')
            parts, total = [], 0
            for page in doc:
                value = page.get_text()
                if len(value.strip()) < 30 and os.getenv('OCR_ENABLED', 'false').lower() == 'true':
                    try:
                        value = page.get_text(textpage=page.get_textpage_ocr(language='eng', dpi=150, full=True))
                    except RuntimeError:
                        raise ValueError('OCR is unavailable. Upload a PDF containing selectable text.')
                total += len(value)
                if total > 500000:
                    raise ValueError('PDF contains too much text; split it into smaller documents')
                parts.append(value)
            return '\n'.join(parts)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('This PDF cannot be read. Export a new PDF and try again.') from exc

def split_sections(text):
    matches = list(SECTION_PATTERN.finditer(text))
    return {ALIASES.get(m.group(1).lower(), m.group(1).title()): text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()
            for i, m in enumerate(matches)}

def detect_sections(text):
    return list(split_sections(text))

def syllables(word):
    # English vowel-group estimate; the UI explicitly labels readability as approximate.
    word = word.lower()
    count = len(re.findall(r'[aeiouy]+', word))
    if word.endswith('e') and not word.endswith(('le', 'ye')) and count > 1:
        count -= 1
    return max(1, count)

def extract_features(text):
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)
    sentences = [s for s in re.split(r'[.!?]+(?:\s|$)', text.strip()) if re.search(r'[A-Za-z]', s)]
    n, count = len(words), len(sentences)
    reading = 206.835 - 1.015 * n / max(1, count) - 84.6 * sum(map(syllables, words)) / max(1, n) if n else None
    return {'word_count': n, 'sentence_count': count,
            'avg_word_length': round(sum(map(len, words)) / n, 2) if n else 0,
            'average_sentence_words': round(n / max(1, count), 1),
            'readability': round(reading, 1) if reading is not None else None,
            'readability_method': 'Flesch Reading Ease; estimated English syllables',
            'citation_markers': len(re.findall(r'\[\d+(?:\s*[,–-]\s*\d+)*\]|\([A-Z][^()\n]{0,60}\b(?:19|20)\d{2}[a-z]?\)', text))}

def extract_summary(text, max_sentences=5):
    sections = split_sections(text)
    if sections.get('Abstract'):
        return ' '.join(sections['Abstract'].split())[:2000]
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 35][:100]
    if not sentences:
        return ' '.join(text.split())[:1000]
    frequency = Counter(re.findall(r'\b[a-z]{4,}\b', text.lower()))
    scores = [sum(frequency[w] for w in re.findall(r'\b[a-z]{4,}\b', s.lower())) / max(1, len(s.split())) for s in sentences]
    chosen = sorted(sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)[:max_sentences])
    return ' '.join(sentences[i] for i in chosen)[:2000]

def matching_text(text):
    sections = split_sections(text)
    # Preserve the abstract and evidence-bearing sections, exclude reference lists.
    first_heading = SECTION_PATTERN.search(text)
    lead = text[:first_heading.start()] if first_heading else text
    pieces = [lead[:800]] + [sections[k][:6000] for k in ('Abstract', 'Introduction', 'Methods', 'Results', 'Discussion', 'Conclusion') if k in sections]
    if len(pieces) == 1:
        pieces = [text[:24000]]
    return '\n\n'.join(pieces)[:36000]

def generate_recommendations(text, features, score=None):
    sections = detect_sections(text)
    tips = []
    if not sections:
        tips.append({'title': 'Check section extraction', 'description': 'No standard headings were detected. This may reflect PDF layout or your document type; it does not establish missing content.'})
    if features['average_sentence_words'] > 30:
        tips.append({'title': 'Review long sentences', 'description': 'Average sentence length exceeds 30 words. Consider splitting sentences where that improves clarity.'})
    if not features['citation_markers']:
        tips.append({'title': 'Check citation formatting', 'description': 'No supported numeric or author-year markers were detected. Other citation styles may not be recognized.'})
    tips.append({'title': 'Check the target venue', 'description': 'Compare length, structure, reporting requirements, and references with the venue’s author guidelines. These vary by discipline and article type.'})
    return tips

def process_paper_analysis(file_bytes, file_name='uploaded.pdf', external_search=False):
    try:
        from rq import get_current_job
        job = get_current_job()
    except Exception:
        job = None
    def stage(name):
        if job:
            job.meta['stage'] = name
            job.save_meta()
    stage('extracting_text')
    text = extract_text_from_pdf(file_bytes)
    if len(text.split()) < 50:
        raise ValueError('Not enough readable text. This may be a scanned PDF. Upload selectable text or enable server OCR.')
    stage('measuring_writing')
    features = extract_features(text)
    from domain_detection import get_domain_stats
    domain = get_domain_stats(text)
    stage('matching_reference_papers')
    from reference_papers_similarity import find_reference_papers
    references = find_reference_papers(matching_text(text), top_k=5, external_search=external_search)
    result = {'analysis_version': ANALYSIS_VERSION, 'score': None, 'score_status': 'not_scientifically_validated',
              'features': features, 'summary': extract_summary(text), 'summary_method': 'extractive',
              'recommendations': generate_recommendations(text, features), 'disclaimer': DISCLAIMER,
              'domain_stats': domain, 'file_name': file_name, 'detected_sections': detect_sections(text),
              'reference_papers': references['papers'], 'reference_search': references['diagnostics'],
              'external_search': external_search, '_matching_text': matching_text(text)}
    stage('done')
    return result

def process_uploaded_paper(job_id, file_name, external_search=False):
    from queue_resources import redis_connection
    from rq import get_current_job
    job = get_current_job()
    key = f'upload:{job_id}'
    try:
        cache_key = job.meta.get('cache_key') if job else None
        cached = redis_connection.get(cache_key) if cache_key else None
        if cached and not redis_connection.exists(f'deleted:{job_id}'):
            result = json.loads(cached)
            result.update(file_name=file_name, cached=True)
            persist_completion(job_id, job.meta.get('owner_key'), result)
            return result
        blob = redis_connection.get(key)
        if not blob:
            raise ValueError('Upload expired before processing. Please upload again.')
        if redis_connection.exists(f'deleted:{job_id}'):
            return {'error': 'Analysis cancelled'}
        result = process_paper_analysis(blob, file_name, external_search)
        if redis_connection.exists(f'deleted:{job_id}'):
            return {'error': 'Analysis cancelled'}
        ttl = int(os.getenv('RETENTION_HOURS', '24')) * 3600
        cache_key = job.meta.get('cache_key') if job else None
        if cache_key:
            # Do not recreate private cache data after a simultaneous deletion.
            redis_connection.eval("if redis.call('EXISTS', KEYS[2]) == 0 then return redis.call('SETEX', KEYS[1], ARGV[1], ARGV[2]) end", 2,
                                  cache_key, f'deleted:{job_id}', ttl, json.dumps(result))
        if job:
            persist_completion(job_id, job.meta.get('owner_key'), result)
        return result
    except ValueError as error:
        if job:
            job.meta['safe_error'] = str(error)
            job.save_meta()
        raise
    finally:
        redis_connection.delete(key)

def persist_completion(job_id, owner_key, result):
    """Save successful results even if the browser closed. Ownership is never mutated."""
    if not os.getenv('DATABASE_URL') or not owner_key:
        return
    try:
        import psycopg2
        from psycopg2.extras import Json
        from contextlib import closing
        public = {key: value for key, value in result.items() if not key.startswith('_')}
        with closing(psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=5)) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute('''UPDATE "Analysis" SET status = 'finished', result = %s, features = %s, summary = %s
                        WHERE "jobId" = %s AND "ownerKey" = %s AND "expiresAt" > NOW()''',
                        (Json(public), Json(public['features']), public['summary'], job_id, owner_key))
    except Exception:
        # Status polling can repair this write later. Never log manuscript content.
        print('Analysis history persistence unavailable; result remains in the private queue')
