from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Request, Response, status

from app.api.schemas import (
    ConnectorJobRead,
    WebSourceFetchCreate,
    WebSourceFetchRead,
)
from app.core.database import DatabaseSession
from app.services.connector_jobs import (
    IdempotencyConflict,
    create_connector_job,
    get_connector_job,
    list_connector_jobs,
)
from app.services.storage import get_run
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
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_public_web_connector_job(
    run_id: ResourceID,
    payload: WebSourceFetchCreate,
    request: Request,
    response: Response,
    session: DatabaseSession,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ] = None,
) -> WebSourceFetchRead:
    run = await get_run(session, run_id)
    if run is None:
        raise not_found("Analysis run")
    connector: PublicWebConnector = request.app.state.web_connector
    try:
        job, idempotent = await create_connector_job(
            session, run, payload, connector.max_attempts, idempotency_key
        )
    except IdempotencyConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "IDEMPOTENCY_KEY_REUSED",
                "message": "The idempotency key was already used for another request.",
            },
        ) from None
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return WebSourceFetchRead(
        job=ConnectorJobRead.model_validate(job), capture=None, idempotent=idempotent
    )


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
