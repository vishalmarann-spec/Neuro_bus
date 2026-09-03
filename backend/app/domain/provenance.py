import hashlib
import posixpath
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src"}


class InvalidSourceURL(ValueError):
    pass


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def canonicalize_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise InvalidSourceURL("Source URL must use http or https and include a host.")
    if parsed.username or parsed.password:
        raise InvalidSourceURL("Source URL must not contain credentials.")

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/":
        path = path.rstrip("/")

    query_items = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_domain(canonical_url: str) -> str:
    hostname = urlsplit(canonical_url).hostname
    if hostname is None:
        raise InvalidSourceURL("Canonical URL has no host.")
    return hostname


@dataclass(frozen=True, slots=True)
class PassageSpan:
    ordinal: int
    start_offset: int
    end_offset: int
    exact_text: str
    text_hash: str


def segment_passages(raw_content: str, max_characters: int = 1_200) -> list[PassageSpan]:
    if max_characters < 200:
        raise ValueError("max_characters must be at least 200")

    block_boundaries = list(re.finditer(r"(?:\r?\n)[ \t]*(?:\r?\n)+", raw_content))
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for boundary in block_boundaries:
        ranges.append((cursor, boundary.start()))
        cursor = boundary.end()
    ranges.append((cursor, len(raw_content)))

    spans: list[PassageSpan] = []
    for block_start, block_end in ranges:
        while block_start < block_end and raw_content[block_start].isspace():
            block_start += 1
        while block_end > block_start and raw_content[block_end - 1].isspace():
            block_end -= 1
        if block_start >= block_end:
            continue

        chunk_start = block_start
        while chunk_start < block_end:
            chunk_end = min(chunk_start + max_characters, block_end)
            if chunk_end < block_end:
                split_at = raw_content.rfind(" ", chunk_start + 200, chunk_end)
                if split_at > chunk_start:
                    chunk_end = split_at
            while chunk_end > chunk_start and raw_content[chunk_end - 1].isspace():
                chunk_end -= 1
            if chunk_end <= chunk_start:
                break

            exact_text = raw_content[chunk_start:chunk_end]
            spans.append(
                PassageSpan(
                    ordinal=len(spans),
                    start_offset=chunk_start,
                    end_offset=chunk_end,
                    exact_text=exact_text,
                    text_hash=sha256_text(exact_text),
                )
            )
            chunk_start = chunk_end
            while chunk_start < block_end and raw_content[chunk_start].isspace():
                chunk_start += 1

    return spans

