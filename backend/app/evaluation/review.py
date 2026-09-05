import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.domain.provenance import canonicalize_url, sha256_text
from app.evaluation.models import EvaluationModel, GoldCase

logger = logging.getLogger(__name__)

ReviewDecision = Literal["approved", "changes_requested", "rejected"]

RESERVED_NON_HUMAN_REVIEWERS = {
    "assistant",
    "automation",
    "chatgpt",
    "codex",
    "model",
}


class ReviewChecklist(EvaluationModel):
    source_url_opened: bool = False
    excerpt_matches_source: bool = False
    entities_and_claims_checked: bool = False

    @property
    def complete(self) -> bool:
        return all(
            (
                self.source_url_opened,
                self.excerpt_matches_source,
                self.entities_and_claims_checked,
            )
        )


class GoldReviewRecord(EvaluationModel):
    schema_version: Literal["gold-review.v1"] = "gold-review.v1"
    case_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    case_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_url: str
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reviewer_kind: Literal["human"] = "human"
    reviewer: str = Field(min_length=2, max_length=160)
    reviewed_at: AwareDatetime
    decision: ReviewDecision
    checklist: ReviewChecklist
    notes: str = Field(min_length=3, max_length=2_000)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return canonicalize_url(value)

    @field_validator("reviewer")
    @classmethod
    def reject_non_human_reviewer_labels(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized.casefold() in RESERVED_NON_HUMAN_REVIEWERS:
            raise ValueError("reviewer must identify the human who performed the review")
        return normalized

    @model_validator(mode="after")
    def validate_approval_attestation(self) -> "GoldReviewRecord":
        if self.decision == "approved" and not self.checklist.complete:
            raise ValueError("Approved reviews require every checklist item to be confirmed.")
        return self


def gold_case_fingerprint(case: GoldCase) -> str:
    payload = {
        "schema_version": case.schema_version,
        "case_id": case.case_id,
        "fixture_type": case.fixture_type,
        "excerpt_policy": case.excerpt_policy,
        "difficulty": case.difficulty,
        "task_tags": case.task_tags,
        "document": case.document.model_dump(mode="json"),
        "gold": case.gold.model_dump(mode="json"),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(serialized)


def create_review_record(
    case: GoldCase,
    *,
    reviewer: str,
    decision: ReviewDecision,
    checklist: ReviewChecklist,
    notes: str,
    reviewed_at: datetime | None = None,
) -> GoldReviewRecord:
    if case.fixture_type == "synthetic":
        raise ValueError("Synthetic cases cannot receive human source verification.")
    if case.document.source_url is None or case.document.content_hash is None:
        raise ValueError("The case is missing source metadata required for review.")
    return GoldReviewRecord(
        case_id=case.case_id,
        case_fingerprint=gold_case_fingerprint(case),
        source_url=case.document.source_url,
        content_hash=case.document.content_hash,
        reviewer=reviewer,
        reviewed_at=reviewed_at or datetime.now(UTC),
        decision=decision,
        checklist=checklist,
        notes=notes,
    )


def load_review_records(path: Path) -> list[GoldReviewRecord]:
    if not path.exists():
        return []
    records: list[GoldReviewRecord] = []
    previous_reviewed_at: datetime | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = GoldReviewRecord.model_validate_json(line)
        except ValueError as error:
            raise ValueError(f"Invalid review record at {path}:{line_number}: {error}") from error
        if previous_reviewed_at is not None and record.reviewed_at < previous_reviewed_at:
            raise ValueError(f"Review ledger is not chronological at {path}:{line_number}.")
        records.append(record)
        previous_reviewed_at = record.reviewed_at
    return records


def append_review_record(path: Path, record: GoldReviewRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_review_records(path)
    if existing and record.reviewed_at < existing[-1].reviewed_at:
        raise ValueError("Review records must be appended in chronological order.")
    serialized = record.model_dump_json() + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())
    logger.info(
        "evaluation_review_appended",
        extra={
            "case_id": record.case_id,
            "case_fingerprint": record.case_fingerprint,
            "decision": record.decision,
            "reviewer": record.reviewer,
        },
    )


def apply_latest_reviews(
    cases: list[GoldCase],
    records: list[GoldReviewRecord],
) -> list[GoldCase]:
    cases_by_id = {case.case_id: case for case in cases}
    if len(cases_by_id) != len(cases):
        raise ValueError("Gold case_id values must be unique before applying reviews.")

    latest_by_case_id: dict[str, GoldReviewRecord] = {}
    for record in records:
        if record.case_id not in cases_by_id:
            raise ValueError(f"Review record references unknown case {record.case_id}.")
        latest_by_case_id[record.case_id] = record

    reviewed_cases: list[GoldCase] = []
    for case in cases:
        record = latest_by_case_id.get(case.case_id)
        if record is None or record.decision != "approved":
            reviewed_cases.append(case)
            continue
        current_fingerprint = gold_case_fingerprint(case)
        if (
            record.case_fingerprint != current_fingerprint
            or record.source_url != case.document.source_url
            or record.content_hash != case.document.content_hash
        ):
            logger.warning(
                "evaluation_review_stale",
                extra={
                    "case_id": case.case_id,
                    "review_fingerprint": record.case_fingerprint,
                    "current_fingerprint": current_fingerprint,
                },
            )
            reviewed_cases.append(case)
            continue

        payload = case.model_dump(mode="json")
        payload["review_status"] = "human_verified"
        payload["reviewer"] = record.reviewer
        payload["reviewed_at"] = record.reviewed_at.isoformat()
        reviewed_cases.append(GoldCase.model_validate(payload))
        logger.info(
            "evaluation_case_human_verified",
            extra={"case_id": case.case_id, "reviewer": record.reviewer},
        )
    return reviewed_cases
