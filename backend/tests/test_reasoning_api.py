import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.models import ExtractionModelResponse, ExtractionRequest


class PassageAwareProvider:
    provider_name = "fake"
    model_name = "multi-source-fixture-v1"
    prompt_version = "claim-extractor.multi-source-fixture.v1"

    async def extract(self, request: ExtractionRequest) -> ExtractionModelResponse:
        passage = request.passages[0]
        surface = "AI security education"
        start = passage.text.index(surface)
        stance = "contradicts" if "observer.example" in request.canonical_url else "supports"
        output = {
            "entities": [
                {
                    "local_id": "topic_1",
                    "entity_type": "course",
                    "canonical_name": "AI Security Education",
                    "aliases": ["AI security education"],
                    "mentions": [
                        {
                            "passage_ordinal": 0,
                            "surface_text": passage.text[start : start + len(surface)],
                            "start_offset": start,
                            "end_offset": start + len(surface),
                            "confidence": 0.95,
                        }
                    ],
                }
            ],
            "claims": [
                {
                    "subject_local_id": "topic_1",
                    "predicate": "demand_trend",
                    "object_value": {"direction": "increasing"},
                    "qualifiers": {},
                    "normalized_text": "Demand for AI security education is increasing.",
                    "extraction_confidence": 0.9,
                    "evidence": [
                        {
                            "passage_ordinal": 0,
                            "stance": stance,
                            "directness": 0.9,
                            "extraction_confidence": 0.9,
                            "rationale": f"The passage {stance} the normalized claim.",
                        }
                    ],
                }
            ],
        }
        return ExtractionModelResponse(raw_output=json.dumps(output))


def seed_run(client: TestClient) -> str:
    project = client.post("/api/v1/projects", json={"name": "Multi-source reasoning"}).json()
    question = client.post(
        f"/api/v1/projects/{project['id']}/questions",
        json={"text": "Is demand for AI security education increasing?"},
    ).json()
    return client.post(f"/api/v1/questions/{question['id']}/runs", json={}).json()["id"]


def capture_and_extract(
    client: TestClient,
    run_id: str,
    *,
    url: str,
    publisher: str,
    content: str,
) -> str:
    capture = client.post(
        f"/api/v1/runs/{run_id}/sources",
        json={
            "url": url,
            "publisher": publisher,
            "source_type": "research",
            "raw_content": content,
        },
    )
    assert capture.status_code == 201
    document_id = capture.json()["document"]["id"]
    extraction = client.post(f"/api/v1/documents/{document_id}/extract")
    assert extraction.status_code == 200
    assert extraction.json()["status"] == "accepted"
    return document_id


def test_multi_source_support_and_contradiction_create_disputed_cluster(
    session_factory,
) -> None:
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=PassageAwareProvider(),
    )
    with TestClient(app) as client:
        run_id = seed_run(client)
        capture_and_extract(
            client,
            run_id,
            url="https://university.example/research/demand",
            publisher="University Research Centre",
            content="Demand for AI security education is increasing.",
        )
        capture_and_extract(
            client,
            run_id,
            url="https://institute.example/reports/demand",
            publisher="Skills Institute",
            content="A national survey reports increasing demand for AI security education.",
        )
        capture_and_extract(
            client,
            run_id,
            url="https://observer.example/analysis/demand",
            publisher="Education Observer",
            content="The survey found demand for AI security education is not increasing.",
        )

        response = client.post(f"/api/v1/runs/{run_id}/reason")

        assert response.status_code == 200
        clusters = response.json()["clusters"]
        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster["label"] == "disputed"
        assert cluster["support_strength"] > 0.9
        assert cluster["contradiction_strength"] > 0.8
        assert cluster["supporting_independent_sources"] == 2
        assert cluster["evidence_count"] == 3
        assert len(cluster["explanation"]["contributions"]) == 3
        metrics = client.get(f"/api/v1/runs/{run_id}").json()["metrics"]["reasoning"]
        assert metrics["scoring_version"] == "claim-confidence.v1"
        assert metrics["cluster_count"] == 1
        assert metrics["included_claim_count"] == 3
        assert metrics["evidence_link_count"] == 3

        conflicts = client.get(f"/api/v1/runs/{run_id}/conflicts").json()
        assert [item["cluster_id"] for item in conflicts] == [cluster["cluster_id"]]
        repeat = client.post(f"/api/v1/runs/{run_id}/reason").json()["clusters"]
        assert len(repeat) == 1
        assert repeat[0]["cluster_id"] == cluster["cluster_id"]


def test_exact_copy_across_domains_counts_as_one_independent_source(session_factory) -> None:
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=PassageAwareProvider(),
    )
    with TestClient(app) as client:
        run_id = seed_run(client)
        copied = "Demand for AI security education is increasing."
        capture_and_extract(
            client,
            run_id,
            url="https://source-one.example/report",
            publisher="Source One",
            content=copied,
        )
        capture_and_extract(
            client,
            run_id,
            url="https://source-two.example/reprint",
            publisher="Source Two",
            content=copied,
        )

        cluster = client.post(f"/api/v1/runs/{run_id}/reason").json()["clusters"][0]

        assert cluster["supporting_independent_sources"] == 1
        weights = sorted(
            item["independence_weight"] for item in cluster["explanation"]["contributions"]
        )
        assert weights == [0.25, 1.0]
        groups = {item["independence_group"] for item in cluster["explanation"]["contributions"]}
        assert len(groups) == 1
        assert next(iter(groups)).startswith("content:sha256:")


def test_rejected_claim_removes_stale_derived_cluster(session_factory) -> None:
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=PassageAwareProvider(),
    )
    with TestClient(app) as client:
        run_id = seed_run(client)
        capture_and_extract(
            client,
            run_id,
            url="https://source.example/report",
            publisher="Source",
            content="Demand for AI security education is increasing.",
        )
        initial = client.post(f"/api/v1/runs/{run_id}/reason").json()["clusters"]
        assert len(initial) == 1
        claim_id = client.get(f"/api/v1/runs/{run_id}/ueos").json()[0]["claim"]["id"]

        review = client.post(
            f"/api/v1/review/claims/{claim_id}",
            json={
                "action": "rejected",
                "reason": "Analyst found the extracted claim unsupported.",
            },
        )
        assert review.status_code == 200

        rerun = client.post(f"/api/v1/runs/{run_id}/reason")
        assert rerun.status_code == 200
        assert rerun.json()["clusters"] == []
        assert client.get(f"/api/v1/runs/{run_id}/clusters").json() == []
