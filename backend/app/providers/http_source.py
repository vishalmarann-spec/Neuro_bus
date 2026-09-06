import asyncio
import logging
import socket
import ssl
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpcore
import httpx

from app.domain.provenance import sha256_bytes
from app.domain.source_policy import (
    SourceFetchPolicy,
    SourcePolicyViolation,
    validate_public_address,
)

logger = logging.getLogger(__name__)

AddressResolver = Callable[[str, int], Awaitable[Sequence[str]]]


class SourceFetchUnavailable(RuntimeError):
    """A source fetch failed without exposing remote response content."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def resolve_host_addresses(host: str, port: int) -> tuple[str, ...]:
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as error:
        raise SourceFetchUnavailable(
            "dns_resolution_failed", "Source host could not be resolved."
        ) from error

    addresses = tuple(dict.fromkeys(record[4][0].split("%", maxsplit=1)[0] for record in records))
    if not addresses:
        raise SourceFetchUnavailable("dns_resolution_failed", "Source host could not be resolved.")
    return addresses


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve, validate, and connect to the same numeric public address."""

    def __init__(
        self,
        resolver: AddressResolver = resolve_host_addresses,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        if network_backend is None:
            from httpcore._backends.auto import AutoBackend

            network_backend = AutoBackend()
        self._network_backend = network_backend

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await self._resolver(host, port)
        validated = tuple(validate_public_address_text(address) for address in addresses)
        last_error: Exception | None = None
        for address in validated:
            try:
                return await self._network_backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise SourceFetchUnavailable("dns_resolution_failed", "Source host could not be resolved.")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix socket source fetches are disabled.")

    async def sleep(self, seconds: float) -> None:
        await self._network_backend.sleep(seconds)


def validate_public_address_text(value: str) -> str:
    import ipaddress

    try:
        address = ipaddress.ip_address(value.split("%", maxsplit=1)[0])
    except ValueError as error:
        raise SourceFetchUnavailable(
            "dns_resolution_failed", "Source host returned an invalid network address."
        ) from error
    return validate_public_address(address)


class _CoreResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: AsyncIterable[bytes]) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for part in self._stream:
            yield part

    async def aclose(self) -> None:
        close = getattr(self._stream, "aclose", None)
        if close is not None:
            await close()


class PinnedAsyncHTTPTransport(httpx.AsyncBaseTransport):
    """HTTPX transport with no proxy support and connect-time public-IP pinning."""

    def __init__(self, resolver: AddressResolver = resolve_host_addresses) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=PinnedNetworkBackend(resolver=resolver),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        response = await self._pool.handle_async_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


@dataclass(frozen=True, slots=True)
class SourceFetchResult:
    requested_url: str
    final_url: str
    status_code: int
    media_type: str
    content: bytes = field(repr=False)
    content_hash: str
    redirect_count: int


@dataclass(frozen=True, slots=True)
class SafeSourceFetcher:
    policy: SourceFetchPolicy = field(default_factory=SourceFetchPolicy)
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    user_agent: str = "Neuro_Bus/0.1 public-source-fetcher"

    async def fetch(self, url: str) -> SourceFetchResult:
        try:
            requested = self.policy.validate_target(url)
        except SourcePolicyViolation as error:
            logger.warning("source_fetch_blocked", extra={"error_code": error.code})
            raise
        transport = self.transport or PinnedAsyncHTTPTransport()
        timeout = httpx.Timeout(self.policy.timeout_seconds)
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                async with httpx.AsyncClient(
                    transport=transport,
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "Accept": ", ".join(sorted(self.policy.allowed_media_types)),
                        "User-Agent": self.user_agent,
                    },
                ) as client:
                    return await self._fetch_redirect_chain(client, requested.url)
        except SourcePolicyViolation as error:
            logger.warning(
                "source_fetch_blocked",
                extra={"host": requested.host, "error_code": error.code},
            )
            raise
        except SourceFetchUnavailable as error:
            logger.warning(
                "source_fetch_unavailable",
                extra={"host": requested.host, "error_code": error.code},
            )
            raise
        except TimeoutError as error:
            unavailable = SourceFetchUnavailable(
                "fetch_timeout", "Source fetch exceeded the configured duration."
            )
            logger.warning(
                "source_fetch_unavailable",
                extra={"host": requested.host, "error_code": unavailable.code},
            )
            raise unavailable from error
        except (httpx.TimeoutException, httpcore.TimeoutException) as error:
            unavailable = SourceFetchUnavailable(
                "fetch_timeout", "Source fetch exceeded the configured duration."
            )
            logger.warning(
                "source_fetch_unavailable",
                extra={"host": requested.host, "error_code": unavailable.code},
            )
            raise unavailable from error
        except (httpx.HTTPError, httpcore.NetworkError) as error:
            unavailable = SourceFetchUnavailable("network_error", "Source could not be fetched.")
            logger.warning(
                "source_fetch_unavailable",
                extra={"host": requested.host, "error_code": unavailable.code},
            )
            raise unavailable from error

    async def _fetch_redirect_chain(
        self, client: httpx.AsyncClient, requested_url: str
    ) -> SourceFetchResult:
        current = self.policy.validate_target(requested_url)
        visited = {current.url}
        for redirect_count in range(self.policy.max_redirects + 1):
            logger.info(
                "source_fetch_requested",
                extra={"host": current.host, "redirect_count": redirect_count},
            )
            async with client.stream("GET", current.url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if location is None:
                        raise SourceFetchUnavailable(
                            "invalid_redirect", "Source returned an invalid redirect."
                        )
                    if redirect_count >= self.policy.max_redirects:
                        raise SourceFetchUnavailable(
                            "too_many_redirects", "Source exceeded the redirect limit."
                        )
                    redirected = self.policy.validate_target(urljoin(current.url, location))
                    if current.scheme == "https" and redirected.scheme != "https":
                        raise SourcePolicyViolation(
                            "https_downgrade", "HTTPS source cannot redirect to HTTP."
                        )
                    if redirected.url in visited:
                        raise SourceFetchUnavailable(
                            "redirect_loop", "Source returned a redirect loop."
                        )
                    visited.add(redirected.url)
                    current = redirected
                    continue

                if not response.is_success:
                    raise SourceFetchUnavailable(
                        "http_error",
                        f"Source returned HTTP {response.status_code}.",
                    )
                media_type = self.policy.validate_media_type(response.headers.get("content-type"))
                self.policy.validate_content_length(response.headers.get("content-length"))
                content = await self._read_limited(response)
                logger.info(
                    "source_fetch_completed",
                    extra={
                        "host": current.host,
                        "status_code": response.status_code,
                        "media_type": media_type,
                        "response_bytes": len(content),
                        "redirect_count": redirect_count,
                    },
                )
                return SourceFetchResult(
                    requested_url=requested_url,
                    final_url=current.url,
                    status_code=response.status_code,
                    media_type=media_type,
                    content=content,
                    content_hash=sha256_bytes(content),
                    redirect_count=redirect_count,
                )
        raise AssertionError("redirect loop must return or raise")

    async def _read_limited(self, response: httpx.Response) -> bytes:
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > self.policy.max_response_bytes:
                raise SourcePolicyViolation(
                    "response_too_large", "Source response exceeds the configured byte limit."
                )
        return bytes(content)
