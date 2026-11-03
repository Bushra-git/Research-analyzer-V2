import fitz
import pytest
import analysis_tasks as tasks

def test_real_readability_changes_with_text():
    easy = tasks.extract_features('The cat sat on a mat. The dog ran home.')
    hard = tasks.extract_features('Multidisciplinary methodological considerations necessitate comprehensive institutional evaluation.')
    assert easy['readability'] > hard['readability']
    assert tasks.extract_features('')['readability'] is None

def test_section_detection_requires_headings_and_keeps_evidence():
    text = 'We discuss methods in this sentence.\nAbstract\nA study of crop water use.\n1. Introduction\nContext.\n2 Methods\nIrrigation design.\n3 Results\nCrops grew.\nReferences\nPrivate reference list.'
    assert tasks.detect_sections(text) == ['Abstract', 'Introduction', 'Methods', 'Results', 'References']
    assert 'Irrigation design' in tasks.matching_text(text)
    assert 'A study' in tasks.extract_summary(text)

def test_pdf_header_and_corruption():
    with pytest.raises(ValueError): tasks.extract_text_from_pdf(b'not a PDF')
    with pytest.raises(ValueError): tasks.extract_text_from_pdf(b'%PDF-broken')

def test_empty_pdf_has_actionable_error():
    with fitz.open() as document:
        document.new_page()
        blob = document.tobytes()
    with pytest.raises(ValueError, match='scanned PDF'):
        tasks.process_paper_analysis(blob)

def test_analysis_never_invents_quality_score(monkeypatch):
    text = 'Abstract\n' + 'We measure crop water use in a controlled field experiment. ' * 12 + '\nMethods\nWe record irrigation and growth.'
    monkeypatch.setattr(tasks, 'extract_text_from_pdf', lambda _: text)
    import reference_papers_similarity as references
    calls = []
    def search(*args, **kwargs):
        calls.append(kwargs)
        return {'papers': [], 'diagnostics': {'method': 'none'}}
    monkeypatch.setattr(references, 'find_reference_papers', search)
    result = tasks.process_paper_analysis(b'%PDF-mocked')
    assert result['score'] is None
    assert result['score_status'] == 'not_scientifically_validated'
    assert 'not peer review' in result['disclaimer']
    assert calls[0]['external_search'] is False

def test_scientific_words_do_not_manufacture_quality():
    features = tasks.extract_features('Conclusion. Discussion. Rigor. Novelty.')
    assert 'research_rigor' not in features
    assert features['citation_markers'] == 0
