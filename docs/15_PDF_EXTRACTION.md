# PDF text extraction v1

The public-web connector can extract text from public, text-based PDF documents without an API key
or model provider. PDF bytes still pass through the existing SSRF-safe, MIME-limited, size-limited
fetch boundary before parsing.

## Provenance boundary

The connector preserves two distinct fingerprints:

- `ConnectorJob.response_hash` identifies the exact downloaded PDF bytes.
- `Document.content_hash` identifies the normalized text stored as evidence.

The job and document record `pypdf.text.v1` as the parser version. The job also records the source
page count and how many pages produced text. PDF metadata titles are normalized and used only as
document metadata; they are not inserted into evidence text.

Pages are processed in source order. Whitespace inside each extracted block is normalized and
non-empty pages are joined by a blank line. Passages are then segmented from that exact stored
snapshot, so every citation offset remains reproducible against `Document.raw_content`.

## Resource limits

Defaults are deliberately conservative for the student MVP:

| Limit | Default | Environment setting |
|---|---:|---|
| Download size | 5 MiB | `SOURCE_FETCH_MAX_RESPONSE_BYTES` |
| Source pages | 100 | `PDF_PARSE_MAX_PAGES` |
| Parsed characters | 2,000,000 | `PDF_PARSE_MAX_OUTPUT_CHARACTERS` |
| Parse wait | 10 seconds | `PDF_PARSE_TIMEOUT_SECONDS` |

Parsing runs away from the async event loop. The timeout bounds how long the connector waits, while
page and output limits bound accepted results. Strong operating-system process isolation and memory
quotas remain deployment-hardening work before high-volume, hostile-input use.

## Explicit unavailable outcomes

No fallback or invented content is created. The connector records a terminal `unavailable` job for:

- malformed structure (`pdf_malformed`);
- encryption (`pdf_encrypted`);
- zero pages (`pdf_no_pages`);
- too many pages (`pdf_page_limit_exceeded`);
- too much extracted text (`pdf_text_limit_exceeded`);
- a page extraction failure (`pdf_page_parse_failed`);
- a parse timeout (`pdf_parse_timeout`); or
- image-only/scanned content without a text layer (`pdf_no_extractable_text`).

OCR is intentionally not included in v1. It requires a separately bounded adapter and must retain
page-level confidence rather than presenting OCR output as exact native PDF text.
