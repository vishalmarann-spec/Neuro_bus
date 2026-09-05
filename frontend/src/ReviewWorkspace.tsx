import { FormEvent, useEffect, useMemo, useState } from "react";

import { ApiError, fetchBenchmarkReviews, submitBenchmarkReviewDecision } from "./api";
import type {
  BenchmarkReviewCase,
  BenchmarkReviewChecklist,
  BenchmarkReviewDecision,
  BenchmarkReviewQueue,
  BenchmarkReviewState,
} from "./types";

const stateLabels: Record<BenchmarkReviewState, string> = {
  pending: "Pending",
  approved: "Approved",
  changes_requested: "Changes requested",
  rejected: "Rejected",
  stale: "Stale",
};

const emptyChecklist: BenchmarkReviewChecklist = {
  source_url_opened: false,
  excerpt_matches_source: false,
  entities_and_claims_checked: false,
};

function shortHash(value: string | null): string {
  if (!value) return "Not supplied";
  return value.length > 26 ? `${value.slice(0, 18)}…${value.slice(-7)}` : value;
}

function formatDate(value: string | null): string {
  if (!value) return "Not supplied";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
        parsed,
      );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function reviewError(reason: unknown): string {
  return reason instanceof ApiError
    ? reason.message
    : "The review API could not be reached. Check that the backend is running locally.";
}

function summarizeCases(cases: BenchmarkReviewCase[]): BenchmarkReviewQueue["summary"] {
  const summary: BenchmarkReviewQueue["summary"] = {
    total: cases.length,
    pending: 0,
    approved: 0,
    changes_requested: 0,
    rejected: 0,
    stale: 0,
  };
  for (const item of cases) summary[item.state] += 1;
  return summary;
}

function CaseQueueItem({
  item,
  active,
  onSelect,
}: {
  item: BenchmarkReviewCase;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`review-case-item${active ? " active" : ""}`}
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
    >
      <span className={`review-state state-${item.state}`}>{stateLabels[item.state]}</span>
      <strong>{item.case.document.title}</strong>
      <small>{item.case.document.publisher}</small>
      <span className="case-id">{item.case.case_id}</span>
    </button>
  );
}

function GoldLabels({ item }: { item: BenchmarkReviewCase }) {
  const { entities, claims } = item.case.gold;
  return (
    <section className="gold-labels" aria-labelledby="gold-label-heading">
      <div className="section-heading-row">
        <div>
          <p className="kicker">Gold extraction</p>
          <h2 id="gold-label-heading">Expected entities and claims</h2>
        </div>
        <span>{entities.length} entities · {claims.length} claims</span>
      </div>

      <div className="gold-grid">
        <div>
          <h3>Entities</h3>
          {entities.length ? (
            <div className="label-stack">
              {entities.map((entity) => (
                <article className="gold-card" key={entity.local_id}>
                  <header>
                    <strong>{entity.canonical_name}</strong>
                    <span>{humanize(entity.entity_type)}</span>
                  </header>
                  {entity.mentions.map((mention, index) => (
                    <p key={`${entity.local_id}-${index}`}>
                      “{mention.surface_text}” <code>{mention.start_offset}:{mention.end_offset}</code>
                    </p>
                  ))}
                </article>
              ))}
            </div>
          ) : <p className="review-empty">No gold entities.</p>}
        </div>

        <div>
          <h3>Claims</h3>
          {claims.length ? (
            <div className="label-stack">
              {claims.map((claim, index) => (
                <article className="gold-card" key={`${claim.predicate}-${index}`}>
                  <header><strong>{claim.normalized_text}</strong></header>
                  <p><code>{claim.predicate}</code></p>
                  <pre>{JSON.stringify(claim.object_value, null, 2)}</pre>
                  {claim.evidence.map((evidence, evidenceIndex) => (
                    <small key={`${claim.predicate}-${evidenceIndex}`}>
                      Passage {evidence.passage_ordinal} · {evidence.stance} — {evidence.rationale}
                    </small>
                  ))}
                </article>
              ))}
            </div>
          ) : (
            <div className="negative-case-note">
              <strong>No testable claim expected.</strong>
              <p>This is a promotion-only negative case. Reject any invented factual claim.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function DecisionForm({
  item,
  onSaved,
}: {
  item: BenchmarkReviewCase;
  onSaved: (saved: BenchmarkReviewCase) => void;
}) {
  const [reviewer, setReviewer] = useState(() => localStorage.getItem("neurobus-reviewer") ?? "");
  const [decision, setDecision] = useState<BenchmarkReviewDecision>("approved");
  const [checklist, setChecklist] = useState<BenchmarkReviewChecklist>(emptyChecklist);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    setDecision("approved");
    setChecklist(emptyChecklist);
    setNotes("");
    setError(null);
    setSavedMessage(null);
  }, [item.case.case_id, item.case_fingerprint]);

  function toggle(key: keyof BenchmarkReviewChecklist) {
    setChecklist((current) => ({ ...current, [key]: !current[key] }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSavedMessage(null);
    try {
      const saved = await submitBenchmarkReviewDecision(item.case.case_id, {
        case_fingerprint: item.case_fingerprint,
        reviewer,
        decision,
        checklist,
        notes,
      });
      localStorage.setItem("neurobus-reviewer", reviewer.trim());
      setSavedMessage(`${stateLabels[saved.state]} decision appended to the review ledger.`);
      onSaved(saved);
    } catch (reason) {
      setError(reviewError(reason));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="decision-panel" aria-labelledby="decision-heading">
      <p className="kicker">Human attestation</p>
      <h2 id="decision-heading">Record your decision</h2>
      <p className="decision-warning">
        Check each item only after you personally complete it. Approval is blocked unless all
        three checks are confirmed.
      </p>

      <form onSubmit={submit}>
        <label className="field-label" htmlFor="reviewer-name">Reviewer full name</label>
        <input
          id="reviewer-name"
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          minLength={2}
          maxLength={160}
          required
          autoComplete="name"
        />

        <fieldset className="decision-options">
          <legend>Decision</legend>
          {(["approved", "changes_requested", "rejected"] as const).map((value) => (
            <label key={value}>
              <input
                type="radio"
                name="decision"
                value={value}
                checked={decision === value}
                onChange={() => setDecision(value)}
              />
              <span>{stateLabels[value]}</span>
            </label>
          ))}
        </fieldset>

        <fieldset className="review-checklist">
          <legend>Verification checklist</legend>
          <label>
            <input
              type="checkbox"
              checked={checklist.source_url_opened}
              onChange={() => toggle("source_url_opened")}
            />
            <span>I opened the official source URL.</span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={checklist.excerpt_matches_source}
              onChange={() => toggle("excerpt_matches_source")}
            />
            <span>The stored excerpt exactly matches the source.</span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={checklist.entities_and_claims_checked}
              onChange={() => toggle("entities_and_claims_checked")}
            />
            <span>I checked every entity, claim, and evidence offset.</span>
          </label>
        </fieldset>

        <label className="field-label" htmlFor="review-notes">Review notes</label>
        <textarea
          id="review-notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          minLength={3}
          maxLength={2000}
          required
          placeholder="What did you verify, or what needs correction?"
          rows={5}
        />

        {error ? <div className="form-message form-error" role="alert">{error}</div> : null}
        {savedMessage ? (
          <div className="form-message form-success" role="status">{savedMessage}</div>
        ) : null}
        <button className="review-submit" type="submit" disabled={submitting}>
          {submitting ? "Appending…" : "Append decision"}
        </button>
      </form>
    </section>
  );
}

export default function ReviewWorkspace() {
  const query = new URLSearchParams(window.location.search);
  const initialCaseId = query.get("case");
  const [queue, setQueue] = useState<BenchmarkReviewQueue | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(initialCaseId);
  const [filter, setFilter] = useState<BenchmarkReviewState | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadQueue(signal?: AbortSignal) {
    setLoading(true);
    setError(null);
    try {
      const loaded = await fetchBenchmarkReviews(undefined, signal);
      setQueue(loaded);
      setSelectedId((current) => {
        if (current && loaded.cases.some((item) => item.case.case_id === current)) return current;
        return loaded.cases.find((item) => item.state === "pending")?.case.case_id
          ?? loaded.cases[0]?.case.case_id
          ?? null;
      });
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reviewError(reason));
      setQueue(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void loadQueue(controller.signal);
    return () => controller.abort();
  }, []);

  const visibleCases = useMemo(
    () => queue?.cases.filter((item) => filter === "all" || item.state === filter) ?? [],
    [filter, queue],
  );
  const selected = queue?.cases.find((item) => item.case.case_id === selectedId) ?? null;

  function selectCase(caseId: string) {
    setSelectedId(caseId);
    const url = new URL(window.location.href);
    url.searchParams.set("workspace", "review");
    url.searchParams.set("case", caseId);
    window.history.replaceState({}, "", url);
  }

  function decisionSaved(saved: BenchmarkReviewCase) {
    setQueue((current) => {
      if (!current) return current;
      const cases = current.cases.map((item) =>
        item.case.case_id === saved.case.case_id ? saved : item,
      );
      return { cases, summary: summarizeCases(cases) };
    });
  }

  return (
    <div className="app-shell review-app">
      <header className="topbar review-topbar">
        <a className="brand" href="/" aria-label="Neuro Bus">
          <span className="brand-mark" aria-hidden="true">N</span>
          <span><strong>Neuro_Bus</strong><small>Benchmark review</small></span>
        </a>
        <div className="review-topbar-title">
          <span>Human verification</span>
          <strong>{queue ? `${queue.summary.approved} of ${queue.summary.total} approved` : "Loading queue"}</strong>
        </div>
        <div className="topbar-actions">
          <a className="button-secondary" href="/">Report workspace</a>
          <button className="button-secondary" type="button" onClick={() => void loadQueue()}>
            Refresh
          </button>
        </div>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      {loading ? <div className="loading-bar" role="status"><span />Loading review queue…</div> : null}

      <main className="review-main">
        {queue ? (
          <div className="review-layout">
            <aside className="review-queue" aria-label="Benchmark cases">
              <div className="review-progress">
                <div>
                  <span
                    style={{
                      width: `${queue.summary.total
                        ? (queue.summary.approved / queue.summary.total) * 100
                        : 0}%`,
                    }}
                  />
                </div>
                <p>{queue.summary.pending} pending · {queue.summary.stale} stale</p>
              </div>
              <label htmlFor="review-filter">Filter cases</label>
              <select
                id="review-filter"
                value={filter}
                onChange={(event) => setFilter(event.target.value as BenchmarkReviewState | "all")}
              >
                <option value="all">All cases ({queue.summary.total})</option>
                {(Object.keys(stateLabels) as BenchmarkReviewState[]).map((state) => (
                  <option value={state} key={state}>
                    {stateLabels[state]} ({queue.summary[state]})
                  </option>
                ))}
              </select>
              <div className="review-case-list">
                {visibleCases.map((item) => (
                  <CaseQueueItem
                    item={item}
                    active={item.case.case_id === selectedId}
                    onSelect={() => selectCase(item.case.case_id)}
                    key={item.case.case_id}
                  />
                ))}
                {!visibleCases.length ? <p className="review-empty">No cases match this filter.</p> : null}
              </div>
            </aside>

            {selected ? (
              <article className="review-content">
                <header className="review-case-heading">
                  <div className="review-badges">
                    <span className={`review-state state-${selected.state}`}>
                      {stateLabels[selected.state]}
                    </span>
                    <span>{selected.case.difficulty}</span>
                    {selected.case.task_tags.map((tag) => <span key={tag}>{humanize(tag)}</span>)}
                  </div>
                  <h1>{selected.case.document.title}</h1>
                  <p>{selected.case.document.publisher} · {humanize(selected.case.document.source_type ?? "unknown source")}</p>
                </header>

                <section className="source-review" aria-labelledby="source-heading">
                  <div className="section-heading-row">
                    <div>
                      <p className="kicker">Source evidence</p>
                      <h2 id="source-heading">Verify the exact excerpt</h2>
                    </div>
                    {selected.case.document.source_url ? (
                      <a href={selected.case.document.source_url} target="_blank" rel="noreferrer">
                        Open official source ↗
                      </a>
                    ) : null}
                  </div>
                  <blockquote>{selected.case.document.raw_content}</blockquote>
                  <dl className="review-metadata">
                    <div><dt>Retrieved</dt><dd>{formatDate(selected.case.document.retrieved_at)}</dd></div>
                    <div><dt>Content hash</dt><dd title={selected.case.document.content_hash ?? undefined}>{shortHash(selected.case.document.content_hash)}</dd></div>
                    <div><dt>Case fingerprint</dt><dd title={selected.case_fingerprint}>{shortHash(selected.case_fingerprint)}</dd></div>
                    <div><dt>Word count</dt><dd>{selected.case.document.raw_content.trim().split(/\s+/).length}</dd></div>
                  </dl>
                </section>

                <GoldLabels item={selected} />

                {selected.latest_review ? (
                  <section className="latest-review">
                    <p className="kicker">Latest ledger entry</p>
                    <h2>{stateLabels[selected.latest_review.decision]} by {selected.latest_review.reviewer}</h2>
                    <p>{selected.latest_review.notes}</p>
                    <small>{formatDate(selected.latest_review.reviewed_at)}</small>
                  </section>
                ) : null}

                <DecisionForm item={selected} onSaved={decisionSaved} />
              </article>
            ) : <div className="review-empty-page">Select a benchmark case to begin.</div>}
          </div>
        ) : null}
      </main>
    </div>
  );
}
