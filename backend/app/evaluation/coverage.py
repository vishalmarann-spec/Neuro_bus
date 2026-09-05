import math
from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from app.domain.provenance import canonical_domain
from app.evaluation.models import (
    BenchmarkDifficulty,
    BenchmarkTaskTag,
    EvaluationModel,
    GoldCase,
)

MINIMUM_SELECTION_CASES = 100
MINIMUM_SOURCE_TYPES = 3
MINIMUM_TASK_TAGS = 6
MINIMUM_PUBLISHERS = 10
MINIMUM_NEGATIVE_SHARE = 0.10
MINIMUM_ADVERSARIAL_SHARE = 0.10


class BenchmarkCoverageReport(EvaluationModel):
    schema_version: Literal["benchmark-coverage.v1"] = "benchmark-coverage.v1"
    case_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    publisher_count: int = Field(ge=0)
    domain_count: int = Field(ge=0)
    source_type_counts: dict[str, int]
    task_tag_counts: dict[str, int]
    difficulty_counts: dict[str, int]
    review_status_counts: dict[str, int]
    negative_case_count: int = Field(ge=0)
    adversarial_case_count: int = Field(ge=0)
    required_negative_cases: int = Field(ge=1)
    required_adversarial_cases: int = Field(ge=1)
    selection_ready: bool
    failures: list[str]

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> "BenchmarkCoverageReport":
        count_maps = (
            self.source_type_counts,
            self.task_tag_counts,
            self.difficulty_counts,
            self.review_status_counts,
        )
        if any(value < 0 for counts in count_maps for value in counts.values()):
            raise ValueError("Coverage count maps cannot contain negative values.")
        if sum(self.difficulty_counts.values()) != self.case_count:
            raise ValueError("Difficulty counts must sum to case_count.")
        if sum(self.review_status_counts.values()) != self.case_count:
            raise ValueError("Review-status counts must sum to case_count.")
        if self.selection_ready != (not self.failures):
            raise ValueError("selection_ready must agree with the failure list.")
        return self


def selection_coverage_failures(cases: list[GoldCase]) -> list[str]:
    case_count = len(cases)
    source_types = {case.document.source_type for case in cases if case.document.source_type}
    task_tags = {tag for case in cases for tag in case.task_tags}
    publishers = {case.document.publisher for case in cases if case.document.publisher}
    negative_count = sum(BenchmarkTaskTag.NEGATIVE_NO_CLAIM in case.task_tags for case in cases)
    adversarial_count = sum(case.difficulty == BenchmarkDifficulty.ADVERSARIAL for case in cases)
    required_negative = max(
        1,
        math.ceil(case_count * MINIMUM_NEGATIVE_SHARE),
    )
    required_adversarial = max(
        1,
        math.ceil(case_count * MINIMUM_ADVERSARIAL_SHARE),
    )

    failures: list[str] = []
    if case_count < MINIMUM_SELECTION_CASES:
        failures.append(
            f"at least {MINIMUM_SELECTION_CASES} cases are required; received {case_count}"
        )
    if len(source_types) < MINIMUM_SOURCE_TYPES:
        failures.append(
            f"at least {MINIMUM_SOURCE_TYPES} source types are required; received "
            f"{len(source_types)}"
        )
    if len(task_tags) < MINIMUM_TASK_TAGS:
        failures.append(
            f"at least {MINIMUM_TASK_TAGS} task tags are required; received {len(task_tags)}"
        )
    if len(publishers) < MINIMUM_PUBLISHERS:
        failures.append(
            f"at least {MINIMUM_PUBLISHERS} publishers are required; received {len(publishers)}"
        )
    if negative_count < required_negative:
        failures.append(
            f"at least {required_negative} negative_no_claim cases are required; "
            f"received {negative_count}"
        )
    if adversarial_count < required_adversarial:
        failures.append(
            f"at least {required_adversarial} adversarial cases are required; "
            f"received {adversarial_count}"
        )
    return failures


def summarize_benchmark_coverage(cases: list[GoldCase]) -> BenchmarkCoverageReport:
    failures = selection_coverage_failures(cases)
    case_count = len(cases)
    negative_count = sum(BenchmarkTaskTag.NEGATIVE_NO_CLAIM in case.task_tags for case in cases)
    adversarial_count = sum(case.difficulty == BenchmarkDifficulty.ADVERSARIAL for case in cases)
    required_negative = max(1, math.ceil(case_count * MINIMUM_NEGATIVE_SHARE))
    required_adversarial = max(1, math.ceil(case_count * MINIMUM_ADVERSARIAL_SHARE))

    source_type_counts = Counter(
        case.document.source_type.value for case in cases if case.document.source_type is not None
    )
    task_tag_counts = Counter(tag.value for case in cases for tag in case.task_tags)
    difficulty_counts = Counter(case.difficulty.value for case in cases)
    review_status_counts = Counter(case.review_status for case in cases)
    publishers = {case.document.publisher for case in cases if case.document.publisher}
    domains = {
        canonical_domain(case.document.source_url)
        for case in cases
        if case.document.source_url is not None
    }

    return BenchmarkCoverageReport(
        case_count=case_count,
        claim_count=sum(len(case.gold.claims) for case in cases),
        publisher_count=len(publishers),
        domain_count=len(domains),
        source_type_counts=dict(sorted(source_type_counts.items())),
        task_tag_counts=dict(sorted(task_tag_counts.items())),
        difficulty_counts=dict(sorted(difficulty_counts.items())),
        review_status_counts=dict(sorted(review_status_counts.items())),
        negative_case_count=negative_count,
        adversarial_case_count=adversarial_count,
        required_negative_cases=required_negative,
        required_adversarial_cases=required_adversarial,
        selection_ready=not failures,
        failures=failures,
    )
