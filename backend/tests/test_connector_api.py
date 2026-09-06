import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.models import ConnectorJob, ConnectorJobStatus
from app.domain.provenance import sha256_bytes, sha256_text
from app.domain.source_policy import SourceFetchPolicy
from app.main import create_app
from app.providers.http_source import BeforeRequest, SourceFetchResult
from app.services.web_connector import HostRateLimiter, PublicWebConnector
from app.workers.connector import ConnectorWorker


class SequenceFetcher:
    def __init__(self, results: Sequence[SourceFetchResult]) -> None:
        self.results = list(results)

    async def fetch(
        self, url: str, *, before_request: BeforeRequest | None = None
    ) -> SourceFetchResult:
        if before_request is not None:
            await before_request(SourceFetchPolicy().validate_target(url))
        return self.results.pop(0)


class ExplodingConnector:
    max_attempts = 3

    async def collect(self, url: str):
        del url
        raise RuntimeError("secret internal detail")


def fetched(url: str, content: bytes, media_type: str) -> SourceFetchResult:
    return SourceFetchResult(
        requested_url=url,
        final_url=url,
        status_code=200,
        media_type=media_type,
        content=content,
        content_hash=sha256_bytes(content),
        redirect_count=0,
    )


def connector_client(
    session_factory,
    results: Sequence[SourceFetchResult],
) -> TestClient:
    policy = SourceFetchPolicy()
    connector = PublicWebConnector(
        fetcher=SequenceFetcher(results),
        rate_limiter=HostRateLimiter(0),
        source_policy=policy,
        retry_base_seconds=0,
    )
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        web_connector=connector,
    )
    return TestClient(app)


def create_run(client: TestClient) -> str:
    project = client.post("/api/v1/projects", json={"name": "Connector API"}).json()
    question = client.post(
        f"/api/v1/projects/{project['id']}/questions",
        json={"text": "What does this public source report?"},
    ).json()
    response = client.post(f"/api/v1/questions/{question['id']}/runs", json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_connector_job_fetches_parses_and_persists_traceable_document(session_factory) -> None:
    source_url = "https://evidence.example/report"
    raw_response = (
        b"<html><head><title>Source title</title><style>hidden</style></head>"
        b"<body><h1>Public finding</h1><p>Demand increased in 2026.</p></body></html>"
    )
    with connector_client(
        session_factory,
        [
            fetched(
                "https://evidence.example/robots.txt",
                b"User-agent: *\nAllow: /",
                "text/plain",
            ),
            fetched(source_url, raw_response, "text/html"),
        ],
    ) as client:
        run_id = create_run(client)
        response = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json={
                "url": source_url,
                "publisher": "Evidence University",
                "source_type": "university",
            },
        )

        assert response.status_code == 202
        result = response.json()
        job = result["job"]
        assert result["capture"] is None
        assert result["idempotent"] is False
        assert job["status"] == "queued"
        assert job["claim_count"] == 0

        worker = ConnectorWorker(
            session_factory=session_factory,
            connector=client.app.state.web_connector,
            worker_id="test-worker",
            lease_seconds=60,
            poll_seconds=0.01,
        )
        assert asyncio.run(worker.run_once()) is True

        job = client.get(f"/api/v1/connector-jobs/{job['id']}").json()
        expected_text = "Public finding\n\nDemand increased in 2026."
        assert job["status"] == "succeeded"
        assert job["claim_count"] == 1
        assert job["attempts"] == 1
        assert job["robots_allowed"] is True
        assert job["response_hash"] == sha256_bytes(raw_response)
        document = client.get(f"/api/v1/documents/{job['document_id']}").json()
        passages = client.get(f"/api/v1/documents/{job['document_id']}/passages").json()
        assert document["title"] == "Source title"
        assert document["content_hash"] == sha256_text(expected_text)
        assert "\n\n".join(passage["exact_text"] for passage in passages) == expected_text

        persisted = client.get(f"/api/v1/connector-jobs/{job['id']}")
        assert persisted.status_code == 200
        assert persisted.json() == job
        listed = client.get(f"/api/v1/runs/{run_id}/connector-jobs")
        assert listed.json() == [job]
        assert client.get(f"/api/v1/runs/{run_id}").json()["state"] == "collecting"


def test_connector_job_persists_robots_block_without_document(session_factory) -> None:
    with connector_client(
        session_factory,
        [
            fetched(
                "https://evidence.example/robots.txt",
                b"User-agent: *\nDisallow: /private",
                "text/plain",
            )
        ],
    ) as client:
        run_id = create_run(client)
        response = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json={
                "url": "https://evidence.example/private/report",
                "publisher": "Evidence University",
            },
        )

        assert response.status_code == 202
        result = response.json()
        assert result["capture"] is None
        assert result["job"]["status"] == "queued"

        worker = ConnectorWorker(
            session_factory, client.app.state.web_connector, "test-worker", lease_seconds=60
        )
        assert asyncio.run(worker.run_once()) is True
        job = client.get(f"/api/v1/connector-jobs/{result['job']['id']}").json()
        assert job["status"] == "blocked"
        assert job["error_code"] == "robots_disallowed"
        assert job["attempts"] == 0
        assert job["document_id"] is None


def test_connector_job_requires_existing_run(session_factory) -> None:
    with connector_client(session_factory, []) as client:
        response = client.post(
            "/api/v1/runs/00000000-0000-0000-0000-000000000000/connector-jobs",
            json={"url": "https://evidence.example/report", "publisher": "Publisher"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RESOURCE_NOT_FOUND"


def test_connector_request_rejects_embedded_credentials_without_storing_job(
    session_factory,
) -> None:
    with connector_client(session_factory, []) as client:
        run_id = create_run(client)
        response = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json={
                "url": "https://user:secret@evidence.example/report",
                "publisher": "Publisher",
            },
        )

        assert response.status_code == 422
        assert client.get(f"/api/v1/runs/{run_id}/connector-jobs").json() == []


def test_connector_submission_is_idempotent_and_rejects_key_reuse(session_factory) -> None:
    with connector_client(session_factory, []) as client:
        run_id = create_run(client)
        payload = {"url": "https://evidence.example/report", "publisher": "Publisher"}
        first = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json=payload,
            headers={"Idempotency-Key": "stable-client-request"},
        )
        repeated = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json=payload,
            headers={"Idempotency-Key": "stable-client-request"},
        )
        conflict = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json={**payload, "publisher": "Another Publisher"},
            headers={"Idempotency-Key": "stable-client-request"},
        )

        assert first.status_code == 202
        assert repeated.status_code == 200
        assert repeated.json()["idempotent"] is True
        assert repeated.json()["job"]["id"] == first.json()["job"]["id"]
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert len(client.get(f"/api/v1/runs/{run_id}/connector-jobs").json()) == 1


def test_worker_reclaims_an_expired_job_lease(session_factory) -> None:
    source_url = "https://evidence.example/recovered"
    with connector_client(
        session_factory,
        [
            fetched(
                "https://evidence.example/robots.txt",
                b"User-agent: *\nAllow: /",
                "text/plain",
            ),
            fetched(source_url, b"Recovered evidence", "text/plain"),
        ],
    ) as client:
        run_id = create_run(client)
        queued = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json={"url": source_url, "publisher": "Publisher"},
        ).json()["job"]

        async def expire_lease() -> None:
            async with session_factory() as session:
                job = (
                    await session.execute(
                        select(ConnectorJob).where(ConnectorJob.id == UUID(queued["id"]))
                    )
                ).scalar_one()
                job.status = ConnectorJobStatus.RUNNING
                job.started_at = datetime.now(UTC) - timedelta(minutes=10)
                job.lease_owner = "dead-worker"
                job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                job.claim_count = 1
                await session.commit()

        asyncio.run(expire_lease())
        worker = ConnectorWorker(
            session_factory, client.app.state.web_connector, "recovery-worker", lease_seconds=60
        )
        assert asyncio.run(worker.run_once()) is True
        recovered = client.get(f"/api/v1/connector-jobs/{queued['id']}").json()
        assert recovered["status"] == "succeeded"
        assert recovered["claim_count"] == 2


def test_worker_records_a_sanitized_terminal_failure(session_factory) -> None:
    app = create_app(
        settings=Settings(app_env="test"),
        session_factory=session_factory,
        web_connector=ExplodingConnector(),  # type: ignore[arg-type]
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        run_id = create_run(client)
        queued = client.post(
            f"/api/v1/runs/{run_id}/connector-jobs",
            json={"url": "https://evidence.example/report", "publisher": "Publisher"},
        ).json()["job"]
        worker = ConnectorWorker(
            session_factory,
            client.app.state.web_connector,
            "failure-worker",
            lease_seconds=60,
        )

        assert asyncio.run(worker.run_once()) is True
        failed = client.get(f"/api/v1/connector-jobs/{queued['id']}").json()
        assert failed["status"] == "unavailable"
        assert failed["error_code"] == "worker_unhandled_error"
        assert failed["error_message"] == "Connector execution failed unexpectedly."
        assert "secret" not in failed["error_message"]
        assert failed["lease_expires_at"] is None
