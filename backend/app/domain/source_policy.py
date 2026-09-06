import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import SplitResult, urlsplit, urlunsplit

DEFAULT_ALLOWED_MEDIA_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "application/xhtml+xml",
        "application/xml",
        "text/html",
        "text/plain",
        "text/xml",
    }
)
BLOCKED_HOST_SUFFIXES = (".home.arpa", ".internal", ".local", ".localhost")
HOST_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SourcePolicyViolation(ValueError):
    """A target or response violates the outbound source policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ValidatedSourceTarget:
    url: str
    scheme: str
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class SourceFetchPolicy:
    timeout_seconds: float = 15.0
    max_redirects: int = 3
    max_response_bytes: int = 5 * 1024 * 1024
    allowed_media_types: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWED_MEDIA_TYPES)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("Source fetch timeout must be positive.")
        if self.max_redirects < 0:
            raise ValueError("Source fetch redirect limit cannot be negative.")
        if self.max_response_bytes < 1:
            raise ValueError("Source fetch byte limit must be positive.")
        if not self.allowed_media_types:
            raise ValueError("At least one source media type must be allowed.")

    def validate_target(self, value: str) -> ValidatedSourceTarget:
        candidate = value.strip()
        if not candidate or any(
            ord(character) < 32 or ord(character) == 127 for character in candidate
        ):
            raise SourcePolicyViolation("invalid_url", "Source URL is invalid.")

        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError as error:
            raise SourcePolicyViolation("invalid_url", "Source URL is invalid.") from error

        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise SourcePolicyViolation(
                "invalid_url", "Source URL must use HTTP or HTTPS and include a host."
            )
        if parsed.username or parsed.password:
            raise SourcePolicyViolation(
                "embedded_credentials", "Source URL must not contain credentials."
            )

        expected_port = 443 if scheme == "https" else 80
        if port not in {None, expected_port}:
            raise SourcePolicyViolation(
                "disallowed_port", "Source URL must use the standard port for its scheme."
            )

        host = self._normalize_host(parsed.hostname)
        self._validate_host(host)
        normalized = self._normalized_url(parsed, scheme, host, port)
        return ValidatedSourceTarget(
            url=normalized,
            scheme=scheme,
            host=host,
            port=expected_port,
        )

    def validate_media_type(self, header_value: str | None) -> str:
        if header_value is None:
            raise SourcePolicyViolation(
                "missing_content_type", "Source response did not declare a content type."
            )
        media_type = header_value.partition(";")[0].strip().lower()
        if media_type not in self.allowed_media_types:
            raise SourcePolicyViolation(
                "disallowed_content_type", "Source response content type is not allowed."
            )
        return media_type

    def validate_content_length(self, header_value: str | None) -> int | None:
        if header_value is None:
            return None
        try:
            length = int(header_value)
        except ValueError as error:
            raise SourcePolicyViolation(
                "invalid_content_length", "Source response content length is invalid."
            ) from error
        if length < 0:
            raise SourcePolicyViolation(
                "invalid_content_length", "Source response content length is invalid."
            )
        if length > self.max_response_bytes:
            raise SourcePolicyViolation(
                "response_too_large", "Source response exceeds the configured byte limit."
            )
        return length

    @staticmethod
    def _normalize_host(host: str) -> str:
        without_trailing_dot = host.rstrip(".")
        try:
            return without_trailing_dot.encode("idna").decode("ascii").lower()
        except UnicodeError as error:
            raise SourcePolicyViolation("invalid_host", "Source host is invalid.") from error

    @staticmethod
    def _validate_host(host: str) -> None:
        if not host or host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
            raise SourcePolicyViolation(
                "private_network_target", "Source target is not a public network address."
            )

        try:
            address = ipaddress.ip_address(host.split("%", maxsplit=1)[0])
        except ValueError:
            labels = host.split(".")
            if len(host) > 253 or any(not HOST_LABEL_PATTERN.fullmatch(label) for label in labels):
                raise SourcePolicyViolation("invalid_host", "Source host is invalid.") from None
            return
        validate_public_address(address)

    @staticmethod
    def _normalized_url(
        parsed: SplitResult, scheme: str, host: str, explicit_port: int | None
    ) -> str:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            netloc = host
        else:
            netloc = f"[{host}]" if address.version == 6 else host
        if explicit_port is not None:
            netloc = f"{netloc}:{explicit_port}"
        return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def validate_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    comparable = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    checked = comparable or address
    if not checked.is_global:
        raise SourcePolicyViolation(
            "private_network_target", "Source target is not a public network address."
        )
    return address.compressed
