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
