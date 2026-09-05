from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.dataset import (
    DatasetSplit,
    build_selection_manifest,
    deterministic_split_assignments,
)
from app.evaluation.io import load_gold_case_files, load_gold_cases
from app.evaluation.models import GoldCase
from app.evaluation.review import (
    GoldReviewRecord,
    ReviewChecklist,
    ReviewDecision,
    append_review_record,
    apply_latest_reviews,
    create_review_record,
    gold_case_fingerprint,
    load_review_records,
)

PUBLIC_PILOT_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "public_pilot_v1.json"
PUBLIC_BATCH_2_PATH = (
    Path(__file__).parents[1] / "evaluation" / "gold" / "public_batch_2_v1.json"
)
REVIEWED_AT = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)


def complete_checklist() -> ReviewChecklist:
    return ReviewChecklist(
        source_url_opened=True,
        excerpt_matches_source=True,
        entities_and_claims_checked=True,
    )


def review_record(
    case: GoldCase,
    *,
    decision: ReviewDecision = "approved",
    reviewed_at: datetime = REVIEWED_AT,
) -> GoldReviewRecord:
    return create_review_record(
        case,
        reviewer="Vishal Maran",
        decision=decision,
        checklist=complete_checklist(),
        notes="Compared the official page, excerpt, entities, claims, and evidence offsets.",
        reviewed_at=reviewed_at,
    )


def reviewable_cases(count: int) -> list[GoldCase]:
    bases = load_gold_case_files([PUBLIC_PILOT_PATH, PUBLIC_BATCH_2_PATH])
    cases = []
    for index in range(count):
        payload = bases[index % len(bases)].model_dump(mode="json")
        payload["case_id"] = f"reviewed_case_{index:03d}"
        cases.append(GoldCase.model_validate(payload))
    return cases


def approved_case_records(cases: list[GoldCase]) -> list[GoldReviewRecord]:
    return [
        review_record(case, reviewed_at=REVIEWED_AT + timedelta(seconds=index))
        for index, case in enumerate(cases)
    ]


def test_approved_review_requires_complete_human_attestation() -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]

    with pytest.raises(ValidationError, match="every checklist item"):
        create_review_record(
            case,
            reviewer="Vishal Maran",
            decision="approved",
            checklist=ReviewChecklist(source_url_opened=True),
            notes="The review is not complete yet.",
            reviewed_at=REVIEWED_AT,
        )

    with pytest.raises(ValidationError, match="identify the human"):
        create_review_record(
            case,
            reviewer="codex",
            decision="approved",
            checklist=complete_checklist(),
            notes="This must not be accepted as human review.",
            reviewed_at=REVIEWED_AT,
        )


def test_review_ledger_is_append_only_and_promotes_exact_case(tmp_path: Path) -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]
    record = review_record(case)
    ledger = tmp_path / "reviews.jsonl"

    append_review_record(ledger, record)
    loaded = load_review_records(ledger)
    promoted = apply_latest_reviews([case], loaded)[0]

    assert loaded == [record]
    assert promoted.review_status == "human_verified"
    assert promoted.reviewer == "Vishal Maran"
    assert promoted.reviewed_at == REVIEWED_AT


def test_review_ledger_rejects_out_of_order_append(tmp_path: Path) -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]
    ledger = tmp_path / "reviews.jsonl"
    later = review_record(case, reviewed_at=REVIEWED_AT + timedelta(minutes=5))
    earlier = review_record(case, reviewed_at=REVIEWED_AT)

    append_review_record(ledger, later)
    with pytest.raises(ValueError, match="chronological order"):
        append_review_record(ledger, earlier)

    assert load_review_records(ledger) == [later]


def test_stale_review_does_not_promote_changed_gold_case() -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]
    record = review_record(case)
    payload = case.model_dump(mode="json")
    payload["gold"]["claims"][0]["normalized_text"] = (
        "The reviewed claim was intentionally changed after approval."
    )
    changed_case = GoldCase.model_validate(payload)

    result = apply_latest_reviews([changed_case], [record])[0]

    assert gold_case_fingerprint(changed_case) != record.case_fingerprint
    assert result.review_status == "assistant_verified"


def test_coverage_label_change_invalidates_review_fingerprint() -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]
    original_fingerprint = gold_case_fingerprint(case)
    payload = case.model_dump(mode="json")
    payload["difficulty"] = "adversarial"
    changed_case = GoldCase.model_validate(payload)

    assert gold_case_fingerprint(changed_case) != original_fingerprint


def test_latest_non_approval_revokes_promotion() -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]
    approved = review_record(case)
    rejected = review_record(
        case,
        decision="rejected",
        reviewed_at=REVIEWED_AT + timedelta(minutes=5),
    )

    result = apply_latest_reviews([case], [approved, rejected])[0]

    assert result.review_status == "assistant_verified"


def test_review_record_for_unknown_case_fails_closed() -> None:
    case = load_gold_cases(PUBLIC_PILOT_PATH)[0]
    payload = review_record(case).model_dump(mode="json")
    payload["case_id"] = "unknown_case"
    unknown = GoldReviewRecord.model_validate(payload)

    with pytest.raises(ValueError, match="unknown case"):
        apply_latest_reviews([case], [unknown])


def test_split_assignments_are_deterministic_and_non_overlapping() -> None:
    cases = reviewable_cases(100)

    with pytest.raises(ValueError, match="Split seed"):
        deterministic_split_assignments(cases, seed=" ")

    first = deterministic_split_assignments(cases, seed="neuro-bus-selection-v1")
    second = deterministic_split_assignments(list(reversed(cases)), seed="neuro-bus-selection-v1")

    assert first == second
    assert len({assignment.case_id for assignment in first}) == 100
    assert sum(assignment.split == DatasetSplit.DEVELOPMENT for assignment in first) == 60
    assert sum(assignment.split == DatasetSplit.VALIDATION for assignment in first) == 20
    assert sum(assignment.split == DatasetSplit.HOLDOUT for assignment in first) == 20


def test_selection_manifest_requires_100_human_verified_cases() -> None:
    pilot = load_gold_cases(PUBLIC_PILOT_PATH)

    with pytest.raises(ValueError, match="at least 100"):
        build_selection_manifest(
            pilot,
            [],
            dataset_id="university-selection-v1",
            seed="neuro-bus-selection-v1",
            created_at=REVIEWED_AT,
        )

    manually_labelled_cases = []
    for case in reviewable_cases(100):
        payload = case.model_dump(mode="json")
        payload["review_status"] = "human_verified"
        payload["reviewer"] = "Unverified Manual Label"
        payload["reviewed_at"] = REVIEWED_AT.isoformat()
        manually_labelled_cases.append(GoldCase.model_validate(payload))
    with pytest.raises(ValueError, match="human verification"):
        build_selection_manifest(
            manually_labelled_cases,
            [],
            dataset_id="university-selection-v1",
            seed="neuro-bus-selection-v1",
            created_at=REVIEWED_AT,
        )


def test_selection_manifest_locks_case_fingerprints_and_split_counts() -> None:
    cases = reviewable_cases(100)
    manifest = build_selection_manifest(
        cases,
        approved_case_records(cases),
        dataset_id="university-selection-v1",
        seed="neuro-bus-selection-v1",
        created_at=REVIEWED_AT,
    )

    assert manifest.case_count == 100
    assert manifest.split_counts == {
        DatasetSplit.DEVELOPMENT: 60,
        DatasetSplit.VALIDATION: 20,
        DatasetSplit.HOLDOUT: 20,
    }
    assert all(item.case_fingerprint.startswith("sha256:") for item in manifest.assignments)
    assert manifest.coverage.selection_ready
    assert manifest.coverage.negative_case_count == 10
