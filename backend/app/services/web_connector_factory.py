from app.core.config import Settings
from app.domain.source_policy import SourceFetchPolicy
from app.providers.http_source import SafeSourceFetcher
from app.services.pdf_parser import PyPDFTextParser
from app.services.web_connector import HostRateLimiter, PublicWebConnector


def create_public_web_connector(settings: Settings) -> PublicWebConnector:
    policy = SourceFetchPolicy(
        timeout_seconds=settings.source_fetch_timeout_seconds,
        max_redirects=settings.source_fetch_max_redirects,
        max_response_bytes=settings.source_fetch_max_response_bytes,
    )
    return PublicWebConnector(
        fetcher=SafeSourceFetcher(policy=policy),
        rate_limiter=HostRateLimiter(settings.source_fetch_host_interval_seconds),
        source_policy=policy,
        max_attempts=settings.source_fetch_max_attempts,
        retry_base_seconds=settings.source_fetch_retry_base_seconds,
        max_crawl_delay_seconds=settings.source_fetch_max_crawl_delay_seconds,
        pdf_parser=PyPDFTextParser(
            max_pages=settings.pdf_parse_max_pages,
            max_output_characters=settings.pdf_parse_max_output_characters,
        ),
        pdf_parse_timeout_seconds=settings.pdf_parse_timeout_seconds,
    )
