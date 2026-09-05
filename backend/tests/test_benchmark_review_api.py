import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.evaluation.io import load_gold_cases
from app.evaluation.review import load_review_records
from app.main import create_app
from app.services.evaluation_review import BenchmarkReviewWorkspace

GOLD_ROOT = Path(__file__).parents[1] / "evaluation" / "gold"
PUBLIC_GOLD_PATHS = [
    GOLD_ROOT / "public_pilot_v1.json",
    GOLD_ROOT / "public_batch_2_v1.json",
    GOLD_ROOT / "public_batch_3_v1.json",
    GOLD_ROOT / "public_batch_4_v1.json",
]


def review_client(
    session_factory,
    *,
    gold_paths: list[Path],
    ledger_path: Path,
) -> TestClient:
    workspace = BenchmarkReviewWorkspace(
        gold_paths=gold_paths,
        ledger_path=ledger_path,
    )
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        benchmark_review_workspace=workspace,
    )
    return TestClient(app)


def complete_payload(case_fingerprint: str, *, decision: str = "approved") -> dict:
    return {
        "case_fingerprint": case_fingerprint,
        "reviewer": "Vishal Maran",
        "decision": decision,
        "checklist": {
            "source_url_opened": True,
            "excerpt_matches_source": True,
            "entities_and_claims_checked": True,
        },
        "notes": "Checked the official source, exact excerpt, labels, and evidence offsets.",
    }


def test_review_queue_and_append_only_decisions(session_factory, tmp_path: Path) -> None:
    ledger = tmp_path / "reviews.jsonl"
    with review_client(
        session_factory,
        gold_paths=PUBLIC_GOLD_PATHS,
        ledger_path=ledger,
    ) as client:
        queue_response = client.get("/api/v1/benchmark-reviews/cases")
        assert queue_response.status_code == 200
        queue = queue_response.json()
        assert queue["summary"] == {
            "total": 100,
            "pending": 100,
            "approved": 0,
            "changes_requested": 0,
            "rejected": 0,
            "stale": 0,
        }
        first = queue["cases"][0]
        case_id = first["case"]["case_id"]
        fingerprint = first["case_fingerprint"]
        assert first["case"]["document"]["source_url"].startswith("https://")
        assert client.get(f"/api/v1/benchmark-reviews/cases/{case_id}").status_code == 200
        unknown = client.get("/api/v1/benchmark-reviews/cases/not_a_real_case")
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "REVIEW_CASE_NOT_FOUND"

        incomplete = complete_payload(fingerprint)
        incomplete["checklist"]["entities_and_claims_checked"] = False
        assert (
            client.post(
                f"/api/v1/benchmark-reviews/cases/{case_id}/decisions",
                json=incomplete,
            ).status_code
            == 422
        )

        non_human = complete_payload(fingerprint)
        non_human["reviewer"] = "codex"
        assert (
            client.post(
                f"/api/v1/benchmark-reviews/cases/{case_id}/decisions",
                json=non_human,
            ).status_code
            == 422
        )

        approved_response = client.post(
            f"/api/v1/benchmark-reviews/cases/{case_id}/decisions",
            json=complete_payload(fingerprint),
        )
        assert approved_response.status_code == 201
        assert approved_response.json()["state"] == "approved"
        assert approved_response.json()["latest_review"]["reviewer"] == "Vishal Maran"

        rejected_response = client.post(
            f"/api/v1/benchmark-reviews/cases/{case_id}/decisions",
            json=complete_payload(fingerprint, decision="rejected"),
        )
        assert rejected_response.status_code == 201
        assert rejected_response.json()["state"] == "rejected"

        filtered = client.get("/api/v1/benchmark-reviews/cases?state=rejected")
        assert filtered.status_code == 200
        assert len(filtered.json()["cases"]) == 1
        assert filtered.json()["summary"]["rejected"] == 1

    records = load_review_records(ledger)
    assert len(records) == 2
    assert [record.decision for record in records] == ["approved", "rejected"]


def test_stale_browser_fingerprint_cannot_submit(session_factory, tmp_path: Path) -> None:
    source_case = load_gold_cases(PUBLIC_GOLD_PATHS[0])[0]
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(
        json.dumps([source_case.model_dump(mode="json")], indent=2) + "\n",
        encoding="utf-8",
    )
    ledger = tmp_path / "reviews.jsonl"
    with review_client(
        session_factory,
        gold_paths=[gold_path],
        ledger_path=ledger,
    ) as client:
        loaded = client.get("/api/v1/benchmark-reviews/cases").json()["cases"][0]
        payload = source_case.model_dump(mode="json")
        payload["difficulty"] = "adversarial"
        gold_path.write_text(json.dumps([payload], indent=2) + "\n", encoding="utf-8")

        response = client.post(
            f"/api/v1/benchmark-reviews/cases/{source_case.case_id}/decisions",
            json=complete_payload(loaded["case_fingerprint"]),
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVIEW_CASE_STALE"
    assert not ledger.exists()


def test_review_workspace_is_disabled_outside_local_development(client: TestClient) -> None:
    response = client.get("/api/v1/benchmark-reviews/cases")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REVIEW_WORKSPACE_DISABLED"


def test_invalid_review_ledger_fails_explicitly(session_factory, tmp_path: Path) -> None:
    ledger = tmp_path / "reviews.jsonl"
    ledger.write_text("{not-valid-json}\n", encoding="utf-8")
    with review_client(
        session_factory,
        gold_paths=PUBLIC_GOLD_PATHS,
        ledger_path=ledger,
    ) as client:
        response = client.get("/api/v1/benchmark-reviews/cases")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REVIEW_WORKSPACE_DATA_INVALID"
