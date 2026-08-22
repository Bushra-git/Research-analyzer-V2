import io
import json
from types import SimpleNamespace


def test_extract_features_basic():
    import app as app_module

    text = "Hello world. Another sentence."
    feats = app_module.extract_features(text)
    assert feats["word_count"] == 4
    assert feats["sentence_count"] == 2
    assert feats["avg_word_length"] > 0


def test_extract_summary_abstract_extraction():
    import app as app_module

    text = (
        "Abstract\n"
        "This is a test abstract with enough content to be extracted properly. "
        "It should stop before Introduction."
        "\n\nIntroduction\n"
        "Some intro."
        ""
    )

    summary = app_module.extract_summary(text)
    assert "test abstract" in summary.lower()
    assert len(summary) > 20


def test_generate_recommendations_returns_list():
    import app as app_module

    text = "word " * 300
    features = {"word_count": 300, "sentence_count": 10, "avg_word_length": 4.0}
    recs = app_module.generate_recommendations(text, features, score=4.0)

    assert isinstance(recs, list)
    assert recs
    assert "title" in recs[0]
    assert "description" in recs[0]


def test_health_reports_queue_count_as_int(client):
    resp = client.get("/health")
    assert resp.status_code in (200, 503)
    payload = resp.get_json()
    assert isinstance(payload["queue"], int)


def test_predict_missing_file_returns_400(client):
    resp = client.post("/predict", data={})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["error"] == "No file uploaded"


def test_predict_non_pdf_returns_400(client):
    resp = client.post(
        "/predict",
        data={"file": (io.BytesIO(b"not a pdf"), "x.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["error"] == "Only PDF files are allowed"


def test_predict_success_returns_required_fields(client):
    import app as app_module

    # Monkeypatching done via conftest for PDF extraction/dataset/model.
    # Ensure deterministic model prediction if needed.
    app_module.model = SimpleNamespace(predict=lambda df: [8.0])

    resp = client.post(
        "/predict",
        data={"file": (io.BytesIO(b"%PDF-1.4 dummy"), "paper.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    payload = resp.get_json()

    assert "score" in payload
    assert "features" in payload
    assert "summary" in payload
    assert "recommendations" in payload
    assert "similar_papers" in payload
    assert "domain_stats" in payload


def test_recommend_success_returns_venues(client, monkeypatch):
    import app as app_module

    def fake_recommend_venues_enhanced(**_kwargs):
        return {
            "venues": [
                {
                    "name": "Journal X",
                    "match_score": 88,
                    "type": "journal",
                    "reason": "mock reason",
                    "publisher": "Pub",
                    "active_status": True,
                    "coverage_year_range": "2010-2020",
                    "open_access": True,
                    "medline_coverage": True,
                    "language": "English",
                    "matched_asjc_subjects": ["CS.AI"],
                    "sourcerecord_id": "ABC123",
                }
            ],
            "paper_domain": "Computer Science & AI",
            "matches_found": 1,
            "total_venues_evaluated": 1,
        }

    monkeypatch.setattr(app_module, "recommend_venues_enhanced", fake_recommend_venues_enhanced)
    monkeypatch.setattr(app_module, "get_reference_similar_papers", lambda _text, top_k=5: [])

    resp = client.post(
        "/recommend",
        data=json.dumps(
            {
                "paper_text": "Machine learning method for images. " * 10,
                "paper_score": 7.0,
                "paper_topic": "",
                "venue_type": "journal",
                "indexing": ["Any"],
                "fee_pref": "Any",
                "acceptance": "Any",
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["venues"][0]["name"] == "Journal X"


def test_recommend_returns_reference_papers(client, monkeypatch):
    import app as app_module

    def fake_recommend_venues_enhanced(**_kwargs):
        return {
            "venues": [{"name": "Journal X", "match_score": 88}],
            "paper_domain": "Biomedical & Medicine",
            "matches_found": 1,
            "total_venues_evaluated": 1,
        }

    def fake_reference_matches(_text, top_k=5):
        return [
            {
                "title": "Life Science Paper",
                "abstract": "Study on protein pathways",
                "authors": ["A. Author", "B. Author"],
                "venue_name": "Open Journal of Biology",
                "venue_type": "journal",
                "venue_issn": "1234-5678",
                "publication_year": 2025,
                "citation_count": 42,
                "similarity_score": 0.8123,
            }
        ][:top_k]

    monkeypatch.setattr(app_module, "recommend_venues_enhanced", fake_recommend_venues_enhanced)
    monkeypatch.setattr(app_module, "get_reference_similar_papers", fake_reference_matches)

    resp = client.post(
        "/recommend",
        data=json.dumps(
            {
                "paper_text": "Biomedical methods for pathway analysis and clinical biomarkers. " * 10,
                "paper_score": 7.2,
                "reference_top_k": 3,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert "reference_papers" in payload
    assert payload["reference_papers"][0]["venue_name"] == "Open Journal of Biology"


def test_recommend_supports_file_when_text_missing(client, monkeypatch):
    import app as app_module

    def fake_recommend_venues_enhanced(**_kwargs):
        return {
            "venues": [{"name": "Journal X", "match_score": 88}],
            "paper_domain": "Biomedical & Medicine",
            "matches_found": 1,
            "total_venues_evaluated": 1,
        }

    monkeypatch.setattr(app_module, "recommend_venues_enhanced", fake_recommend_venues_enhanced)
    monkeypatch.setattr(
        app_module,
        "get_reference_similar_papers",
        lambda _text, top_k=5: [{"title": "Ref", "venue_name": "Venue"}],
    )
    monkeypatch.setattr(
        app_module,
        "extract_text_from_pdf",
        lambda _bytes: "This PDF contains enough extracted biomedical text for recommendations. " * 4,
    )

    resp = client.post(
        "/recommend",
        data={
            "paper_score": "7.0",
            "paper_topic": "biomedical",
            "file": (io.BytesIO(b"%PDF-1.4 mock"), "paper.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["reference_papers"][0]["venue_name"] == "Venue"


def test_recommend_invalid_payload_400(client):
    resp = client.post(
        "/recommend",
        data=json.dumps({"paper_text": "short", "paper_score": 5.0}),
        content_type="application/json",
    )
    assert resp.status_code in (400, 500)
    payload = resp.get_json()
    assert "error" in payload

