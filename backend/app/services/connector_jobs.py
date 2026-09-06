from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AnalysisRun, ConnectorJob, ConnectorJobStatus, RunState
from app.services.web_connector import WebConnectorOutcome


async def create_connector_job(
    session: AsyncSession,
    run: AnalysisRun,
    requested_url: str,
    max_attempts: int,
) -> ConnectorJob:
    job = ConnectorJob(
        run_id=run.id,
        requested_url=requested_url,
        max_attempts=max_attempts,
        status=ConnectorJobStatus.QUEUED,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def start_connector_job(session: AsyncSession, run: AnalysisRun, job: ConnectorJob) -> None:
    now = datetime.now(UTC)
    job.status = ConnectorJobStatus.RUNNING
    job.started_at = now
    if run.state == RunState.QUEUED:
        run.state = RunState.COLLECTING
        run.started_at = run.started_at or now
    await session.commit()


async def finish_connector_job(
    session: AsyncSession,
    job: ConnectorJob,
    outcome: WebConnectorOutcome,
    document_id: UUID | None = None,
) -> None:
    job.status = outcome.status
    job.requested_url = outcome.requested_url
    job.attempts = outcome.attempts
    job.robots_url = outcome.robots_url
    job.robots_allowed = outcome.robots_allowed
    job.final_url = outcome.final_url
    job.response_media_type = outcome.media_type
    job.response_hash = outcome.response_hash
    job.response_bytes = outcome.response_bytes
    job.redirect_count = outcome.redirect_count
    job.error_code = outcome.error_code
    job.error_message = outcome.error_message
    job.document_id = document_id
    job.finished_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(job)


async def get_connector_job(session: AsyncSession, job_id: UUID) -> ConnectorJob | None:
    return await session.get(ConnectorJob, job_id)


async def list_connector_jobs(session: AsyncSession, run_id: UUID) -> list[ConnectorJob]:
    result = await session.execute(
        select(ConnectorJob)
        .where(ConnectorJob.run_id == run_id)
        .order_by(ConnectorJob.created_at, ConnectorJob.id)
    )
    return list(result.scalars())
