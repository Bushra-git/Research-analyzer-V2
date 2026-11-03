"""Legacy import compatibility. Paper search no longer returns venue titles as papers."""
from reference_papers_similarity import get_reference_similar_papers

def compute_similar_papers(paper_text, dataset=None, detected_domain=None, top_k=5, prefilter_threshold=20):
    return [{**paper, 'score': paper['similarity_score']} for paper in get_reference_similar_papers(paper_text, top_k)]
