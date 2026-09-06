from dataclasses import replace
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request, status

from app.api.schemas import (
    ConnectorJobRead,
    DocumentCapture,
    DocumentCaptureRead,
    WebSourceFetchCreate,
    WebSourceFetchRead,
)
from app.core.database import DatabaseSession
from app.core.models import ConnectorJobStatus
from app.services.connector_jobs import (
    create_connector_job,
    finish_connector_job,
    get_connector_job,
    list_connector_jobs,
    start_connector_job,
)
from app.services.storage import SourceMetadataConflict, capture_document, get_run
from app.services.web_connector import PublicWebConnector

router = APIRouter(tags=["public-web-connector"])
ResourceID = Annotated[UUID, Path()]


def not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"{resource} was not found."},
    )


@router.post(
    "/runs/{run_id}/connector-jobs",
    response_model=WebSourceFetchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_web_connector_job(
    run_id: ResourceID,
    payload: WebSourceFetchCreate,
    request: Request,
    session: DatabaseSession,
) -> WebSourceFetchRead:
    run = await get_run(session, run_id)
    if run is None:
        raise not_found("Analysis run")
    connector: PublicWebConnector = request.app.state.web_connector
    job = await create_connector_job(
        session,
        run,
        str(payload.url),
        connector.max_attempts,
    )
    await start_connector_job(session, run, job)
    outcome = await connector.collect(str(payload.url))
    capture: DocumentCaptureRead | None = None
    document_id: UUID | None = None

    if outcome.status == ConnectorJobStatus.SUCCEEDED:
        assert outcome.final_url is not None
        assert outcome.text is not None
        try:
            source, document, passages, duplicate = await capture_document(
                session,
                run,
                DocumentCapture(
                    url=outcome.final_url,
                    publisher=payload.publisher,
                    publisher_family=payload.publisher_family,
                    source_type=payload.source_type,
                    title=payload.title or outcome.title,
                    raw_content=outcome.text,
                    published_at=payload.published_at,
                ),
            )
        except SourceMetadataConflict:
            outcome = replace(
                outcome,
                status=ConnectorJobStatus.UNAVAILABLE,
                error_code="source_metadata_conflict",
                error_message="Source metadata conflicts with an existing source record.",
            )
        else:
            document_id = document.id
            capture = DocumentCaptureRead(
                source=source,
                document=document,
                passages=passages,
                duplicate=duplicate,
            )

    await finish_connector_job(session, job, outcome, document_id)
    return WebSourceFetchRead(job=ConnectorJobRead.model_validate(job), capture=capture)


@router.get("/connector-jobs/{job_id}", response_model=ConnectorJobRead)
async def read_connector_job(job_id: ResourceID, session: DatabaseSession) -> ConnectorJobRead:
    job = await get_connector_job(session, job_id)
    if job is None:
        raise not_found("Connector job")
    return ConnectorJobRead.model_validate(job)


@router.get("/runs/{run_id}/connector-jobs", response_model=list[ConnectorJobRead])
async def read_run_connector_jobs(
    run_id: ResourceID, session: DatabaseSession
) -> list[ConnectorJobRead]:
    if await get_run(session, run_id) is None:
        raise not_found("Analysis run")
    jobs = await list_connector_jobs(session, run_id)
    return [ConnectorJobRead.model_validate(job) for job in jobs]
