import numpy as np
import semantic_matching as matching
import reference_papers_similarity as references


def test_blank_query_does_not_recommend_arbitrary_papers():
    scores, diagnostics = matching.rank_texts('   ', ['quantum optics', 'crop farming'])
    assert not scores.any()
    assert diagnostics['method'] == 'none'


def test_semantic_candidates_are_not_lost_to_keyword_gate(monkeypatch):
    rows = [{'title': f'Paper {i}', 'text_content': f'Text {i}'} for i in range(230)]
    monkeypatch.setattr(references, '_load_reference_rows', lambda: rows)
    def rank(query, documents, semantic=True):
        assert len(documents) in (200, 230)
        scores = np.zeros(len(documents))
        scores[0] = .9
        return scores, {'method': 'hybrid'}
    monkeypatch.setattr(references, 'rank_texts', rank)
    result = references.find_reference_papers('a paraphrase')
    assert result['papers'][0]['title'] == 'Paper 0'
    assert result['diagnostics']['candidate_count'] == 230
    assert result['diagnostics']['semantic_candidate_count'] == 200


def test_chunking_uses_token_budget_and_preserves_tail():
    class Tokenizer:
        def num_special_tokens_to_add(self, pair): return 2
        def encode(self, text, **kwargs): return list(range(35))
        def decode(self, tokens, **kwargs): return ' '.join(map(str, tokens))
    class Model:
        tokenizer = Tokenizer()
        max_seq_length = 12
        def encode(self, passages, **kwargs):
            assert all(len(p.split()) <= 10 for p in passages)
            assert passages[-1].split()[-1] == '34'
            return np.ones((len(passages), 3))
    vectors = matching.embed_documents(Model(), ['technical terminology'])
    assert vectors.shape == (1, 3)
    np.testing.assert_allclose(np.linalg.norm(vectors[0]), 1)


def test_inference_failure_keeps_lexical_results(monkeypatch):
    monkeypatch.setattr(matching, 'get_model', lambda: object())
    def broken(*args): raise RuntimeError('inference unavailable')
    monkeypatch.setattr(matching, 'embed_documents', broken)
    matching._corpus_cache.clear()
    scores, diagnostics = matching.rank_texts('quantum optics', ['quantum optics', 'crop farming'])
    assert scores[0] > scores[1]
    assert diagnostics['method'] == 'tfidf'
    assert 'failed' in diagnostics['warning']
