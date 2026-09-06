# Security, privacy, and governance

## MVP data policy

- Ingest public, business-relevant material only.
- Do not ingest private CRM data, credentials, paywalled material, or personal profiles.
- Respect robots policy, terms, rate limits, and content licensing constraints.
- Store the minimum source text required for reproducibility and review.
- Reports cite sources; they do not republish entire documents.

## Threat boundaries

- Treat web content as untrusted input and ignore instructions embedded in it.
- Restrict fetch protocols and block private/link-local network targets.
- Limit redirects, response size, MIME types, and request duration.
- Sanitize rendered text and never execute fetched scripts.
- Validate model output against strict schemas.
- Keep secrets in environment/secret management only.

## Public-source fetch boundary

`SafeSourceFetcher` is the required network boundary for web connectors. The first public-web
connector is submitted through an asynchronous job API and executed by a database-claiming worker;
manual document capture still makes no outbound network requests.

The default policy:

- permits only HTTP and HTTPS on their standard ports and rejects embedded credentials;
- rejects localhost and internal-use host suffixes before a request is made;
- resolves every connection immediately before dialing, rejects the entire DNS answer if any
  address is non-public, and connects to the validated numeric address to prevent DNS rebinding;
- disables environment proxy inheritance and Unix-socket connections;
- follows at most three manually validated redirects, detects loops, and blocks HTTPS-to-HTTP
  downgrades;
- accepts only HTML, plain text, XML, JSON, XHTML, and PDF responses;
- rejects missing or invalid content types, oversized `Content-Length` values, and decoded bodies
  above 5 MiB; and
- applies a 15-second wall-clock limit to the complete redirect chain.

Failures expose a stable error code and a sanitized message. Logs include the target host, failure
code, status, media type, byte count, and redirect count when available, but never URL queries or
response bodies. The public-web connector checks `robots.txt`, honors a bounded crawl delay,
spaces requests per host including redirect targets, and retries only transient failures. Source
terms and licensing remain operator checks before a URL is submitted.

Text-based PDF extraction uses local `pypdf` parsing with page-count, output-character, and wait
limits. Encrypted, malformed, over-limit, and image-only documents are recorded as unavailable;
OCR is not silently substituted. The exact PDF response hash remains distinct from the parsed-text
document hash. Process-level parser isolation and memory quotas remain required before hostile,
high-volume production use.

Connector idempotency keys are stored only as SHA-256 hashes. Worker claims expire so abandoned
jobs can be recovered, and terminal updates require the current lease owner. Worker logs use job
identifiers rather than requested URLs and unexpected exception details are not returned by the API.

## Audit requirements

Record who/what changed claim status, entity resolution, trust profile, thresholds, prompts, and model versions. Analyst corrections append events and never rewrite historical model output.

## Human control

The analyst can inspect evidence, override machine classifications with a reason, and mark an insight unsuitable for decision use. Low-confidence and disputed results are visually explicit.

## Later requirements

Before multi-user production: authentication, tenant isolation, authorization tests, deletion/export policy, encrypted backups, retention controls, abuse monitoring, and incident response.
