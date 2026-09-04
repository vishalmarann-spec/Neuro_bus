from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy import select

from app.api.routes.storage import not_found
from app.api.schemas import (
    ClaimReviewCreate,
    ClaimReviewRead,
    ExtractionRunRead,
    ModelExecutionRead,
    UEOClaimRead,
    UEOEntityRead,
    UEOEvidenceRead,
    UEOProvenanceRead,
    UEORead,
    UEOScoresRead,
    UEOVersionsRead,
)
from app.core.database import DatabaseSession
from app.core.models import (
    Claim,
    Document,
    Entity,
    EvidenceLink,
    ModelExecution,
    Passage,
    ReviewDecision,
    Source,
    ValidationStatus,
)
from app.providers.models import ExtractionModelProvider
from app.services.extraction import extract_document
from app.services.storage import get_document, get_run

router = APIRouter(tags=["evidence-extraction"])
ResourceID = Annotated[UUID, Path()]


def get_model_provider(request: Request) -> ExtractionModelProvider:
    return request.app.state.model_provider


@router.post("/documents/{document_id}/extract", response_model=ExtractionRunRead)
async def run_document_extraction(
    document_id: ResourceID,
    response: Response,
    session: DatabaseSession,
    provider: Annotated[ExtractionModelProvider, Depends(get_model_provider)],
) -> ExtractionRunRead:
    document = await get_document(session, document_id)
    if document is None:
        raise not_found("Document")
    outcome = await extract_document(session, document, provider)
    if outcome.execution.validation_status == ValidationStatus.UNAVAILABLE:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ExtractionRunRead(
        execution_id=outcome.execution.id,
        status=outcome.execution.validation_status,
        entities_count=outcome.entities_count,
        claims_count=outcome.claims_count,
        evidence_links_count=outcome.evidence_links_count,
        idempotent=outcome.idempotent,
        validation_errors=outcome.execution.validation_errors,
    )


@router.get("/model-executions/{execution_id}", response_model=ModelExecutionRead)
async def read_model_execution(
    execution_id: ResourceID,
    session: DatabaseSession,
) -> ModelExecution:
    execution = await session.get(ModelExecution, execution_id)
    if execution is None:
        raise not_found("Model execution")
    return execution


@router.get("/runs/{run_id}/ueos", response_model=list[UEORead])
async def read_run_ueos(run_id: ResourceID, session: DatabaseSession) -> list[UEORead]:
    if await get_run(session, run_id) is None:
        raise not_found("Analysis run")

    result = await session.execute(
        select(EvidenceLink, Claim, Passage, Document, Source, Entity, ModelExecution)
        .join(Claim, EvidenceLink.claim_id == Claim.id)
        .join(Passage, EvidenceLink.passage_id == Passage.id)
        .join(Document, Passage.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .join(ModelExecution, Claim.model_execution_id == ModelExecution.id)
        .outerjoin(Entity, Claim.subject_entity_id == Entity.id)
        .where(
            Document.run_id == run_id,
            ModelExecution.validation_status == ValidationStatus.ACCEPTED,
        )
        .order_by(ModelExecution.created_at, Claim.created_at, Passage.ordinal)
    )

    ueos: list[UEORead] = []
    for link, claim, passage, document, source, entity, execution in result.all():
        subject = (
            UEOEntityRead(
                id=entity.id,
                entity_type=entity.entity_type,
                canonical_name=entity.canonical_name,
            )
            if entity
            else None
        )
        ueos.append(
            UEORead(
                id=f"ueo_{link.id}",
                claim=UEOClaimRead(
                    id=claim.id,
                    normalized_text=claim.normalized_text,
                    subject=subject,
                    predicate=claim.predicate,
                    object_value=claim.object_value,
                    qualifiers=claim.qualifiers,
                    extraction_confidence=claim.extraction_confidence,
                    review_status=claim.review_status,
                ),
                evidence=UEOEvidenceRead(
                    link_id=link.id,
                    stance=link.stance,
                    passage_id=passage.id,
                    quote=passage.exact_text,
                    directness=link.directness,
                    extraction_confidence=link.extraction_confidence,
                    rationale=link.rationale,
                ),
                provenance=UEOProvenanceRead(
                    url=document.canonical_url,
                    publisher=source.publisher,
                    published_at=document.published_at,
                    retrieved_at=document.retrieved_at,
                    document_hash=document.content_hash,
                ),
                scores=UEOScoresRead(
                    extraction_confidence=link.extraction_confidence,
                ),
                versions=UEOVersionsRead(extractor_version=execution.prompt_version),
            )
        )
    return ueos


@router.post("/review/claims/{claim_id}", response_model=ClaimReviewRead)
async def review_claim(
    claim_id: ResourceID,
    payload: ClaimReviewCreate,
    session: DatabaseSession,
) -> ClaimReviewRead:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise not_found("Claim")
    decision = ReviewDecision(
        claim_id=claim.id,
        action=payload.action,
        reason=payload.reason.strip(),
        actor=payload.actor.strip(),
    )
    claim.review_status = payload.action
    session.add(decision)
    await session.commit()
    await session.refresh(decision)
    return ClaimReviewRead(
        decision_id=decision.id,
        claim_id=claim.id,
        action=decision.action,
        reason=decision.reason,
        actor=decision.actor,
        created_at=decision.created_at,
    )


@router.get("/claims/{claim_id}/reviews", response_model=list[ClaimReviewRead])
async def read_claim_reviews(
    claim_id: ResourceID,
    session: DatabaseSession,
) -> list[ClaimReviewRead]:
    if await session.get(Claim, claim_id) is None:
        raise not_found("Claim")
    result = await session.execute(
        select(ReviewDecision)
        .where(ReviewDecision.claim_id == claim_id)
        .order_by(ReviewDecision.created_at, ReviewDecision.id)
    )
    return [
        ClaimReviewRead(
            decision_id=decision.id,
            claim_id=decision.claim_id,
            action=decision.action,
            reason=decision.reason,
            actor=decision.actor,
            created_at=decision.created_at,
        )
        for decision in result.scalars()
    ]
