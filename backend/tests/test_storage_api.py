from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.provenance import sha256_text
from app.main import create_app


def create_research_run(client: TestClient) -> tuple[str, str, str]:
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "University AI Security", "vertical": "university"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    question_response = client.post(
        f"/api/v1/projects/{project_id}/questions",
        json={
            "text": "Is demand for AI security education increasing?",
            "scope": {"region": "global"},
        },
    )
    assert question_response.status_code == 201
    question_id = question_response.json()["id"]

    run_response = client.post(f"/api/v1/questions/{question_id}/runs", json={})
    assert run_response.status_code == 201
    return project_id, question_id, run_response.json()["id"]


def test_complete_storage_vertical_slice_is_traceable_and_idempotent(client: TestClient) -> None:
    _, _, run_id = create_research_run(client)
    raw_content = (
        "The university launched a postgraduate AI security programme in 2026.\n\n"
        "The programme combines machine learning security and secure software engineering."
    )
    payload = {
        "url": "https://Example.EDU/programmes/ai-security/?utm_source=newsletter#overview",
        "publisher": "Example University",
        "source_type": "university",
        "title": "Postgraduate AI Security",
        "raw_content": raw_content,
        "published_at": "2026-08-10T00:00:00Z",
    }

    capture_response = client.post(f"/api/v1/runs/{run_id}/sources", json=payload)

    assert capture_response.status_code == 201
    capture = capture_response.json()
    document_id = capture["document"]["id"]
    assert capture["duplicate"] is False
    assert capture["source"]["canonical_domain"] == "example.edu"
    assert capture["document"]["canonical_url"] == ("https://example.edu/programmes/ai-security")
    assert capture["document"]["content_hash"] == sha256_text(raw_content)
    assert len(capture["passages"]) == 2

    passages_response = client.get(f"/api/v1/documents/{document_id}/passages")
    assert passages_response.status_code == 200
    for passage in passages_response.json():
        start, end = passage["start_offset"], passage["end_offset"]
        assert raw_content[start:end] == passage["exact_text"]
        assert sha256_text(passage["exact_text"]) == passage["text_hash"]

    duplicate_payload = {**payload, "url": "https://example.edu/programmes/ai-security"}
    duplicate_response = client.post(f"/api/v1/runs/{run_id}/sources", json=duplicate_payload)
    assert duplicate_response.status_code == 201
    assert duplicate_response.json()["duplicate"] is True
    assert duplicate_response.json()["document"]["id"] == document_id


def test_records_survive_a_new_api_application_instance(session_factory) -> None:
    settings = Settings(app_env="test")
    first_app = create_app(settings=settings, session_factory=session_factory)
    with TestClient(first_app) as first_client:
        project_id, question_id, run_id = create_research_run(first_client)

    second_app = create_app(settings=settings, session_factory=session_factory)
    with TestClient(second_app) as second_client:
        assert second_client.get(f"/api/v1/projects/{project_id}").status_code == 200
        assert second_client.get(f"/api/v1/questions/{question_id}").status_code == 200
        assert second_client.get(f"/api/v1/runs/{run_id}").status_code == 200
        assert second_client.get("/api/v1/health/ready").json()["status"] == "ready"


def test_missing_parent_returns_explicit_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/questions",
        json={"text": "Does this parent exist?"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RESOURCE_NOT_FOUND"
