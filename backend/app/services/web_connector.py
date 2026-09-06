import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol
from urllib import robotparser
from urllib.parse import urlsplit, urlunsplit

from app.core.models import ConnectorJobStatus
from app.domain.source_policy import (
    SourceFetchPolicy,
    SourcePolicyViolation,
    ValidatedSourceTarget,
)
from app.providers.http_source import BeforeRequest, SourceFetchResult, SourceFetchUnavailable
from app.services.pdf_parser import PDFParseFailure, PDFParser

logger = logging.getLogger(__name__)

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
MARKUP_MEDIA_TYPES = frozenset(
    {"application/xhtml+xml", "application/xml", "text/html", "text/xml"}
)


class SourceFetcher(Protocol):
    async def fetch(
        self, url: str, *, before_request: BeforeRequest | None = None
    ) -> SourceFetchResult: ...


class HostRateLimiter:
    """Process-local per-host spacing with concurrency-safe reservations."""

    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("Host request interval cannot be negative.")
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    async def wait(self, host: str, interval_seconds: float | None = None) -> None:
        interval = self.min_interval_seconds if interval_seconds is None else interval_seconds
        if interval < 0:
            raise ValueError("Host request interval cannot be negative.")
        normalized_host = host.casefold()
        lock = self._locks.setdefault(normalized_host, asyncio.Lock())
        async with lock:
            last_request = self._last_request_at.get(normalized_host)
            delay = (
                0.0 if last_request is None else max(0.0, last_request + interval - self._clock())
            )
            if delay:
                await self._sleep(delay)
            self._last_request_at[normalized_host] = self._clock()


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    robots_url: str
    allowed: bool | None
    crawl_delay_seconds: float = 0.0
    error_code: str | None = None
    error_message: str | None = None
    rules: robotparser.RobotFileParser | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class WebConnectorOutcome:
    status: ConnectorJobStatus
    requested_url: str
    attempts: int
    robots_url: str | None = None
    robots_allowed: bool | None = None
    final_url: str | None = None
    media_type: str | None = None
    response_hash: str | None = None
    response_bytes: int | None = None
    redirect_count: int | None = None
    parser_version: str | None = None
    source_page_count: int | None = None
    extracted_page_count: int | None = None
    title: str | None = None
    text: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedSourceContent:
    text: str | None = None
    title: str | None = None
    parser_version: str | None = None
    source_page_count: int | None = None
    extracted_page_count: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class _MarkupTextParser(HTMLParser):
    skipped_tags = frozenset({"noscript", "script", "style", "svg", "template"})
    block_tags = frozenset(
        {
            "article",
            "aside",
            "blockquote",
            "br",
            "dd",
            "div",
            "dl",
            "dt",
            "figcaption",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "nav",
            "ol",
            "p",
            "pre",
            "section",
            "table",
            "td",
            "th",
            "tr",
            "ul",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skipped_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.casefold()
        if normalized in self.skipped_tags:
            self._skipped_depth += 1
            return
        if self._skipped_depth:
            return
        if normalized == "title":
            self._in_title = True
        if normalized in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self.skipped_tags and self._skipped_depth:
            self._skipped_depth -= 1
            return
        if self._skipped_depth:
            return
        if normalized == "title":
            self._in_title = False
        if normalized in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skipped_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        self.parts.append(data)

    def parsed(self) -> tuple[str, str | None]:
        raw_text = "".join(self.parts)
        normalized_lines = [" ".join(line.split()) for line in raw_text.splitlines()]
        paragraphs = [line for line in normalized_lines if line]
        text = "\n\n".join(paragraphs).strip()
        title = " ".join("".join(self.title_parts).split()).strip() or None
        return text, title


@dataclass(frozen=True, slots=True)
class PublicWebConnector:
    fetcher: SourceFetcher
    rate_limiter: HostRateLimiter
    source_policy: SourceFetchPolicy
    user_agent: str = "Neuro_Bus"
    max_attempts: int = 3
    retry_base_seconds: float = 0.5
    max_crawl_delay_seconds: float = 10.0
    pdf_parser: PDFParser | None = None
    pdf_parse_timeout_seconds: float = 10.0
    sleep: Sleeper = asyncio.sleep

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 5:
            raise ValueError("Web connector attempts must be between 1 and 5.")
        if self.retry_base_seconds < 0:
            raise ValueError("Web connector retry delay cannot be negative.")
        if self.max_crawl_delay_seconds < 0:
            raise ValueError("Maximum robots crawl delay cannot be negative.")
        if self.pdf_parse_timeout_seconds <= 0:
            raise ValueError("PDF parse timeout must be positive.")

    async def collect(self, url: str) -> WebConnectorOutcome:
        try:
            target = self.source_policy.validate_target(url)
        except SourcePolicyViolation as error:
            return self._blocked(url, 0, None, error.code, str(error))

        robots = await self._check_robots(target.url)
        if robots.allowed is not True:
            status = (
                ConnectorJobStatus.BLOCKED
                if robots.allowed is False
                else ConnectorJobStatus.UNAVAILABLE
            )
            return WebConnectorOutcome(
                status=status,
                requested_url=target.url,
                attempts=0,
                robots_url=robots.robots_url,
                robots_allowed=robots.allowed,
                error_code=robots.error_code,
                error_message=robots.error_message,
            )

        interval = max(self.rate_limiter.min_interval_seconds, robots.crawl_delay_seconds)
        requested_origin = (target.scheme, target.host, target.port)

        async def before_request(request_target: ValidatedSourceTarget) -> None:
            redirect_origin = (
                request_target.scheme,
                request_target.host,
                request_target.port,
            )
            if redirect_origin != requested_origin:
                raise SourcePolicyViolation(
                    "cross_origin_redirect",
                    "Public web connector does not follow redirects to another origin.",
                )
            if robots.rules is not None and not robots.rules.can_fetch(
                self.user_agent, request_target.url
            ):
                raise SourcePolicyViolation(
                    "robots_disallowed_redirect",
                    "Source robots policy disallows the redirected path.",
                )
            await self.rate_limiter.wait(request_target.host, interval)

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self.fetcher.fetch(
                    target.url,
                    before_request=before_request,
                )
            except SourcePolicyViolation as error:
                return self._blocked(target.url, attempt, robots, error.code, str(error))
            except SourceFetchUnavailable as error:
                if attempt < self.max_attempts and self._is_retryable(error):
                    delay = self.retry_base_seconds * (2 ** (attempt - 1))
                    logger.info(
                        "web_connector_retry_scheduled",
                        extra={"host": target.host, "attempt": attempt, "delay_seconds": delay},
                    )
                    await self.sleep(delay)
                    continue
                return WebConnectorOutcome(
                    status=ConnectorJobStatus.UNAVAILABLE,
                    requested_url=target.url,
                    attempts=attempt,
                    robots_url=robots.robots_url,
                    robots_allowed=True,
                    error_code=error.code,
                    error_message=str(error),
                )

            parsed = await self._extract_content(response)
            if parsed.error_code is not None:
                return WebConnectorOutcome(
                    status=ConnectorJobStatus.UNAVAILABLE,
                    requested_url=target.url,
                    attempts=attempt,
                    robots_url=robots.robots_url,
                    robots_allowed=True,
                    final_url=response.final_url,
                    media_type=response.media_type,
                    response_hash=response.content_hash,
                    response_bytes=len(response.content),
                    redirect_count=response.redirect_count,
                    parser_version=parsed.parser_version,
                    source_page_count=parsed.source_page_count,
                    extracted_page_count=parsed.extracted_page_count,
                    error_code=parsed.error_code,
                    error_message=parsed.error_message,
                )
            assert parsed.text is not None
            return WebConnectorOutcome(
                status=ConnectorJobStatus.SUCCEEDED,
                requested_url=target.url,
                attempts=attempt,
                robots_url=robots.robots_url,
                robots_allowed=True,
                final_url=response.final_url,
                media_type=response.media_type,
                response_hash=response.content_hash,
                response_bytes=len(response.content),
                redirect_count=response.redirect_count,
                parser_version=parsed.parser_version,
                source_page_count=parsed.source_page_count,
                extracted_page_count=parsed.extracted_page_count,
                title=parsed.title,
                text=parsed.text,
            )

        raise AssertionError("attempt loop must return")

    async def _check_robots(self, target_url: str) -> RobotsDecision:
        parsed = urlsplit(target_url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))

        async def before_request(request_target: ValidatedSourceTarget) -> None:
            await self.rate_limiter.wait(request_target.host)

        try:
            response = await self.fetcher.fetch(robots_url, before_request=before_request)
        except SourcePolicyViolation as error:
            return RobotsDecision(
                robots_url=robots_url,
                allowed=None,
                error_code=error.code,
                error_message=str(error),
            )
        except SourceFetchUnavailable as error:
            if error.code == "http_error" and error.status_code in {404, 410}:
                return RobotsDecision(robots_url=robots_url, allowed=True)
            if error.code == "http_error" and error.status_code in {401, 403}:
                return RobotsDecision(
                    robots_url=robots_url,
                    allowed=False,
                    error_code="robots_access_denied",
                    error_message="Source does not permit access to its robots policy.",
                )
            return RobotsDecision(
                robots_url=robots_url,
                allowed=None,
                error_code="robots_unavailable",
                error_message="Source robots policy could not be verified.",
            )

        if response.media_type != "text/plain":
            return RobotsDecision(
                robots_url=robots_url,
                allowed=None,
                error_code="robots_invalid_content_type",
                error_message="Source robots policy did not return plain text.",
            )
        robots_text = self._decode_text(response.content)
        parser = robotparser.RobotFileParser(robots_url)
        parser.parse(robots_text.splitlines())
        if not parser.can_fetch(self.user_agent, target_url):
            return RobotsDecision(
                robots_url=robots_url,
                allowed=False,
                error_code="robots_disallowed",
                error_message="Source robots policy disallows this path.",
            )

        crawl_delay = parser.crawl_delay(self.user_agent)
        if crawl_delay is None:
            crawl_delay = parser.crawl_delay("*")
        delay = float(crawl_delay or 0)
        if delay > self.max_crawl_delay_seconds:
            return RobotsDecision(
                robots_url=robots_url,
                allowed=None,
                error_code="robots_crawl_delay_too_long",
                error_message="Source robots crawl delay exceeds the connector limit.",
            )
        return RobotsDecision(
            robots_url=robots_url,
            allowed=True,
            crawl_delay_seconds=delay,
            rules=parser,
        )

    @staticmethod
    def _decode_text(content: bytes) -> str:
        return content.decode("utf-8", errors="replace")

    async def _extract_content(self, response: SourceFetchResult) -> ParsedSourceContent:
        if response.media_type == "application/pdf":
            return await self._extract_pdf(response.content)
        decoded = self._decode_text(response.content)
        if response.media_type in MARKUP_MEDIA_TYPES:
            parser = _MarkupTextParser()
            try:
                parser.feed(decoded)
                text, title = parser.parsed()
            except (AssertionError, ValueError):
                logger.warning(
                    "web_connector_parse_failed", extra={"media_type": response.media_type}
                )
                return ParsedSourceContent(
                    error_code="parse_failed",
                    error_message="Source content could not be parsed.",
                )
            parser_version = "markup.text.v1"
        else:
            text = decoded.strip()
            title = None
            parser_version = "text.v1"
        if not text:
            return ParsedSourceContent(
                title=title,
                parser_version=parser_version,
                error_code="empty_content",
                error_message="Source contained no extractable text.",
            )
        return ParsedSourceContent(text=text, title=title, parser_version=parser_version)

    async def _extract_pdf(self, content: bytes) -> ParsedSourceContent:
        if self.pdf_parser is None:
            return ParsedSourceContent(
                error_code="parser_unavailable",
                error_message="PDF parsing is not enabled for the public web connector.",
            )
        try:
            parsed = await asyncio.wait_for(
                asyncio.to_thread(self.pdf_parser.parse, content),
                timeout=self.pdf_parse_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("pdf_parse_timed_out")
            return ParsedSourceContent(
                parser_version=self.pdf_parser.parser_version,
                error_code="pdf_parse_timeout",
                error_message="PDF text extraction exceeded the configured time limit.",
            )
        except PDFParseFailure as error:
            logger.info(
                "pdf_parse_unavailable",
                extra={
                    "error_code": error.code,
                    "page_count": error.page_count,
                    "extracted_page_count": error.extracted_page_count,
                },
            )
            return ParsedSourceContent(
                parser_version=getattr(self.pdf_parser, "parser_version", None),
                source_page_count=error.page_count,
                extracted_page_count=error.extracted_page_count,
                error_code=error.code,
                error_message=str(error),
            )
        except Exception as error:
            logger.warning("pdf_parse_failed", extra={"error_type": type(error).__name__})
            return ParsedSourceContent(
                parser_version=self.pdf_parser.parser_version,
                error_code="pdf_parse_failed",
                error_message="PDF text could not be extracted safely.",
            )
        logger.info(
            "pdf_parse_completed",
            extra={
                "page_count": parsed.page_count,
                "extracted_page_count": parsed.extracted_page_count,
                "parser_version": parsed.parser_version,
            },
        )
        return ParsedSourceContent(
            text=parsed.text,
            title=parsed.title,
            parser_version=parsed.parser_version,
            source_page_count=parsed.page_count,
            extracted_page_count=parsed.extracted_page_count,
        )

    @staticmethod
    def _is_retryable(error: SourceFetchUnavailable) -> bool:
        if error.code in {"dns_resolution_failed", "fetch_timeout", "network_error"}:
            return True
        return error.code == "http_error" and error.status_code in RETRYABLE_HTTP_STATUSES

    @staticmethod
    def _blocked(
        requested_url: str,
        attempts: int,
        robots: RobotsDecision | None,
        error_code: str,
        error_message: str,
    ) -> WebConnectorOutcome:
        return WebConnectorOutcome(
            status=ConnectorJobStatus.BLOCKED,
            requested_url=requested_url,
            attempts=attempts,
            robots_url=robots.robots_url if robots else None,
            robots_allowed=robots.allowed if robots else None,
            error_code=error_code,
            error_message=error_message,
        )
