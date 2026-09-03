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

## Audit requirements

Record who/what changed claim status, entity resolution, trust profile, thresholds, prompts, and model versions. Analyst corrections append events and never rewrite historical model output.

## Human control

The analyst can inspect evidence, override machine classifications with a reason, and mark an insight unsuitable for decision use. Low-confidence and disputed results are visually explicit.

## Later requirements

Before multi-user production: authentication, tenant isolation, authorization tests, deletion/export policy, encrypted backups, retention controls, abuse monitoring, and incident response.

