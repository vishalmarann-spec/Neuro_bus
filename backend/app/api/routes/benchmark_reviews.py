from collections import Counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, status

from app.api.schemas import (
    BenchmarkReviewCaseRead,
    BenchmarkReviewDecisionCreate,
    BenchmarkReviewQueueRead,
    BenchmarkReviewSummaryRead,
)
from app.services.evaluation_review import (
    BenchmarkReviewCase,
    BenchmarkReviewState,
    BenchmarkReviewWorkspace,
    BenchmarkReviewWorkspaceError,
)

router = APIRouter(prefix="/benchmark-reviews", tags=["benchmark-human-review"])
CaseID = Annotated[str, Path(pattern=r"^[a-z0-9_-]+$")]


def get_workspace(request: Request) -> BenchmarkReviewWorkspace:
    workspace = request.app.state.benchmark_review_workspace
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "REVIEW_WORKSPACE_DISABLED",
                "message": "Benchmark review writes are available only in local development.",
            },
        )
    return workspace


def render_case(snapshot: BenchmarkReviewCase) -> BenchmarkReviewCaseRead:
    return BenchmarkReviewCaseRead(
        case=snapshot.case,
        case_fingerprint=snapshot.case_fingerprint,
        state=snapshot.state,
        latest_review=snapshot.latest_review,
    )


def workspace_error(error: BenchmarkReviewWorkspaceError) -> HTTPException:
    status_code = {
        "REVIEW_CASE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "REVIEW_CASE_STALE": status.HTTP_409_CONFLICT,
        "REVIEW_LEDGER_WRITE_FAILED": status.HTTP_503_SERVICE_UNAVAILABLE,
        "REVIEW_WORKSPACE_DATA_INVALID": status.HTTP_503_SERVICE_UNAVAILABLE,
    }.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    )


@router.get("/cases", response_model=BenchmarkReviewQueueRead)
def list_benchmark_review_cases(
    request: Request,
    review_state: Annotated[BenchmarkReviewState | None, Query(alias="state")] = None,
) -> BenchmarkReviewQueueRead:
    workspace = get_workspace(request)
    try:
        all_cases = workspace.list_cases()
    except BenchmarkReviewWorkspaceError as error:
        raise workspace_error(error) from error
    counts = Counter(snapshot.state for snapshot in all_cases)
    selected = (
        all_cases
        if review_state is None
        else [snapshot for snapshot in all_cases if snapshot.state == review_state]
    )
    return BenchmarkReviewQueueRead(
        summary=BenchmarkReviewSummaryRead(
            total=len(all_cases),
            pending=counts[BenchmarkReviewState.PENDING],
            approved=counts[BenchmarkReviewState.APPROVED],
            changes_requested=counts[BenchmarkReviewState.CHANGES_REQUESTED],
            rejected=counts[BenchmarkReviewState.REJECTED],
            stale=counts[BenchmarkReviewState.STALE],
        ),
        cases=[render_case(snapshot) for snapshot in selected],
    )


@router.get("/cases/{case_id}", response_model=BenchmarkReviewCaseRead)
def read_benchmark_review_case(
    case_id: CaseID,
    request: Request,
) -> BenchmarkReviewCaseRead:
    try:
        return render_case(get_workspace(request).get_case(case_id))
    except BenchmarkReviewWorkspaceError as error:
        raise workspace_error(error) from error


@router.post(
    "/cases/{case_id}/decisions",
    response_model=BenchmarkReviewCaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_benchmark_review_decision(
    case_id: CaseID,
    payload: BenchmarkReviewDecisionCreate,
    request: Request,
) -> BenchmarkReviewCaseRead:
    try:
        snapshot = get_workspace(request).submit_decision(
            case_id=case_id,
            expected_fingerprint=payload.case_fingerprint,
            reviewer=payload.reviewer,
            decision=payload.decision,
            checklist=payload.checklist,
            notes=payload.notes,
        )
    except BenchmarkReviewWorkspaceError as error:
        raise workspace_error(error) from error
    return render_case(snapshot)
