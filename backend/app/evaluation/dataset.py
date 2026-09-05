import hashlib
import logging
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.evaluation.coverage import (
    MINIMUM_SELECTION_CASES,
    BenchmarkCoverageReport,
    summarize_benchmark_coverage,
)
from app.evaluation.models import EvaluationModel, GoldCase
from app.evaluation.review import GoldReviewRecord, apply_latest_reviews, gold_case_fingerprint

logger = logging.getLogger(__name__)

class DatasetSplit(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    HOLDOUT = "holdout"


class SplitAssignment(EvaluationModel):
    case_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    case_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    split: DatasetSplit


class SelectionDatasetManifest(EvaluationModel):
    schema_version: Literal["selection-dataset.v1"] = "selection-dataset.v1"
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    created_at: AwareDatetime
    seed: str = Field(min_length=3, max_length=160)
    minimum_cases: int = MINIMUM_SELECTION_CASES
    case_count: int = Field(ge=MINIMUM_SELECTION_CASES)
    split_counts: dict[DatasetSplit, int]
    coverage: BenchmarkCoverageReport
    assignments: list[SplitAssignment]

    @model_validator(mode="after")
    def validate_manifest_counts(self) -> "SelectionDatasetManifest":
        if self.minimum_cases != MINIMUM_SELECTION_CASES:
            raise ValueError(f"minimum_cases must remain {MINIMUM_SELECTION_CASES}")
        if len(self.assignments) != self.case_count:
            raise ValueError("case_count must equal the number of assignments.")
        if len({assignment.case_id for assignment in self.assignments}) != self.case_count:
            raise ValueError("Manifest case_id values must be unique.")
        actual_counts = Counter(assignment.split for assignment in self.assignments)
        expected_counts = {split: actual_counts[split] for split in DatasetSplit}
        if self.split_counts != expected_counts:
            raise ValueError("split_counts do not match the assignments.")
        if any(expected_counts[split] == 0 for split in DatasetSplit):
            raise ValueError("Every dataset split must contain at least one case.")
        if not self.coverage.selection_ready:
            raise ValueError("Selection manifest coverage must pass every coverage gate.")
        if self.coverage.case_count != self.case_count:
            raise ValueError("Selection manifest coverage case_count must match the manifest.")
        return self


def deterministic_split_assignments(
    cases: list[GoldCase],
    *,
    seed: str,
) -> list[SplitAssignment]:
    if len(seed.strip()) < 3:
        raise ValueError("Split seed must contain at least three non-whitespace characters.")
    if len(cases) < 5:
        raise ValueError("At least five cases are required to create three useful splits.")
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Gold case_id values must be unique before splitting.")

    ordered = sorted(
        cases,
        key=lambda case: (
            hashlib.sha256(f"{seed}:{case.case_id}".encode()).hexdigest(),
            case.case_id,
        ),
    )
    development_end = int(len(ordered) * 0.60)
    validation_end = development_end + int(len(ordered) * 0.20)
    assignments: list[SplitAssignment] = []
    for index, case in enumerate(ordered):
        if index < development_end:
            split = DatasetSplit.DEVELOPMENT
        elif index < validation_end:
            split = DatasetSplit.VALIDATION
        else:
            split = DatasetSplit.HOLDOUT
        assignments.append(
            SplitAssignment(
                case_id=case.case_id,
                case_fingerprint=gold_case_fingerprint(case),
                split=split,
            )
        )
    return assignments


def build_selection_manifest(
    cases: list[GoldCase],
    review_records: list[GoldReviewRecord],
    *,
    dataset_id: str,
    seed: str,
    created_at: datetime | None = None,
) -> SelectionDatasetManifest:
    if len(cases) < MINIMUM_SELECTION_CASES:
        raise ValueError(
            f"Selection datasets require at least {MINIMUM_SELECTION_CASES} cases; "
            f"received {len(cases)}."
        )
    synthetic = [case.case_id for case in cases if case.fixture_type == "synthetic"]
    if synthetic:
        raise ValueError("Selection datasets cannot contain synthetic cases.")
    reviewed_cases = apply_latest_reviews(cases, review_records)
    latest_by_case_id = {record.case_id: record for record in review_records}
    unverified = []
    for case in cases:
        record = latest_by_case_id.get(case.case_id)
        if (
            record is None
            or record.decision != "approved"
            or record.case_fingerprint != gold_case_fingerprint(case)
            or record.source_url != case.document.source_url
            or record.content_hash != case.document.content_hash
        ):
            unverified.append(case.case_id)
    if unverified:
        preview = ", ".join(unverified[:5])
        suffix = "..." if len(unverified) > 5 else ""
        raise ValueError(f"Selection datasets require human verification: {preview}{suffix}")

    coverage = summarize_benchmark_coverage(reviewed_cases)
    if not coverage.selection_ready:
        raise ValueError(
            "Selection dataset coverage requirements not met: " + "; ".join(coverage.failures)
        )

    assignments = deterministic_split_assignments(reviewed_cases, seed=seed)
    counts = Counter(assignment.split for assignment in assignments)
    manifest = SelectionDatasetManifest(
        dataset_id=dataset_id,
        created_at=created_at or datetime.now(UTC),
        seed=seed,
        case_count=len(cases),
        split_counts={split: counts[split] for split in DatasetSplit},
        coverage=coverage,
        assignments=assignments,
    )
    logger.info(
        "evaluation_selection_manifest_created",
        extra={
            "dataset_id": dataset_id,
            "case_count": len(cases),
            "development_count": counts[DatasetSplit.DEVELOPMENT],
            "validation_count": counts[DatasetSplit.VALIDATION],
            "holdout_count": counts[DatasetSplit.HOLDOUT],
        },
    )
    return manifest
