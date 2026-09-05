export type InsightStatus = "ready" | "needs_review";
export type ClusterLabel =
  | "well_supported"
  | "supported"
  | "emerging"
  | "weak"
  | "disputed";
export type EvidenceStance = "supports" | "contradicts" | "contextual" | "irrelevant";

export interface Insight {
  id: string;
  run_id: string;
  title: string;
  conclusion: string;
  confidence: number;
  status: InsightStatus;
  generation_version: string;
  fingerprint: string;
  explanation: {
    included_cluster_count?: number;
    excluded_weak_cluster_count?: number;
    excluded_without_supporting_citations_count?: number;
    disputed_cluster_count?: number;
    confidence_method?: string;
    statement_source?: string;
    [key: string]: unknown;
  };
  created_at: string;
}

export interface InsightCitation {
  evidence_link_id: string;
  stance: EvidenceStance;
  passage_id: string;
  quote: string;
  canonical_url: string;
  publisher: string;
  published_at: string | null;
  retrieved_at: string;
  document_hash: string;
  evidence_quality: number | null;
}

export interface InsightStatement {
  id: string;
  cluster_id: string | null;
  claim_id: string | null;
  text: string;
  label: ClusterLabel;
  confidence: number;
  display_order: number;
  citations: InsightCitation[];
}

export interface InsightReport {
  insight: Insight;
  statements: InsightStatement[];
}

export type BenchmarkDifficulty = "basic" | "intermediate" | "adversarial";
export type BenchmarkReviewState =
  | "pending"
  | "approved"
  | "changes_requested"
  | "rejected"
  | "stale";
export type BenchmarkReviewDecision = "approved" | "changes_requested" | "rejected";

export interface BenchmarkMention {
  passage_ordinal: number;
  surface_text: string;
  start_offset: number;
  end_offset: number;
  confidence: number;
}

export interface BenchmarkEntity {
  local_id: string;
  entity_type: string;
  canonical_name: string;
  aliases: string[];
  mentions: BenchmarkMention[];
}

export interface BenchmarkEvidence {
  passage_ordinal: number;
  stance: EvidenceStance;
  directness: number;
  extraction_confidence: number;
  rationale: string;
}

export interface BenchmarkClaim {
  subject_local_id: string | null;
  predicate: string;
  object_value: Record<string, unknown>;
  qualifiers: Record<string, unknown>;
  normalized_text: string;
  extraction_confidence: number;
  evidence: BenchmarkEvidence[];
}

export interface BenchmarkGoldCase {
  schema_version: "gold-case.v1";
  case_id: string;
  fixture_type: "synthetic" | "licensed" | "public_excerpt";
  excerpt_policy: "synthetic" | "licensed" | "short_public_excerpt";
  review_status: "synthetic" | "assistant_verified" | "human_verified";
  reviewer: string | null;
  reviewed_at: string | null;
  difficulty: BenchmarkDifficulty;
  task_tags: string[];
  document: {
    title: string;
    raw_content: string;
    source_url: string | null;
    publisher: string | null;
    source_type: string | null;
    retrieved_at: string | null;
    content_hash: string | null;
  };
  gold: {
    entities: BenchmarkEntity[];
    claims: BenchmarkClaim[];
  };
}

export interface BenchmarkReviewChecklist {
  source_url_opened: boolean;
  excerpt_matches_source: boolean;
  entities_and_claims_checked: boolean;
}

export interface BenchmarkReviewRecord {
  schema_version: "gold-review.v1";
  case_id: string;
  case_fingerprint: string;
  source_url: string;
  content_hash: string;
  reviewer_kind: "human";
  reviewer: string;
  reviewed_at: string;
  decision: BenchmarkReviewDecision;
  checklist: BenchmarkReviewChecklist;
  notes: string;
}

export interface BenchmarkReviewCase {
  case: BenchmarkGoldCase;
  case_fingerprint: string;
  state: BenchmarkReviewState;
  latest_review: BenchmarkReviewRecord | null;
}

export interface BenchmarkReviewQueue {
  summary: {
    total: number;
    pending: number;
    approved: number;
    changes_requested: number;
    rejected: number;
    stale: number;
  };
  cases: BenchmarkReviewCase[];
}

export interface BenchmarkReviewDecisionPayload {
  case_fingerprint: string;
  reviewer: string;
  decision: BenchmarkReviewDecision;
  checklist: BenchmarkReviewChecklist;
  notes: string;
}
