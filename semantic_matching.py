"""Local, chunked semantic retrieval with a visible lexical fallback."""
import hashlib
import os
from collections import OrderedDict
from pathlib import Path
from threading import RLock

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
MODEL_PATH = os.getenv('EMBEDDING_MODEL_PATH', str(Path(__file__).parent / 'models' / 'all-MiniLM-L6-v2'))
_model = None
_failure = None
_lock = RLock()
_corpus_cache = OrderedDict()

def model_status():
    return {'model': MODEL_NAME, 'installed': Path(MODEL_PATH).is_dir(), 'loaded': _model is not None,
            'enabled': os.getenv('SEMANTIC_SIMILARITY_ENABLED', 'true').lower() == 'true',
            'fallback_reason': _failure}

def get_model():
    global _model, _failure
    with _lock:
        if _model is not None: return _model
        if _failure: return None
        if os.getenv('SEMANTIC_SIMILARITY_ENABLED', 'true').lower() != 'true':
            _failure = 'Semantic matching is disabled'; return None
        if not Path(MODEL_PATH).is_dir():
            _failure = 'Local embedding model is not installed'; return None
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            torch.set_num_threads(max(1, min(4, int(os.getenv('EMBEDDING_CPU_THREADS', '2')))))
            _model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True, trust_remote_code=False)
            return _model
        except Exception:
            _failure = 'Local embedding model could not load'
            return None

def chunks(text, size=150, overlap=25):
    words = str(text).split()
    return [' '.join(words[i:i+size]) for i in range(0, min(len(words), 6000), size-overlap)] or ['']

def embed_documents(model, documents):
    # Scientific words can span many tokens. Word-count windows alone silently
    # lose text at the encoder's limit, so use the installed model's tokenizer.
    budget = max(8, int(model.max_seq_length) - model.tokenizer.num_special_tokens_to_add(pair=False))
    overlap = min(32, budget // 4)
    pooled = []
    # Bound transient passage/vector allocations even for the full reference corpus.
    for offset in range(0, len(documents), 32):
        groups = []
        for text in documents[offset:offset + 32]:
            tokens = model.tokenizer.encode(str(text), add_special_tokens=False, truncation=True, max_length=8192)
            groups.append([model.tokenizer.decode(tokens[i:i + budget], skip_special_tokens=True)
                           for i in range(0, len(tokens), budget - overlap)] or [''])
        flat = [part for group in groups for part in group]
        vectors = model.encode(flat, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        start = 0
        for group in groups:
            value = np.mean(vectors[start:start+len(group)], axis=0)
            pooled.append(value / max(float(np.linalg.norm(value)), 1e-12))
            start += len(group)
    return np.asarray(pooled)

def rank_texts(query, documents, semantic=True):
    if not documents:
        return np.array([]), {'method': 'none', 'warning': 'No candidate documents available'}
    if not str(query).strip():
        return np.zeros(len(documents)), {'method': 'none', 'warning': 'No query text available'}
    try:
        vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=20000)
        matrix = vectorizer.fit_transform(documents)
        lexical = cosine_similarity(vectorizer.transform([query]), matrix).ravel()
    except ValueError:
        lexical = np.zeros(len(documents))
    model = get_model() if semantic else None
    if model is None:
        return lexical, {'method': 'tfidf', 'model': None, 'warning': _failure if semantic else None}
    try:
        digest = hashlib.sha256()
        for document in documents:
            value = document.encode()
            digest.update(len(value).to_bytes(8, 'big'))
            digest.update(value)
        key = digest.hexdigest()
        with _lock:
            corpus = _corpus_cache.get(key)
            if corpus is not None:
                _corpus_cache.move_to_end(key)
            if corpus is None:
                corpus = embed_documents(model, documents)
                _corpus_cache[key] = corpus
                if len(_corpus_cache) > 4: _corpus_cache.popitem(last=False)
            # Manuscript embeddings are deliberately never cached globally.
            query_vector = embed_documents(model, [query])[0]
        scores = np.clip(corpus @ query_vector, 0, 1)
        return .7 * scores + .3 * lexical, {'method': 'hybrid', 'model': MODEL_NAME,
            'semantic_weight': .7, 'lexical_weight': .3, 'warning': None}
    except Exception:
        return lexical, {'method': 'tfidf', 'model': None, 'warning': 'Semantic inference failed; lexical matching was used'}
