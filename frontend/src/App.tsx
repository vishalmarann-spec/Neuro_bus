import { FormEvent, useEffect, useMemo, useState } from "react";

import { ApiError, fetchInsightReport, insightExportPath } from "./api";
import type {
  ClusterLabel,
  EvidenceStance,
  InsightCitation,
  InsightReport,
} from "./types";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const labelNames: Record<ClusterLabel, string> = {
  well_supported: "Well supported",
  supported: "Supported",
  emerging: "Emerging",
  weak: "Weak",
  disputed: "Disputed",
};

const stanceNames: Record<EvidenceStance, string> = {
  supports: "Supports",
  contradicts: "Contradicts",
  contextual: "Context",
  irrelevant: "Irrelevant",
};

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null): string {
  if (!value) return "Not supplied";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

function shortHash(value: string): string {
  return value.length > 26 ? `${value.slice(0, 18)}…${value.slice(-7)}` : value;
}

function CitationCard({ citation, index }: { citation: InsightCitation; index: number }) {
  const domain = useMemo(() => {
    try {
      return new URL(citation.canonical_url).hostname.replace(/^www\./, "");
    } catch {
      return citation.canonical_url;
    }
  }, [citation.canonical_url]);

  return (
    <article className={`citation-card citation-${citation.stance}`}>
      <header className="citation-header">
        <div>
          <span className={`stance stance-${citation.stance}`}>
            {stanceNames[citation.stance]}
          </span>
          <h4>{citation.publisher}</h4>
          <a href={citation.canonical_url} target="_blank" rel="noreferrer">
            {domain}
            <span aria-hidden="true"> ↗</span>
          </a>
        </div>
        <span className="citation-index" aria-label={`Citation ${index}`}>
          {String(index).padStart(2, "0")}
        </span>
      </header>

      <blockquote>{citation.quote}</blockquote>

      <dl className="citation-meta">
        <div>
          <dt>Evidence quality</dt>
          <dd>{citation.evidence_quality === null ? "Not calculated" : percent(citation.evidence_quality)}</dd>
        </div>
        <div>
          <dt>Published</dt>
          <dd>{formatDate(citation.published_at)}</dd>
        </div>
        <div>
          <dt>Retrieved</dt>
          <dd>{formatDate(citation.retrieved_at)}</dd>
        </div>
        <div>
          <dt>Document hash</dt>
          <dd title={citation.document_hash}>{shortHash(citation.document_hash)}</dd>
        </div>
      </dl>
    </article>
  );
}

function EmptyWorkspace() {
  return (
    <section className="empty-workspace" aria-labelledby="empty-heading">
      <div className="empty-mark" aria-hidden="true">
        NB
      </div>
      <p className="kicker">Report workspace</p>
      <h1 id="empty-heading">Inspect a complete chain of evidence.</h1>
      <p>
        Enter an insight ID above to review its findings, confidence calculation, supporting
        sources, contradictions, and immutable provenance.
      </p>
      <ol className="workflow">
        <li><span>01</span> Load a scored insight</li>
        <li><span>02</span> Inspect every cited passage</li>
        <li><span>03</span> Export the evidence record</li>
      </ol>
    </section>
  );
}

function ReportWorkspace({ report }: { report: InsightReport }) {
  const { insight, statements } = report;
  const sourceCount = new Set(
    statements.flatMap((statement) => statement.citations.map((citation) => citation.canonical_url)),
  ).size;
  const disputedCount = statements.filter((statement) => statement.label === "disputed").length;
  const confidenceAngle = `${Math.round(insight.confidence * 360)}deg`;

  return (
    <div className="report-layout">
      <aside className="report-rail" aria-label="Report summary">
        <div
          className="confidence-ring"
          style={{ "--confidence-angle": confidenceAngle } as React.CSSProperties}
          aria-label={`Report confidence ${percent(insight.confidence)}`}
        >
          <span>{percent(insight.confidence)}</span>
          <small>confidence</small>
        </div>

        <dl className="summary-list">
          <div><dt>Findings</dt><dd>{statements.length}</dd></div>
          <div><dt>Sources</dt><dd>{sourceCount}</dd></div>
          <div><dt>Disputed</dt><dd>{disputedCount}</dd></div>
          <div><dt>Weak excluded</dt><dd>{insight.explanation.excluded_weak_cluster_count ?? 0}</dd></div>
        </dl>

        <div className="method-note">
          <span>Method</span>
          <p>{insight.explanation.confidence_method ?? "Stored report calculation"}</p>
        </div>

        <dl className="audit-list">
          <div><dt>Version</dt><dd>{insight.generation_version}</dd></div>
          <div><dt>Created</dt><dd>{formatDate(insight.created_at)}</dd></div>
          <div><dt>Fingerprint</dt><dd title={insight.fingerprint}>{shortHash(insight.fingerprint)}</dd></div>
        </dl>
      </aside>

      <article className="report-content">
        <header className="report-heading">
          <div className="report-heading-meta">
            <span className={`report-status status-${insight.status}`}>
              {insight.status === "ready" ? "Ready" : "Needs review"}
            </span>
            <span>{statements.length} evidence-backed {statements.length === 1 ? "finding" : "findings"}</span>
          </div>
          <h1>{insight.title.replace(/^Evidence report:\s*/i, "")}</h1>
          <p className="report-id">Insight {insight.id}</p>
        </header>

        <div className="findings">
          {statements.map((statement, statementIndex) => {
            const supports = statement.citations.filter((item) => item.stance === "supports").length;
            const contradictions = statement.citations.filter(
              (item) => item.stance === "contradicts",
            ).length;
            return (
              <section className="finding" key={statement.id} aria-labelledby={`finding-${statement.id}`}>
                <header className="finding-header">
                  <div className="finding-number">{String(statementIndex + 1).padStart(2, "0")}</div>
                  <div className="finding-title">
                    <div className="finding-labels">
                      <span className={`claim-label label-${statement.label}`}>
                        {labelNames[statement.label]}
                      </span>
                      <span>{percent(statement.confidence)} confidence</span>
                    </div>
                    <h2 id={`finding-${statement.id}`}>{statement.text}</h2>
                  </div>
                </header>

                <div className="evidence-tally" aria-label="Evidence summary">
                  <span className="tally-support">{supports} supporting</span>
                  <span className="tally-contradict">{contradictions} contradicting</span>
                  <span>{statement.citations.length} total citations</span>
                </div>

                <details className="evidence-disclosure" open>
                  <summary>View cited evidence</summary>
                  <div className="citation-list">
                    {statement.citations.map((citation, citationIndex) => (
                      <CitationCard
                        citation={citation}
                        index={citationIndex + 1}
                        key={citation.evidence_link_id}
                      />
                    ))}
                  </div>
                </details>
              </section>
            );
          })}
        </div>
      </article>
    </div>
  );
}

export default function App() {
  const initialInsightId = new URLSearchParams(window.location.search).get("insight") ?? "";
  const [insightId, setInsightId] = useState(initialInsightId);
  const [report, setReport] = useState<InsightReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadReport(id: string, signal?: AbortSignal) {
    const normalizedId = id.trim();
    if (!UUID_PATTERN.test(normalizedId)) {
      setError("Enter a valid insight UUID.");
      setReport(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const loaded = await fetchInsightReport(normalizedId, signal);
      setReport(loaded);
      const url = new URL(window.location.href);
      url.searchParams.set("insight", normalizedId);
      window.history.replaceState({}, "", url);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setReport(null);
      setError(
        reason instanceof ApiError
          ? reason.message
          : "The evidence API could not be reached. Check that the backend is running.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!initialInsightId) return;
    const controller = new AbortController();
    void loadReport(initialInsightId, controller.signal);
    return () => controller.abort();
    // The query parameter is intentionally read once when the workspace opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadReport(insightId);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Neuro Bus report workspace">
          <span className="brand-mark" aria-hidden="true">N</span>
          <span><strong>Neuro_Bus</strong><small>Evidence intelligence</small></span>
        </a>

        <form className="report-loader" onSubmit={submit} noValidate>
          <label htmlFor="insight-id">Insight ID</label>
          <div className="report-loader-controls">
            <input
              id="insight-id"
              value={insightId}
              onChange={(event) => setInsightId(event.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              spellCheck={false}
              autoComplete="off"
              aria-describedby={error ? "load-error" : undefined}
            />
            <button type="submit" disabled={loading}>
              {loading ? "Loading…" : "Load report"}
            </button>
          </div>
        </form>

        <div className="topbar-actions">
          {report ? (
            <>
              <a className="button-secondary" href={insightExportPath(report.insight.id)} download>
                Export .md
              </a>
              <button className="button-secondary" type="button" onClick={() => window.print()}>
                Print
              </button>
            </>
          ) : null}
        </div>
      </header>

      {error ? <div className="error-banner" id="load-error" role="alert">{error}</div> : null}
      {loading ? <div className="loading-bar" role="status"><span />Loading evidence report…</div> : null}

      <main>{report ? <ReportWorkspace report={report} /> : <EmptyWorkspace />}</main>

      <footer className="app-footer">
        <span>Every finding must resolve to stored evidence.</span>
        <a href="https://github.com/vishalmarann-spec/Neuro_bus" target="_blank" rel="noreferrer">
          Repository ↗
        </a>
      </footer>
    </div>
  );
}
