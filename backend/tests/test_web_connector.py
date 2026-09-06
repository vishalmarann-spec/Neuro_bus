import time
from collections.abc import Sequence

import pytest

from app.core.models import ConnectorJobStatus
from app.domain.provenance import sha256_bytes
from app.domain.source_policy import SourceFetchPolicy
from app.providers.http_source import BeforeRequest, SourceFetchResult, SourceFetchUnavailable
from app.services.pdf_parser import PDFParseFailure, PDFParser, PDFParseResult
from app.services.web_connector import HostRateLimiter, PublicWebConnector, SourceFetcher


def fetched(
    url: str,
    content: bytes,
    media_type: str = "text/plain",
    redirect_count: int = 0,
) -> SourceFetchResult:
    return SourceFetchResult(
        requested_url=url,
        final_url=url,
        status_code=200,
        media_type=media_type,
        content=content,
        content_hash=sha256_bytes(content),
        redirect_count=redirect_count,
    )


class SequenceFetcher:
    def __init__(self, results: Sequence[SourceFetchResult | Exception]) -> None:
        self.results = list(results)
        self.urls: list[str] = []

    async def fetch(
        self, url: str, *, before_request: BeforeRequest | None = None
    ) -> SourceFetchResult:
        self.urls.append(url)
        if before_request is not None:
            await before_request(SourceFetchPolicy().validate_target(url))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class RedirectAttemptFetcher:
    def __init__(self, robots_text: bytes, redirected_url: str) -> None:
        self.robots_text = robots_text
        self.redirected_url = redirected_url
        self.policy = SourceFetchPolicy()
        self.urls: list[str] = []

    async def fetch(
        self, url: str, *, before_request: BeforeRequest | None = None
    ) -> SourceFetchResult:
        self.urls.append(url)
        assert before_request is not None
        await before_request(self.policy.validate_target(url))
        if url.endswith("/robots.txt"):
            return fetched(url, self.robots_text)
        await before_request(self.policy.validate_target(self.redirected_url))
        raise AssertionError("redirect destination must be blocked before its request")


def connector(
    fetcher: SourceFetcher,
    *,
    limiter: HostRateLimiter | None = None,
    max_attempts: int = 3,
    retry_base_seconds: float = 0,
    pdf_parser: PDFParser | None = None,
    pdf_parse_timeout_seconds: float = 10.0,
) -> PublicWebConnector:
    return PublicWebConnector(
        fetcher=fetcher,
        rate_limiter=limiter or HostRateLimiter(0),
        source_policy=SourceFetchPolicy(),
        max_attempts=max_attempts,
        retry_base_seconds=retry_base_seconds,
        pdf_parser=pdf_parser,
        pdf_parse_timeout_seconds=pdf_parse_timeout_seconds,
    )


class SuccessfulPDFParser:
    parser_version = "test.pdf.v1"

    def parse(self, content: bytes) -> PDFParseResult:
        assert content == b"%PDF-test"
        return PDFParseResult(
            text="Page one evidence.\n\nPage two evidence.",
            title="PDF evidence",
            page_count=2,
            extracted_page_count=2,
            parser_version=self.parser_version,
        )


class EmptyPDFParser:
    parser_version = "test.pdf.v1"

    def parse(self, content: bytes) -> PDFParseResult:
        del content
        raise PDFParseFailure(
            "pdf_no_extractable_text",
            "PDF contains no extractable text; OCR is not enabled.",
            page_count=3,
            extracted_page_count=0,
        )


class SlowPDFParser:
    parser_version = "test.pdf.v1"

    def parse(self, content: bytes) -> PDFParseResult:
        del content
        time.sleep(0.05)
        return PDFParseResult(
            text="late text",
            title=None,
            page_count=1,
            extracted_page_count=1,
            parser_version=self.parser_version,
        )


@pytest.mark.asyncio
async def test_robots_disallow_blocks_source_request() -> None:
    fetcher = SequenceFetcher(
        [
            fetched(
                "https://evidence.example/robots.txt",
                b"User-agent: *\nDisallow: /private",
            )
        ]
    )

    outcome = await connector(fetcher).collect("https://evidence.example/private/report")

    assert outcome.status == ConnectorJobStatus.BLOCKED
    assert outcome.error_code == "robots_disallowed"
    assert outcome.robots_allowed is False
    assert outcome.attempts == 0
    assert fetcher.urls == ["https://evidence.example/robots.txt"]


@pytest.mark.asyncio
async def test_missing_robots_file_allows_source_and_strips_executable_markup() -> None:
    source_url = "https://evidence.example/report"
    body = (
        b"<html><head><title> Verified Report </title><script>ignore()</script></head>"
        b"<body><h1>Finding</h1><p>Exact evidence.</p></body></html>"
    )
    fetcher = SequenceFetcher(
        [
            SourceFetchUnavailable("http_error", "Source returned HTTP 404.", status_code=404),
            fetched(source_url, body, "text/html"),
        ]
    )

    outcome = await connector(fetcher).collect(source_url)

    assert outcome.status == ConnectorJobStatus.SUCCEEDED
    assert outcome.robots_allowed is True
    assert outcome.attempts == 1
    assert outcome.title == "Verified Report"
    assert outcome.text == "Finding\n\nExact evidence."
    assert "ignore" not in outcome.text
    assert outcome.response_hash == sha256_bytes(body)


@pytest.mark.asyncio
async def test_unverified_robots_policy_fails_closed() -> None:
    fetcher = SequenceFetcher(
        [SourceFetchUnavailable("network_error", "Source could not be fetched.")]
    )

    outcome = await connector(fetcher).collect("https://evidence.example/report")

    assert outcome.status == ConnectorJobStatus.UNAVAILABLE
    assert outcome.error_code == "robots_unavailable"
    assert outcome.robots_allowed is None
    assert outcome.attempts == 0
    assert len(fetcher.urls) == 1


@pytest.mark.asyncio
async def test_transient_source_failures_retry_with_capped_attempts() -> None:
    source_url = "https://evidence.example/report"
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    fetcher = SequenceFetcher(
        [
            fetched("https://evidence.example/robots.txt", b"User-agent: *\nAllow: /"),
            SourceFetchUnavailable("http_error", "Source returned HTTP 503.", status_code=503),
            SourceFetchUnavailable("network_error", "Source could not be fetched."),
            fetched(source_url, b"Recovered evidence."),
        ]
    )
    web_connector = PublicWebConnector(
        fetcher=fetcher,
        rate_limiter=HostRateLimiter(0),
        source_policy=SourceFetchPolicy(),
        max_attempts=3,
        retry_base_seconds=0.5,
        sleep=record_sleep,
    )

    outcome = await web_connector.collect(source_url)

    assert outcome.status == ConnectorJobStatus.SUCCEEDED
    assert outcome.attempts == 3
    assert delays == [0.5, 1.0]
    assert len(fetcher.urls) == 4


@pytest.mark.asyncio
async def test_non_retryable_source_failure_stops_after_one_attempt() -> None:
    fetcher = SequenceFetcher(
        [
            fetched("https://evidence.example/robots.txt", b"User-agent: *\nAllow: /"),
            SourceFetchUnavailable("http_error", "Source returned HTTP 404.", status_code=404),
        ]
    )

    outcome = await connector(fetcher).collect("https://evidence.example/missing")

    assert outcome.status == ConnectorJobStatus.UNAVAILABLE
    assert outcome.error_code == "http_error"
    assert outcome.attempts == 1
    assert len(fetcher.urls) == 2


@pytest.mark.asyncio
async def test_robots_crawl_delay_controls_same_host_request_spacing() -> None:
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    async def advance(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now += delay

    source_url = "https://evidence.example/report"
    limiter = HostRateLimiter(1.0, clock=clock, sleep=advance)
    fetcher = SequenceFetcher(
        [
            fetched(
                "https://evidence.example/robots.txt",
                b"User-agent: *\nAllow: /\nCrawl-delay: 2",
            ),
            fetched(source_url, b"Evidence."),
        ]
    )

    outcome = await connector(fetcher, limiter=limiter).collect(source_url)

    assert outcome.status == ConnectorJobStatus.SUCCEEDED
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_pdf_response_records_parser_unavailable_without_fake_text() -> None:
    source_url = "https://evidence.example/report.pdf"
    fetcher = SequenceFetcher(
        [
            fetched("https://evidence.example/robots.txt", b"User-agent: *\nAllow: /"),
            fetched(source_url, b"%PDF-1.7", "application/pdf"),
        ]
    )

    outcome = await connector(fetcher).collect(source_url)

    assert outcome.status == ConnectorJobStatus.UNAVAILABLE
    assert outcome.error_code == "parser_unavailable"
    assert outcome.text is None
    assert outcome.response_hash == sha256_bytes(b"%PDF-1.7")


@pytest.mark.asyncio
async def test_pdf_response_uses_configured_parser_and_preserves_audit_metadata() -> None:
    source_url = "https://evidence.example/report.pdf"
    body = b"%PDF-test"
    fetcher = SequenceFetcher(
        [
            fetched("https://evidence.example/robots.txt", b"User-agent: *\nAllow: /"),
            fetched(source_url, body, "application/pdf"),
        ]
    )

    outcome = await connector(fetcher, pdf_parser=SuccessfulPDFParser()).collect(source_url)

    assert outcome.status == ConnectorJobStatus.SUCCEEDED
    assert outcome.text == "Page one evidence.\n\nPage two evidence."
    assert outcome.title == "PDF evidence"
    assert outcome.parser_version == "test.pdf.v1"
    assert outcome.source_page_count == 2
    assert outcome.extracted_page_count == 2
    assert outcome.response_hash == sha256_bytes(body)


@pytest.mark.asyncio
async def test_pdf_failure_keeps_page_counts_and_never_returns_text() -> None:
    source_url = "https://evidence.example/scanned.pdf"
    fetcher = SequenceFetcher(
        [
            fetched("https://evidence.example/robots.txt", b"User-agent: *\nAllow: /"),
            fetched(source_url, b"%PDF-scanned", "application/pdf"),
        ]
    )

    outcome = await connector(fetcher, pdf_parser=EmptyPDFParser()).collect(source_url)

    assert outcome.status == ConnectorJobStatus.UNAVAILABLE
    assert outcome.error_code == "pdf_no_extractable_text"
    assert outcome.text is None
    assert outcome.parser_version == "test.pdf.v1"
    assert outcome.source_page_count == 3
    assert outcome.extracted_page_count == 0


@pytest.mark.asyncio
async def test_pdf_parser_timeout_is_explicit_and_does_not_return_late_text() -> None:
    source_url = "https://evidence.example/slow.pdf"
    fetcher = SequenceFetcher(
        [
            fetched("https://evidence.example/robots.txt", b"User-agent: *\nAllow: /"),
            fetched(source_url, b"%PDF-slow", "application/pdf"),
        ]
    )

    outcome = await connector(
        fetcher,
        pdf_parser=SlowPDFParser(),
        pdf_parse_timeout_seconds=0.001,
    ).collect(source_url)

    assert outcome.status == ConnectorJobStatus.UNAVAILABLE
    assert outcome.error_code == "pdf_parse_timeout"
    assert outcome.text is None


@pytest.mark.asyncio
async def test_cross_origin_redirect_is_blocked_before_destination_request() -> None:
    fetcher = RedirectAttemptFetcher(
        b"User-agent: *\nAllow: /",
        "https://other.example/final",
    )

    outcome = await connector(fetcher).collect("https://evidence.example/start")

    assert outcome.status == ConnectorJobStatus.BLOCKED
    assert outcome.error_code == "cross_origin_redirect"
    assert outcome.attempts == 1


@pytest.mark.asyncio
async def test_same_origin_redirect_path_is_rechecked_against_robots() -> None:
    fetcher = RedirectAttemptFetcher(
        b"User-agent: *\nAllow: /start\nDisallow: /private",
        "https://evidence.example/private/final",
    )

    outcome = await connector(fetcher).collect("https://evidence.example/start")

    assert outcome.status == ConnectorJobStatus.BLOCKED
    assert outcome.error_code == "robots_disallowed_redirect"
    assert outcome.attempts == 1
