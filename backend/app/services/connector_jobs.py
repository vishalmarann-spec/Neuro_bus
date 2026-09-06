import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import WebSourceFetchCreate
from app.core.models import AnalysisRun, ConnectorJob, ConnectorJobStatus, RunState
from app.domain.provenance import sha256_text
from app.services.web_connector import WebConnectorOutcome


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different connector request."""


def connector_request_hash(payload: WebSourceFetchCreate) -> str:
    serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return sha256_text(serialized)


async def create_connector_job(
    session: AsyncSession,
    run: AnalysisRun,
    payload: WebSourceFetchCreate,
    max_attempts: int,
    idempotency_key: str | None = None,
) -> tuple[ConnectorJob, bool]:
    request_hash = connector_request_hash(payload)
    idempotency_hash = sha256_text(idempotency_key) if idempotency_key is not None else None

    if idempotency_hash is not None:
        existing = await _find_idempotent_job(session, run.id, idempotency_hash)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyConflict
            return existing, True

    job = ConnectorJob(
        run_id=run.id,
        requested_url=str(payload.url),
        publisher=payload.publisher,
        publisher_family=payload.publisher_family,
        source_type=payload.source_type,
        title=payload.title,
        published_at=payload.published_at,
        request_hash=request_hash,
        idempotency_hash=idempotency_hash,
        max_attempts=max_attempts,
        status=ConnectorJobStatus.QUEUED,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if idempotency_hash is None:
            raise
        existing = await _find_idempotent_job(session, run.id, idempotency_hash)
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            raise IdempotencyConflict from None
        return existing, True
    await session.refresh(job)
    return job, False


async def _find_idempotent_job(
    session: AsyncSession, run_id: UUID, idempotency_hash: str
) -> ConnectorJob | None:
    result = await session.execute(
        select(ConnectorJob).where(
            ConnectorJob.run_id == run_id,
            ConnectorJob.connector == "public_web.v1",
            ConnectorJob.idempotency_hash == idempotency_hash,
        )
    )
    return result.scalar_one_or_none()


def _claimable(now: datetime):
    return or_(
        and_(
            ConnectorJob.status == ConnectorJobStatus.QUEUED,
            ConnectorJob.available_at <= now,
        ),
        and_(
            ConnectorJob.status == ConnectorJobStatus.RUNNING,
            ConnectorJob.lease_expires_at.is_not(None),
            ConnectorJob.lease_expires_at <= now,
        ),
    )


async def claim_connector_job(
    session: AsyncSession,
    worker_id: str,
    lease_seconds: int,
    *,
    now: datetime | None = None,
) -> ConnectorJob | None:
    claimed_at = now or datetime.now(UTC)
    candidate_result = await session.execute(
        select(ConnectorJob.id)
        .where(_claimable(claimed_at))
        .order_by(
            case((ConnectorJob.status == ConnectorJobStatus.QUEUED, 0), else_=1),
            ConnectorJob.available_at,
            ConnectorJob.created_at,
            ConnectorJob.id,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job_id = candidate_result.scalar_one_or_none()
    if job_id is None:
        await session.rollback()
        return None

    claimed_result = await session.execute(
        update(ConnectorJob)
        .where(ConnectorJob.id == job_id, _claimable(claimed_at))
        .values(
            status=ConnectorJobStatus.RUNNING,
            started_at=case(
                (ConnectorJob.started_at.is_(None), claimed_at),
                else_=ConnectorJob.started_at,
            ),
            finished_at=None,
            lease_owner=worker_id,
            lease_expires_at=claimed_at + timedelta(seconds=lease_seconds),
            claim_count=ConnectorJob.claim_count + 1,
        )
        .returning(ConnectorJob.id)
    )
    if claimed_result.scalar_one_or_none() is None:
        await session.rollback()
        return None

    job = await session.get(ConnectorJob, job_id)
    assert job is not None
    run = await session.get(AnalysisRun, job.run_id)
    assert run is not None
    if run.state == RunState.QUEUED:
        run.state = RunState.COLLECTING
        run.started_at = run.started_at or claimed_at
    await session.commit()
    await session.refresh(job)
    return job


async def finish_connector_job(
    session: AsyncSession,
    job_id: UUID,
    worker_id: str,
    outcome: WebConnectorOutcome,
    document_id: UUID | None = None,
) -> bool:
    result = await session.execute(
        update(ConnectorJob)
        .where(
            ConnectorJob.id == job_id,
            ConnectorJob.status == ConnectorJobStatus.RUNNING,
            ConnectorJob.lease_owner == worker_id,
        )
        .values(
            status=outcome.status,
            requested_url=outcome.requested_url,
            attempts=outcome.attempts,
            robots_url=outcome.robots_url,
            robots_allowed=outcome.robots_allowed,
            final_url=outcome.final_url,
            response_media_type=outcome.media_type,
            response_hash=outcome.response_hash,
            response_bytes=outcome.response_bytes,
            redirect_count=outcome.redirect_count,
            parser_version=outcome.parser_version,
            source_page_count=outcome.source_page_count,
            extracted_page_count=outcome.extracted_page_count,
            error_code=outcome.error_code,
            error_message=outcome.error_message,
            document_id=document_id,
            finished_at=datetime.now(UTC),
            lease_owner=None,
            lease_expires_at=None,
        )
        .returning(ConnectorJob.id)
    )
    finished = result.scalar_one_or_none() is not None
    await session.commit()
    return finished


async def get_connector_job(session: AsyncSession, job_id: UUID) -> ConnectorJob | None:
    return await session.get(ConnectorJob, job_id)


async def list_connector_jobs(session: AsyncSession, run_id: UUID) -> list[ConnectorJob]:
    result = await session.execute(
        select(ConnectorJob)
        .where(ConnectorJob.run_id == run_id)
        .order_by(ConnectorJob.created_at, ConnectorJob.id)
    )
    return list(result.scalars())
