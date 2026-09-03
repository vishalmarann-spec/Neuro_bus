# Product specification

## 1. Problem

Decision-makers face large volumes of fragmented web pages, reports, discussions, videos, datasets, and competitor material. Current research workflows either require extensive manual work or produce AI summaries whose source support and uncertainty are difficult to audit.

Neuro_Bus converts those signals into structured evidence and decision-ready insights without hiding uncertainty.

## 2. First user and vertical

The MVP serves a university strategy or curriculum analyst researching questions such as:

- Which technology courses are showing credible demand growth?
- How are competing universities positioning and pricing similar programmes?
- Which skills appear in employer demand but not in current curricula?
- Is an apparent trend supported by independent sources or amplified repetition?

This is the proving ground, not a permanent product limitation.

## 3. Core jobs

An analyst can:

1. Create a research project and question.
2. Add or discover public sources.
3. Run evidence extraction.
4. Review extracted claims and exact supporting passages.
5. See corroboration, contradiction, source independence, and confidence.
6. Produce a cited insight report.
7. Correct entity matches and claim classifications with an audit trail.

## 4. MVP outputs

- Evidence table with filters by source, entity, stance, date, and confidence
- Claim detail showing verbatim evidence passages and provenance
- Entity and relationship view
- Conflicts requiring analyst review
- Insight cards containing conclusion, confidence, rationale, and citations
- Exportable evidence report

## 5. Non-goals for MVP

- Predicting stock prices or guaranteeing future market outcomes
- Autonomous business decisions
- Ingesting private CRM or personal data
- Real-time monitoring of every social network
- Supporting every industry at launch
- A general-purpose chatbot over unverified web results
- Replacing analyst judgment

## 6. Success criteria

### Evidence integrity

- 100% of surfaced claims link to at least one stored passage.
- 100% of passages link to a captured document and source URL.
- A stored passage can be verified against its immutable document snapshot/hash.
- Contradictory evidence is displayed alongside supporting evidence.

### Extraction quality

- On a labelled evaluation set, claim extraction precision reaches at least 0.80.
- Entity resolution precision reaches at least 0.85 on reviewed university-domain examples.
- Citation correctness reaches at least 0.95: the cited passage actually supports the assigned stance.

### Product utility

- An analyst can trace an insight to source evidence in no more than two interactions.
- A complete small research run of up to 20 documents completes without manual database repair.
- Connector/model failures produce a visible partial result and retryable error.

## 7. MVP boundary

The first demo topic is `AI security university education`. It must use at least five accessible sources from at least three independent domains. YouTube and Reddit are optional inputs, not launch blockers.

## 8. Product language

- **Source:** publisher/domain/channel that produced material.
- **Document:** immutable captured content at a particular time.
- **Passage:** exact span taken from a document.
- **Claim:** normalized, testable statement extracted from evidence.
- **Evidence link:** relationship between a passage and claim with a stance.
- **Entity:** resolved real-world subject such as a university, course, skill, or employer.
- **Insight:** decision-oriented synthesis of claims; never itself treated as evidence.

