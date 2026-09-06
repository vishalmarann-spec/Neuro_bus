from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from app.api.schemas import (
    DocumentCapture,
    DocumentCaptureRead,
    DocumentProvenanceLinkCaptureRead,
    DocumentProvenanceLinkCreate,
    DocumentProvenanceLinkRead,
    DocumentRead,
    PassageRead,
    ProjectCreate,
    ProjectRead,
    QuestionCreate,
    QuestionRead,
    RunCreate,
    RunRead,
)
from app.core.database import DatabaseSession
from app.core.models import AnalysisRun, Project, ResearchQuestion
from app.domain.provenance import InvalidSourceURL
from app.services.storage import (
    InvalidProvenanceLink,
    SourceMetadataConflict,
    capture_document,
    get_document,
    get_project,
    get_question,
    get_run,
    list_provenance_links,
    record_provenance_link,
)

router = APIRouter(tags=["evidence-storage"])
ResourceID = Annotated[UUID, Path()]


def not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"{resource} was not found."},
    )


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: DatabaseSession) -> Project:
    project = Project(name=payload.name, vertical=payload.vertical)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def read_project(project_id: ResourceID, session: DatabaseSession) -> Project:
    project = await get_project(session, project_id)
    if project is None:
        raise not_found("Project")
    return project


@router.post(
    "/projects/{project_id}/questions",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_question(
    project_id: ResourceID,
    payload: QuestionCreate,
    session: DatabaseSession,
) -> ResearchQuestion:
    if await get_project(session, project_id) is None:
        raise not_found("Project")
    question = ResearchQuestion(project_id=project_id, text=payload.text, scope=payload.scope)
    session.add(question)
    await session.commit()
    await session.refresh(question)
    return question


@router.get("/questions/{question_id}", response_model=QuestionRead)
async def read_question(question_id: ResourceID, session: DatabaseSession) -> ResearchQuestion:
    question = await get_question(session, question_id)
    if question is None:
        raise not_found("Research question")
    return question


@router.post(
    "/questions/{question_id}/runs",
    response_model=RunRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(
    question_id: ResourceID,
    payload: RunCreate,
    session: DatabaseSession,
) -> AnalysisRun:
    if await get_question(session, question_id) is None:
        raise not_found("Research question")
    run = AnalysisRun(question_id=question_id, pipeline_version=payload.pipeline_version)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@router.get("/runs/{run_id}", response_model=RunRead)
async def read_run(run_id: ResourceID, session: DatabaseSession) -> AnalysisRun:
    run = await get_run(session, run_id)
    if run is None:
        raise not_found("Analysis run")
    return run


@router.post(
    "/runs/{run_id}/sources",
    response_model=DocumentCaptureRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_capture(
    run_id: ResourceID,
    payload: DocumentCapture,
    session: DatabaseSession,
) -> DocumentCaptureRead:
    run = await get_run(session, run_id)
    if run is None:
        raise not_found("Analysis run")
    try:
        source, document, passages, duplicate = await capture_document(session, run, payload)
    except InvalidSourceURL as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except SourceMetadataConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DocumentCaptureRead(
        source=source,
        document=document,
        passages=passages,
        duplicate=duplicate,
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def read_document(document_id: ResourceID, session: DatabaseSession):
    document = await get_document(session, document_id)
    if document is None:
        raise not_found("Document")
    return document


@router.post(
    "/documents/{document_id}/provenance-links",
    response_model=DocumentProvenanceLinkCaptureRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_provenance_link(
    document_id: ResourceID,
    payload: DocumentProvenanceLinkCreate,
    session: DatabaseSession,
) -> DocumentProvenanceLinkCaptureRead:
    document = await get_document(session, document_id)
    if document is None:
        raise not_found("Document")
    try:
        link, duplicate = await record_provenance_link(session, document, payload)
    except (InvalidSourceURL, InvalidProvenanceLink) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return DocumentProvenanceLinkCaptureRead(link=link, duplicate=duplicate)


@router.get(
    "/documents/{document_id}/provenance-links",
    response_model=list[DocumentProvenanceLinkRead],
)
async def read_document_provenance_links(document_id: ResourceID, session: DatabaseSession):
    if await get_document(session, document_id) is None:
        raise not_found("Document")
    return await list_provenance_links(session, document_id)


@router.get("/documents/{document_id}/passages", response_model=list[PassageRead])
async def read_document_passages(document_id: ResourceID, session: DatabaseSession):
    document = await get_document(session, document_id)
    if document is None:
        raise not_found("Document")
    return document.passages
