# Public web connector v1

The first real-source connector collects a user-supplied public URL without an API key or paid
provider. It uses `SafeSourceFetcher`; no connector may replace or bypass that network boundary.

## API and lifecycle

`POST /api/v1/runs/{run_id}/connector-jobs` requires the URL, declared publisher, and optional
publisher family, source type, title, and publication timestamp. During the MVP the request runs
inline, but a durable job is committed as `queued`, changed to `running`, and then finished in
exactly one terminal state:

| Status | Meaning | Document created |
|---|---|---|
| `succeeded` | robots allowed, fetch and parsing succeeded | yes |
| `blocked` | URL, redirect, response, or robots rule violated policy | no |
| `unavailable` | robots could not be verified, retries failed, or no parser exists | no |

Every terminal record includes its attempt count and timestamps. When available it also stores the
robots URL and decision, final URL, MIME type, redirect count, response size, SHA-256 fingerprint,
linked document, and sanitized failure code/message.

The response fingerprint covers the exact decoded response bytes returned by the HTTP client. The
linked `Document.content_hash` covers the inert text passed to deterministic passage segmentation.
Keeping both hashes makes the raw-to-parsed boundary explicit.

## Robots policy

The connector requests the target origin's `/robots.txt` through the same SSRF-safe fetcher.

- HTTP 404 or 410 means no robots file and permits the requested path.
- HTTP 401 or 403 blocks collection.
- Other network or HTTP failures produce `robots_unavailable`; the connector fails closed.
- A successful robots response must be `text/plain`.
- Matching `Disallow` rules block collection.
- `Crawl-delay` is honored up to 10 seconds. A larger delay is recorded as unavailable instead of
  leaving an inline request open indefinitely.

## Rate limiting and retries

The process-local limiter spaces all requests to the same host, including robots, source retries,
and redirect hops. The default minimum is one second. Robots crawl delay can increase it.

V1 follows redirects only within the original scheme, host, and port. Before each same-origin
redirect, the destination path is checked against the verified robots rules. Cross-origin
redirects and redirects to disallowed paths are blocked before the destination request is sent.

The connector makes at most three source attempts. It retries DNS, network, and timeout failures,
plus HTTP 408, 425, 429, 500, 502, 503, and 504. Backoff starts at 0.5 seconds and doubles. Other
failures stop immediately. Robots verification itself is not retried in v1.

Before multiple worker processes are enabled, the process-local limiter must be replaced with a
shared Redis-backed reservation mechanism so the per-host policy remains global.

## Parsing boundary

HTML, XHTML, and XML are converted into deterministic plain text with scripts, styles, SVG,
templates, and noscript content removed. The page title is stored as metadata rather than evidence
text. Plain text and JSON are decoded as UTF-8 with replacement for invalid bytes. Empty results do
not create documents.

PDF downloads are safely fingerprinted but finish as `parser_unavailable`; PDF text extraction is
a separate checkpoint. The connector never invents fallback content.

Terms, licensing, paywall status, and permission to retain content require operator verification
before submission. The connector only automates network and robots controls.
