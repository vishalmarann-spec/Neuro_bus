from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.extraction import ExtractionEnvelope


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BenchmarkDocument(EvaluationModel):
    title: str
    raw_content: str = Field(min_length=1)
    source_url: str | None = None


class GoldCase(EvaluationModel):
    case_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    fixture_type: Literal["synthetic", "licensed", "public_excerpt"]
    document: BenchmarkDocument
    gold: ExtractionEnvelope


class ModelPrediction(EvaluationModel):
    case_id: str
    model_id: str
    raw_output: str
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class PRFScore(EvaluationModel):
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int


class ModelScorecard(EvaluationModel):
    model_id: str
    cases_total: int
    cases_with_prediction: int
    schema_and_provenance_valid_rate: float
    entity: PRFScore
    mention: PRFScore
    claim: PRFScore
    evidence_link: PRFScore
    citation_correctness: float
    false_claim_rate: float
    average_latency_ms: float | None
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_cost_usd: float | None
