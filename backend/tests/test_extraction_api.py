import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.models import ExtractionRequest, FakeModelProvider

RAW_CONTENT = (
    "Example University launched an AI security programme in 2026.\n\n"
    "The programme includes machine learning security."
)


class FailingModelProvider:
    provider_name = "failing-test-provider"
    model_name = "failure-fixture-v1"

    async def extract(self, request: ExtractionRequest) -> str:
        raise RuntimeError("simulated provider failure")


def seed_document(client: TestClient) -> tuple[str, str]:
    project = client.post(
        "/api/v1/projects",
        json={"name": "AI Security Research", "vertical": "university"},
    ).json()
    question = client.post(
        f"/api/v1/projects/{project['id']}/questions",
        json={"text": "What AI security programmes are universities launching?"},
    ).json()
    run = client.post(f"/api/v1/questions/{question['id']}/runs", json={}).json()
    capture = client.post(
        f"/api/v1/runs/{run['id']}/sources",
        json={
            "url": "https://example.edu/programmes/ai-security",
            "publisher": "Example University",
            "source_type": "university",
            "title": "AI Security Programme",
            "raw_content": RAW_CONTENT,
            "published_at": "2026-08-10T00:00:00Z",
        },
    ).json()
    return run["id"], capture["document"]["id"]


def valid_extraction_output() -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "local_id": "university_1",
                    "entity_type": "university",
                    "canonical_name": "Example University",
                    "aliases": [],
                    "mentions": [
                        {
                            "passage_ordinal": 0,
                            "surface_text": "Example University",
                            "start_offset": 0,
                            "end_offset": 18,
                            "confidence": 0.99,
                        }
                    ],
                },
                {
                    "local_id": "skill_1",
                    "entity_type": "skill",
                    "canonical_name": "Machine Learning Security",
                    "aliases": ["ML security"],
                    "mentions": [
                        {
                            "passage_ordinal": 1,
                            "surface_text": "machine learning security",
                            "start_offset": 23,
                            "end_offset": 48,
                            "confidence": 0.96,
                        }
                    ],
                },
            ],
            "claims": [
                {
                    "subject_local_id": "university_1",
                    "predicate": "launched_programme",
                    "object_value": {"programme": "AI security"},
                    "qualifiers": {"year": 2026},
                    "normalized_text": (
                        "Example University launched an AI security programme in 2026."
                    ),
                    "extraction_confidence": 0.94,
                    "evidence": [
                        {
                            "passage_ordinal": 0,
                            "stance": "supports",
                            "directness": 0.98,
                            "extraction_confidence": 0.95,
                            "rationale": "The passage states the launch directly.",
                        }
                    ],
                }
            ],
        }
    )


def test_valid_extraction_creates_traceable_ueo_and_is_idempotent(session_factory) -> None:
    provider = FakeModelProvider(valid_extraction_output())
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=provider,
    )
    with TestClient(app) as client:
        run_id, document_id = seed_document(client)

        response = client.post(f"/api/v1/documents/{document_id}/extract")

        assert response.status_code == 200
        extraction = response.json()
        assert extraction["status"] == "accepted"
        assert extraction["entities_count"] == 2
        assert extraction["claims_count"] == 1
        assert extraction["evidence_links_count"] == 1
        assert extraction["idempotent"] is False

        ueos = client.get(f"/api/v1/runs/{run_id}/ueos").json()
        assert len(ueos) == 1
        assert ueos[0]["id"].startswith("ueo_")
        assert ueos[0]["claim"]["subject"]["canonical_name"] == "Example University"
        assert ueos[0]["evidence"]["quote"] == RAW_CONTENT.split("\n\n")[0]
        assert ueos[0]["evidence"]["stance"] == "supports"
        assert ueos[0]["provenance"]["url"] == ("https://example.edu/programmes/ai-security")
        assert ueos[0]["provenance"]["document_hash"].startswith("sha256:")
        assert ueos[0]["scores"]["source_trust"] is None
        assert ueos[0]["versions"]["extractor_version"] == "claim-extractor.v1"

        claim_id = ueos[0]["claim"]["id"]
        review = client.post(
            f"/api/v1/review/claims/{claim_id}",
            json={
                "action": "accepted",
                "reason": "The cited passage explicitly supports this claim.",
            },
        )
        assert review.status_code == 200
        assert review.json()["action"] == "accepted"
        assert (
            client.get(f"/api/v1/runs/{run_id}/ueos").json()[0]["claim"]["review_status"]
            == "accepted"
        )
        reviews = client.get(f"/api/v1/claims/{claim_id}/reviews").json()
        assert len(reviews) == 1
        assert reviews[0]["decision_id"] == review.json()["decision_id"]

        repeat = client.post(f"/api/v1/documents/{document_id}/extract").json()
        assert repeat["idempotent"] is True
        assert repeat["execution_id"] == extraction["execution_id"]
        assert provider.call_count == 1

        audit = client.get(f"/api/v1/model-executions/{extraction['execution_id']}").json()
        assert audit["validation_status"] == "accepted"
        assert audit["provider"] == "fake"
        assert audit["raw_output"] == provider.raw_output


def test_broken_mention_provenance_is_quarantined(session_factory) -> None:
    invalid = json.loads(valid_extraction_output())
    invalid["entities"][0]["mentions"][0]["start_offset"] = 1
    provider = FakeModelProvider(json.dumps(invalid))
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=provider,
    )
    with TestClient(app) as client:
        run_id, document_id = seed_document(client)

        response = client.post(f"/api/v1/documents/{document_id}/extract")

        assert response.status_code == 200
        extraction = response.json()
        assert extraction["status"] == "invalid"
        assert extraction["entities_count"] == 0
        assert extraction["claims_count"] == 0
        assert any("does not match" in error for error in extraction["validation_errors"])
        assert client.get(f"/api/v1/runs/{run_id}/ueos").json() == []

        audit = client.get(f"/api/v1/model-executions/{extraction['execution_id']}").json()
        assert audit["raw_output"] == provider.raw_output
        assert audit["validation_errors"] == extraction["validation_errors"]


def test_schema_invalid_output_is_quarantined(session_factory) -> None:
    provider = FakeModelProvider('{"entities": [], "claims": "not-a-list"}')
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=provider,
    )
    with TestClient(app) as client:
        run_id, document_id = seed_document(client)
        response = client.post(f"/api/v1/documents/{document_id}/extract")

        assert response.status_code == 200
        assert response.json()["status"] == "invalid"
        assert response.json()["validation_errors"]
        assert client.get(f"/api/v1/runs/{run_id}/ueos").json() == []


def test_disabled_provider_is_audited_and_returns_service_unavailable(session_factory) -> None:
    app = create_app(settings=Settings(app_env="test"), session_factory=session_factory)
    with TestClient(app) as client:
        _, document_id = seed_document(client)

        response = client.post(f"/api/v1/documents/{document_id}/extract")

        assert response.status_code == 503
        extraction = response.json()
        assert extraction["status"] == "unavailable"
        assert extraction["claims_count"] == 0
        audit = client.get(f"/api/v1/model-executions/{extraction['execution_id']}").json()
        assert audit["validation_status"] == "unavailable"
        assert audit["raw_output"] is None


def test_unexpected_provider_failure_is_audited_without_leaking_error_details(
    session_factory,
) -> None:
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=FailingModelProvider(),
    )
    with TestClient(app) as client:
        _, document_id = seed_document(client)

        response = client.post(f"/api/v1/documents/{document_id}/extract")

        assert response.status_code == 503
        errors = response.json()["validation_errors"]
        assert errors == ["Provider failed with RuntimeError."]
        assert "simulated provider failure" not in errors[0]
