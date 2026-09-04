from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Response, status

from app.api.routes.storage import not_found
from app.api.schemas import (
    InsightCitationRead,
    InsightGenerationRead,
    InsightRead,
    InsightReportRead,
    InsightStatementRead,
)
from app.core.database import DatabaseSession
from app.core.models import Insight
from app.services.insights import (
    InsightBuildError,
    InsightBundle,
    generate_insight,
    load_insight_bundle,
)
from app.services.report_exports import render_report_markdown

router = APIRouter(tags=["cited-insights"])
ResourceID = Annotated[UUID, Path()]


def render_insight(insight: Insight) -> InsightRead:
    return InsightRead.model_validate(insight)


def render_report(bundle: InsightBundle) -> InsightReportRead:
    return InsightReportRead(
        insight=render_insight(bundle.insight),
        statements=[
            InsightStatementRead(
                id=record.statement.id,
                cluster_id=record.statement.cluster_id,
                claim_id=record.statement.claim_id,
                text=record.statement.text,
                label=record.statement.label,
                confidence=record.statement.confidence,
                display_order=record.statement.display_order,
                citations=[
                    InsightCitationRead(
                        evidence_link_id=citation.link.id,
                        stance=citation.link.stance,
                        passage_id=citation.passage.id,
                        quote=citation.passage.exact_text,
                        canonical_url=citation.document.canonical_url,
                        publisher=citation.source.publisher,
                        published_at=citation.document.published_at,
                        retrieved_at=citation.document.retrieved_at,
                        document_hash=citation.document.content_hash,
                        evidence_quality=citation.link.quality_score,
                    )
                    for citation in record.citations
                ],
            )
            for record in bundle.statements
        ],
    )


@router.post(
    "/runs/{run_id}/insights",
    response_model=InsightGenerationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_insight(
    run_id: ResourceID,
    response: Response,
    session: DatabaseSession,
) -> InsightGenerationRead:
    try:
        outcome = await generate_insight(session, run_id)
    except InsightBuildError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if exc.code == "RESOURCE_NOT_FOUND"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    if outcome.idempotent:
        response.status_code = status.HTTP_200_OK
    return InsightGenerationRead(
        **render_insight(outcome.bundle.insight).model_dump(),
        idempotent=outcome.idempotent,
    )


@router.get("/insights/{insight_id}", response_model=InsightRead)
async def read_insight(insight_id: ResourceID, session: DatabaseSession) -> InsightRead:
    insight = await session.get(Insight, insight_id)
    if insight is None:
        raise not_found("Insight")
    return render_insight(insight)


@router.get("/insights/{insight_id}/report", response_model=InsightReportRead)
async def read_insight_report(
    insight_id: ResourceID,
    session: DatabaseSession,
) -> InsightReportRead:
    bundle = await load_insight_bundle(session, insight_id)
    if bundle is None:
        raise not_found("Insight")
    return render_report(bundle)


@router.get("/insights/{insight_id}/report.md", response_class=Response)
async def export_insight_report(
    insight_id: ResourceID,
    session: DatabaseSession,
) -> Response:
    bundle = await load_insight_bundle(session, insight_id)
    if bundle is None:
        raise not_found("Insight")
    return Response(
        content=render_report_markdown(bundle),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="neuro-bus-report-{insight_id}.md"'},
    )
