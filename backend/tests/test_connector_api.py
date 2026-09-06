from collections.abc import Sequence

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.provenance import sha256_bytes, sha256_text
from app.domain.source_policy import SourceFetchPolicy
from app.main import create_app
from app.providers.http_source import BeforeRequest, SourceFetchResult
from app.services.web_connector import HostRateLimiter, PublicWebConnector


class SequenceFetcher:
    def __init__(self, results: Sequence[SourceFetchResult]) -> None:
        self.results = list(results)

    async def fetch(
        self, url: str, *, before_request: BeforeRequest | None = None
    ) -> SourceFetchResult:
        if before_request is not None:
            await before_request(SourceFetchPolicy().validate_target(url))
        return self.results.pop(0)


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

        assert response.status_code == 201
        result = response.json()
        job = result["job"]
        capture = result["capture"]
        expected_text = "Public finding\n\nDemand increased in 2026."
        assert job["status"] == "succeeded"
        assert job["attempts"] == 1
        assert job["robots_allowed"] is True
        assert job["response_hash"] == sha256_bytes(raw_response)
        assert job["document_id"] == capture["document"]["id"]
        assert capture["document"]["title"] == "Source title"
        assert capture["document"]["content_hash"] == sha256_text(expected_text)
        assert (
            "\n\n".join(passage["exact_text"] for passage in capture["passages"]) == expected_text
        )

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

        assert response.status_code == 201
        result = response.json()
        assert result["capture"] is None
        assert result["job"]["status"] == "blocked"
        assert result["job"]["error_code"] == "robots_disallowed"
        assert result["job"]["attempts"] == 0
        assert result["job"]["document_id"] is None


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
