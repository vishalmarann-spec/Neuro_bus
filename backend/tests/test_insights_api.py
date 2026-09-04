import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.models import ExtractionModelResponse, ExtractionRequest


class ReportFixtureProvider:
    provider_name = "fake"
    model_name = "report-fixture-v1"

    async def extract(self, request: ExtractionRequest) -> ExtractionModelResponse:
        passage = request.passages[0]
        surface = "AI security education"
        start = passage.text.index(surface)
        stance = "contradicts" if "observer.example" in request.canonical_url else "supports"
        return ExtractionModelResponse(
            raw_output=json.dumps(
                {
                    "entities": [
                        {
                            "local_id": "topic_1",
                            "entity_type": "course",
                            "canonical_name": "AI Security Education",
                            "aliases": [],
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
                            "normalized_text": ("Demand for AI security education is increasing."),
                            "extraction_confidence": 0.9,
                            "evidence": [
                                {
                                    "passage_ordinal": 0,
                                    "stance": stance,
                                    "directness": 0.9,
                                    "extraction_confidence": 0.9,
                                    "rationale": "Synthetic report test evidence.",
                                }
                            ],
                        }
                    ],
                }
            )
        )


def seed_run(client: TestClient) -> str:
    project = client.post("/api/v1/projects", json={"name": "Cited insight test"}).json()
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
) -> None:
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
    extraction = client.post(f"/api/v1/documents/{capture.json()['document']['id']}/extract")
    assert extraction.status_code == 200


def test_insight_requires_scored_reasoning(client: TestClient) -> None:
    run_id = seed_run(client)

    response = client.post(f"/api/v1/runs/{run_id}/insights")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REASONING_REQUIRED"


def test_cited_report_is_traceable_disputed_and_idempotent(session_factory) -> None:
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        model_provider=ReportFixtureProvider(),
    )
    with TestClient(app) as client:
        run_id = seed_run(client)
        fixtures = [
            (
                "https://university.example/research/demand",
                "University Research Centre",
                "Demand for AI security education is increasing.",
            ),
            (
                "https://institute.example/reports/demand",
                "Skills Institute",
                "A survey reports increasing demand for AI security education.",
            ),
            (
                "https://observer.example/analysis/demand",
                "Education Observer",
                "The survey found demand for AI security education is not increasing.",
            ),
            (
                "https://employer.example/skills/demand",
                "Employer Council",
                "Employers report increasing demand for AI security education.",
            ),
            (
                "https://agency.example/data/demand",
                "Public Skills Agency",
                "New data indicates increasing demand for AI security education.",
            ),
        ]
        for url, publisher, content in fixtures:
            capture_and_extract(
                client,
                run_id,
                url=url,
                publisher=publisher,
                content=content,
            )
        assert client.post(f"/api/v1/runs/{run_id}/reason").status_code == 200

        created = client.post(f"/api/v1/runs/{run_id}/insights")

        assert created.status_code == 201
        insight = created.json()
        assert insight["idempotent"] is False
        assert insight["status"] == "needs_review"
        assert insight["generation_version"] == "cited-report.v1"
        assert insight["conclusion"] == ("Demand for AI security education is increasing.")

        report_response = client.get(f"/api/v1/insights/{insight['id']}/report")
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["insight"]["id"] == insight["id"]
        assert len(report["statements"]) == 1
        statement = report["statements"][0]
        assert statement["label"] == "disputed"
        assert statement["text"] == insight["conclusion"]
        assert {item["stance"] for item in statement["citations"]} == {
            "supports",
            "contradicts",
        }
        assert {item["canonical_url"] for item in statement["citations"]} == {
            item[0] for item in fixtures
        }
        assert {item["quote"] for item in statement["citations"]} == {item[2] for item in fixtures}
        assert len(statement["citations"]) == 5
        assert all(item["document_hash"].startswith("sha256:") for item in statement["citations"])
        assert all(item["evidence_link_id"] for item in statement["citations"])

        exported = client.get(f"/api/v1/insights/{insight['id']}/report.md")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/markdown")
        assert "attachment; filename=" in exported.headers["content-disposition"]
        assert "## Finding 1: Disputed" in exported.text
        assert insight["conclusion"] in exported.text
        assert all(url in exported.text for url, _, _ in fixtures)
        assert all(content in exported.text for _, _, content in fixtures)

        repeated = client.post(f"/api/v1/runs/{run_id}/insights")
        assert repeated.status_code == 200
        assert repeated.json()["idempotent"] is True
        assert repeated.json()["id"] == insight["id"]
        assert client.get(f"/api/v1/insights/{insight['id']}").status_code == 200

        claim_ids = {
            item["claim"]["id"] for item in client.get(f"/api/v1/runs/{run_id}/ueos").json()
        }
        for claim_id in claim_ids:
            review = client.post(
                f"/api/v1/review/claims/{claim_id}",
                json={
                    "action": "rejected",
                    "reason": "Synthetic lifecycle test rejection.",
                },
            )
            assert review.status_code == 200
        rescored = client.post(f"/api/v1/runs/{run_id}/reason")
        assert rescored.status_code == 200
        assert rescored.json()["clusters"] == []

        unavailable = client.post(f"/api/v1/runs/{run_id}/insights")
        assert unavailable.status_code == 409
        assert unavailable.json()["detail"]["code"] == "INSUFFICIENT_EVIDENCE"
        historical = client.get(f"/api/v1/insights/{insight['id']}/report")
        assert historical.status_code == 200
        assert historical.json()["statements"][0]["cluster_id"] is None
        assert len(historical.json()["statements"][0]["citations"]) == 5
