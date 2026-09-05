import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock

from app.evaluation.io import load_gold_case_files
from app.evaluation.models import GoldCase
from app.evaluation.review import (
    GoldReviewRecord,
    ReviewChecklist,
    ReviewDecision,
    append_review_record,
    create_review_record,
    gold_case_fingerprint,
    load_review_records,
)

logger = logging.getLogger(__name__)


class BenchmarkReviewState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    STALE = "stale"


class BenchmarkReviewWorkspaceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BenchmarkReviewCase:
    case: GoldCase
    case_fingerprint: str
    state: BenchmarkReviewState
    latest_review: GoldReviewRecord | None


class BenchmarkReviewWorkspace:
    def __init__(self, *, gold_paths: list[Path], ledger_path: Path) -> None:
        if not gold_paths:
            raise ValueError("At least one gold path is required for benchmark review.")
        self.gold_paths = gold_paths
        self.ledger_path = ledger_path
        self._write_lock = Lock()

    def _load(self) -> tuple[list[GoldCase], list[GoldReviewRecord]]:
        try:
            cases = load_gold_case_files(self.gold_paths)
            records = load_review_records(self.ledger_path)
        except (OSError, ValueError) as error:
            raise BenchmarkReviewWorkspaceError(
                "REVIEW_WORKSPACE_DATA_INVALID",
                f"Benchmark review data could not be loaded: {error}",
            ) from error
        known_case_ids = {case.case_id for case in cases}
        unknown = sorted({record.case_id for record in records} - known_case_ids)
        if unknown:
            raise BenchmarkReviewWorkspaceError(
                "REVIEW_WORKSPACE_DATA_INVALID",
                "Review ledger references unknown cases: " + ", ".join(unknown[:5]),
            )
        return cases, records

    @staticmethod
    def _snapshot(
        case: GoldCase,
        latest_review: GoldReviewRecord | None,
    ) -> BenchmarkReviewCase:
        fingerprint = gold_case_fingerprint(case)
        if latest_review is None:
            state = BenchmarkReviewState.PENDING
        elif (
            latest_review.case_fingerprint != fingerprint
            or latest_review.source_url != case.document.source_url
            or latest_review.content_hash != case.document.content_hash
        ):
            state = BenchmarkReviewState.STALE
        else:
            state = BenchmarkReviewState(latest_review.decision)
        return BenchmarkReviewCase(
            case=case,
            case_fingerprint=fingerprint,
            state=state,
            latest_review=latest_review,
        )

    def list_cases(
        self,
        *,
        state: BenchmarkReviewState | None = None,
    ) -> list[BenchmarkReviewCase]:
        cases, records = self._load()
        latest_by_case_id = {record.case_id: record for record in records}
        snapshots = [self._snapshot(case, latest_by_case_id.get(case.case_id)) for case in cases]
        if state is not None:
            snapshots = [snapshot for snapshot in snapshots if snapshot.state == state]
        return snapshots

    def get_case(self, case_id: str) -> BenchmarkReviewCase:
        snapshots = self.list_cases()
        for snapshot in snapshots:
            if snapshot.case.case_id == case_id:
                return snapshot
        raise BenchmarkReviewWorkspaceError(
            "REVIEW_CASE_NOT_FOUND",
            f"Benchmark review case {case_id} was not found.",
        )

    def submit_decision(
        self,
        *,
        case_id: str,
        expected_fingerprint: str,
        reviewer: str,
        decision: ReviewDecision,
        checklist: ReviewChecklist,
        notes: str,
    ) -> BenchmarkReviewCase:
        with self._write_lock:
            current = self.get_case(case_id)
            if current.case_fingerprint != expected_fingerprint:
                raise BenchmarkReviewWorkspaceError(
                    "REVIEW_CASE_STALE",
                    "The benchmark case changed after it was loaded. Refresh before reviewing.",
                )
            record = create_review_record(
                current.case,
                reviewer=reviewer,
                decision=decision,
                checklist=checklist,
                notes=notes,
            )
            try:
                append_review_record(self.ledger_path, record)
            except (OSError, ValueError) as error:
                raise BenchmarkReviewWorkspaceError(
                    "REVIEW_LEDGER_WRITE_FAILED",
                    f"The review decision could not be appended: {error}",
                ) from error
            logger.info(
                "benchmark_review_decision_submitted",
                extra={
                    "case_id": case_id,
                    "case_fingerprint": current.case_fingerprint,
                    "decision": decision,
                    "reviewer": reviewer,
                },
            )
            return self._snapshot(current.case, record)


def default_benchmark_review_workspace() -> BenchmarkReviewWorkspace:
    backend_root = Path(__file__).resolve().parents[2]
    return BenchmarkReviewWorkspace(
        gold_paths=[
            backend_root / "evaluation" / "gold" / "public_pilot_v1.json",
            backend_root / "evaluation" / "gold" / "public_batch_2_v1.json",
            backend_root / "evaluation" / "gold" / "public_batch_3_v1.json",
        ],
        ledger_path=backend_root / "evaluation" / "reviews" / "public_corpus_v1.jsonl",
    )
