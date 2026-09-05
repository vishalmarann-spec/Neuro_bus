import re
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.models import SourceType
from app.domain.extraction import ExtractionEnvelope, validate_provenance
from app.domain.provenance import canonicalize_url, segment_passages, sha256_text


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BenchmarkDifficulty(StrEnum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVERSARIAL = "adversarial"


class BenchmarkTaskTag(StrEnum):
    ADMISSIONS = "admissions"
    ACCREDITATION = "accreditation"
    CURRICULUM = "curriculum"
    PROGRAMME_STATUS = "programme_status"
    FEE = "fee"
    DURATION = "duration"
    LEARNING_OUTCOME = "learning_outcome"
    LABOUR_MARKET = "labour_market"
    SKILLS_DEMAND = "skills_demand"
    PUBLIC_INITIATIVE = "public_initiative"
    EDUCATION_TREND = "education_trend"
    EMPLOYER_DEMAND = "employer_demand"
    METHODOLOGY_CAVEAT = "methodology_caveat"
    RESEARCH_TREND = "research_trend"
    NEGATIVE_NO_CLAIM = "negative_no_claim"


class BenchmarkDocument(EvaluationModel):
    title: str
    raw_content: str = Field(min_length=1)
    source_url: str | None = None
    publisher: str | None = Field(default=None, min_length=1, max_length=255)
    source_type: SourceType | None = None
    retrieved_at: AwareDatetime | None = None
    content_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @field_validator("source_url")
    @classmethod
    def validate_and_canonicalize_source_url(cls, value: str | None) -> str | None:
        return canonicalize_url(value) if value is not None else None


class GoldCase(EvaluationModel):
    schema_version: Literal["gold-case.v1"] = "gold-case.v1"
    case_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    fixture_type: Literal["synthetic", "licensed", "public_excerpt"]
    excerpt_policy: Literal["synthetic", "licensed", "short_public_excerpt"] = "synthetic"
    review_status: Literal["synthetic", "assistant_verified", "human_verified"] = "synthetic"
    reviewer: str | None = Field(default=None, min_length=1, max_length=160)
    reviewed_at: AwareDatetime | None = None
    difficulty: BenchmarkDifficulty = BenchmarkDifficulty.BASIC
    task_tags: list[BenchmarkTaskTag] = Field(default_factory=list, max_length=4)
    document: BenchmarkDocument
    gold: ExtractionEnvelope

    @model_validator(mode="after")
    def validate_fixture_integrity(self) -> "GoldCase":
        if self.fixture_type == "synthetic":
            if self.document.source_url is not None:
                raise ValueError("Synthetic cases must not contain a source URL.")
            if self.excerpt_policy != "synthetic" or self.review_status != "synthetic":
                raise ValueError("Synthetic cases must retain synthetic policy labels.")
        else:
            if not self.task_tags:
                raise ValueError("Non-synthetic cases require at least one benchmark task tag.")
            required_metadata = {
                "source_url": self.document.source_url,
                "publisher": self.document.publisher,
                "source_type": self.document.source_type,
                "retrieved_at": self.document.retrieved_at,
                "content_hash": self.document.content_hash,
                "reviewer": self.reviewer,
                "reviewed_at": self.reviewed_at,
            }
            missing = [name for name, value in required_metadata.items() if value is None]
            if missing:
                raise ValueError(
                    "Non-synthetic cases require verified metadata: " + ", ".join(missing)
                )
            if self.document.content_hash != sha256_text(self.document.raw_content):
                raise ValueError("Document content_hash does not match raw_content.")
            if self.review_status == "synthetic":
                raise ValueError("Non-synthetic cases require an explicit review status.")

        if self.fixture_type == "public_excerpt":
            if self.excerpt_policy != "short_public_excerpt":
                raise ValueError("Public excerpts require the short_public_excerpt policy.")
            if len(re.findall(r"\S+", self.document.raw_content)) > 25:
                raise ValueError("Public benchmark excerpts may contain at most 25 words.")
        elif self.fixture_type == "licensed" and self.excerpt_policy != "licensed":
            raise ValueError("Licensed fixtures require the licensed excerpt policy.")

        if len(set(self.task_tags)) != len(self.task_tags):
            raise ValueError("Benchmark task tags must be unique within a case.")
        is_negative = BenchmarkTaskTag.NEGATIVE_NO_CLAIM in self.task_tags
        if is_negative and self.gold.claims:
            raise ValueError("negative_no_claim cases must not contain gold claims.")
        if not self.gold.claims and self.fixture_type != "synthetic" and not is_negative:
            raise ValueError("Non-synthetic cases without claims require negative_no_claim.")

        provenance_errors = validate_provenance(
            self.gold,
            segment_passages(self.document.raw_content),
        )
        if provenance_errors:
            raise ValueError("Gold provenance is invalid: " + " ".join(provenance_errors))
        return self


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
