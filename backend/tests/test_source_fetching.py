import asyncio
from typing import Any

import httpcore
import httpx
import pytest

from app.domain.source_policy import SourceFetchPolicy, SourcePolicyViolation
from app.providers.http_source import (
    PinnedNetworkBackend,
    SafeSourceFetcher,
    SourceFetchUnavailable,
)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("file:///etc/passwd", "invalid_url"),
        ("https://example.com/path\x00suffix", "invalid_url"),
        ("http://user:secret@example.com/", "embedded_credentials"),
        ("http://localhost/admin", "private_network_target"),
        ("http://service.internal/status", "private_network_target"),
        ("http://127.0.0.1/admin", "private_network_target"),
        ("http://169.254.169.254/latest/meta-data", "private_network_target"),
        ("http://[::1]/", "private_network_target"),
        ("http://[::ffff:127.0.0.1]/", "private_network_target"),
        ("https://example.com:8443/", "disallowed_port"),
    ],
)
def test_source_policy_rejects_unsafe_targets(url: str, code: str) -> None:
    with pytest.raises(SourcePolicyViolation) as captured:
        SourceFetchPolicy().validate_target(url)

    assert captured.value.code == code


def test_source_policy_normalizes_public_target_without_changing_query() -> None:
    target = SourceFetchPolicy().validate_target(
        " HTTPS://Example.COM./research?q=neuro+bus#section "
    )

    assert target.url == "https://example.com/research?q=neuro+bus"
    assert target.host == "example.com"
    assert target.port == 443


class FakeNetworkStream(httpcore.AsyncNetworkStream):
    pass


class RecordingNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connected_hosts: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected_hosts.append(host)
        return FakeNetworkStream()

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("Unix sockets must not be used")

    async def sleep(self, seconds: float) -> None:
        return None


@pytest.mark.asyncio
async def test_pinned_network_backend_connects_to_validated_numeric_address() -> None:
    connected = RecordingNetworkBackend()

    async def resolver(host: str, port: int) -> tuple[str, ...]:
        assert (host, port) == ("public.example", 443)
        return ("93.184.216.34",)

    backend = PinnedNetworkBackend(resolver=resolver, network_backend=connected)
    await backend.connect_tcp("public.example", 443)

    assert connected.connected_hosts == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_pinned_network_backend_rejects_mixed_public_private_dns_answer() -> None:
    connected = RecordingNetworkBackend()

    async def resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34", "10.0.0.8")

    backend = PinnedNetworkBackend(resolver=resolver, network_backend=connected)
    with pytest.raises(SourcePolicyViolation) as captured:
        await backend.connect_tcp("rebinding.example", 443)

    assert captured.value.code == "private_network_target"
    assert connected.connected_hosts == []


@pytest.mark.asyncio
async def test_fetcher_validates_redirects_and_returns_bounded_content() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<main>Evidence</main>",
        )

    result = await SafeSourceFetcher(transport=httpx.MockTransport(handler)).fetch(
        "https://evidence.example/start"
    )

    assert seen_urls == [
        "https://evidence.example/start",
        "https://evidence.example/final",
    ]
    assert result.final_url == "https://evidence.example/final"
    assert result.media_type == "text/html"
    assert result.content == b"<main>Evidence</main>"
    assert result.redirect_count == 1
    assert result.content_hash.startswith("sha256:")


@pytest.mark.asyncio
async def test_fetcher_blocks_private_redirect_before_second_request() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with pytest.raises(SourcePolicyViolation) as captured:
        await SafeSourceFetcher(transport=httpx.MockTransport(handler)).fetch(
            "https://evidence.example/start"
        )

    assert captured.value.code == "private_network_target"
    assert request_count == 1


@pytest.mark.asyncio
async def test_fetcher_blocks_https_downgrade() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://public.example/final"})

    with pytest.raises(SourcePolicyViolation) as captured:
        await SafeSourceFetcher(transport=httpx.MockTransport(handler)).fetch(
            "https://evidence.example/start"
        )

    assert captured.value.code == "https_downgrade"


@pytest.mark.asyncio
async def test_fetcher_rejects_executable_content_type() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/javascript"},
            content=b"alert(1)",
        )
    )

    with pytest.raises(SourcePolicyViolation) as captured:
        await SafeSourceFetcher(transport=transport).fetch("https://evidence.example/script")

    assert captured.value.code == "disallowed_content_type"


@pytest.mark.asyncio
async def test_fetcher_stops_stream_after_decoded_byte_limit() -> None:
    policy = SourceFetchPolicy(max_response_bytes=5)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"123456",
        )
    )

    with pytest.raises(SourcePolicyViolation) as captured:
        await SafeSourceFetcher(policy=policy, transport=transport).fetch(
            "https://evidence.example/large"
        )

    assert captured.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_fetcher_rejects_oversized_declared_length_before_reading() -> None:
    policy = SourceFetchPolicy(max_response_bytes=5)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "6"},
            content=b"123456",
        )
    )

    with pytest.raises(SourcePolicyViolation) as captured:
        await SafeSourceFetcher(policy=policy, transport=transport).fetch(
            "https://evidence.example/large"
        )

    assert captured.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_fetcher_enforces_total_duration_and_sanitizes_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    fetcher = SafeSourceFetcher(
        policy=SourceFetchPolicy(timeout_seconds=0.01),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(SourceFetchUnavailable) as captured:
        await fetcher.fetch("https://evidence.example/slow?secret=value")

    assert captured.value.code == "fetch_timeout"
    assert "secret" not in str(captured.value)


@pytest.mark.asyncio
async def test_fetcher_sanitizes_transport_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpcore.ReadTimeout("remote detail must not escape")

    with pytest.raises(SourceFetchUnavailable) as captured:
        await SafeSourceFetcher(transport=httpx.MockTransport(handler)).fetch(
            "https://evidence.example/slow"
        )

    assert captured.value.code == "fetch_timeout"
    assert str(captured.value) == "Source fetch exceeded the configured duration."
