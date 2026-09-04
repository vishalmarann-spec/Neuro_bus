from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path

from app.api.routes.storage import not_found
from app.api.schemas import ClaimClusterScoreRead, ReasoningRunRead
from app.core.database import DatabaseSession
from app.services.reasoning import (
    ReasoningRecord,
    load_reasoning_records,
    reason_over_run,
)
from app.services.storage import get_run

router = APIRouter(tags=["multi-source-reasoning"])
ResourceID = Annotated[UUID, Path()]


def render_record(record: ReasoningRecord) -> ClaimClusterScoreRead:
    return ClaimClusterScoreRead(
        cluster_id=record.cluster.id,
        canonical_text=record.cluster.canonical_text,
        predicate=record.cluster.predicate,
        support_strength=record.score.support_strength,
        contradiction_strength=record.score.contradiction_strength,
        confidence=record.score.confidence,
        label=record.score.label,
        supporting_independent_sources=record.score.supporting_independent_sources,
        evidence_count=record.score.evidence_count,
        scoring_version=record.score.scoring_version,
        explanation=record.score.explanation,
        calculated_at=record.score.calculated_at,
    )


@router.post("/runs/{run_id}/reason", response_model=ReasoningRunRead)
async def reason_run(run_id: ResourceID, session: DatabaseSession) -> ReasoningRunRead:
    if await get_run(session, run_id) is None:
        raise not_found("Analysis run")
    records = await reason_over_run(session, run_id)
    return ReasoningRunRead(run_id=run_id, clusters=[render_record(item) for item in records])


@router.get("/runs/{run_id}/clusters", response_model=list[ClaimClusterScoreRead])
async def read_clusters(
    run_id: ResourceID,
    session: DatabaseSession,
) -> list[ClaimClusterScoreRead]:
    if await get_run(session, run_id) is None:
        raise not_found("Analysis run")
    return [render_record(item) for item in await load_reasoning_records(session, run_id)]


@router.get("/runs/{run_id}/conflicts", response_model=list[ClaimClusterScoreRead])
async def read_conflicts(
    run_id: ResourceID,
    session: DatabaseSession,
) -> list[ClaimClusterScoreRead]:
    if await get_run(session, run_id) is None:
        raise not_found("Analysis run")
    records = await load_reasoning_records(session, run_id, disputed_only=True)
    return [render_record(item) for item in records]
