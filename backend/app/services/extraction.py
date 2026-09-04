import json
from dataclasses import dataclass
from time import perf_counter

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    Claim,
    Document,
    EntityMention,
    EvidenceLink,
    ModelExecution,
    ValidationStatus,
)
from app.domain.extraction import (
    ExtractionEnvelope,
    validate_provenance,
)
from app.domain.provenance import sha256_text
from app.providers.models import (
    ExtractionModelProvider,
    ExtractionPassage,
    ExtractionRequest,
    ModelProviderUnavailable,
)
from app.services.entity_resolution import resolve_entity

EXTRACTION_TASK = "entity_claim_extraction"
DEFAULT_PROMPT_VERSION = "claim-extractor.v1"


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    execution: ModelExecution
    entities_count: int = 0
    claims_count: int = 0
    evidence_links_count: int = 0
    idempotent: bool = False


def extraction_input_hash(document: Document, prompt_version: str) -> str:
    serialized = json.dumps(
        {
            "document_hash": document.content_hash,
            "passages": [
                {"ordinal": item.ordinal, "text_hash": item.text_hash} for item in document.passages
            ],
            "prompt_version": prompt_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(serialized)


def format_validation_errors(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors(include_url=False)
    ]


async def execution_counts(
    session: AsyncSession,
    execution_id,
) -> tuple[int, int, int]:
    claims_count = await session.scalar(
        select(func.count(Claim.id)).where(Claim.model_execution_id == execution_id)
    )
    evidence_count = await session.scalar(
        select(func.count(EvidenceLink.id))
        .join(Claim, EvidenceLink.claim_id == Claim.id)
        .where(Claim.model_execution_id == execution_id)
    )
    entity_count = await session.scalar(
        select(func.count(func.distinct(EntityMention.entity_id))).where(
            EntityMention.model_execution_id == execution_id
        )
    )
    return int(entity_count or 0), int(claims_count or 0), int(evidence_count or 0)


async def extract_document(
    session: AsyncSession,
    document: Document,
    provider: ExtractionModelProvider,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> ExtractionOutcome:
    input_hash = extraction_input_hash(document, prompt_version)
    previous_result = await session.execute(
        select(ModelExecution).where(
            ModelExecution.document_id == document.id,
            ModelExecution.task == EXTRACTION_TASK,
            ModelExecution.provider == provider.provider_name,
            ModelExecution.model == provider.model_name,
            ModelExecution.prompt_version == prompt_version,
            ModelExecution.input_hash == input_hash,
            ModelExecution.validation_status == ValidationStatus.ACCEPTED,
        )
    )
    previous = previous_result.scalar_one_or_none()
    if previous is not None:
        counts = await execution_counts(session, previous.id)
        return ExtractionOutcome(previous, *counts, idempotent=True)

    request = ExtractionRequest(
        document_id=document.id,
        title=document.title,
        canonical_url=document.canonical_url,
        passages=tuple(
            ExtractionPassage(
                ordinal=passage.ordinal,
                passage_id=passage.id,
                text=passage.exact_text,
            )
            for passage in document.passages
        ),
    )
    started = perf_counter()
    try:
        provider_response = await provider.extract(request)
    except ModelProviderUnavailable as exc:
        execution = ModelExecution(
            run_id=document.run_id,
            document_id=document.id,
            task=EXTRACTION_TASK,
            provider=provider.provider_name,
            model=provider.model_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
            raw_output=None,
            validation_status=ValidationStatus.UNAVAILABLE,
            validation_errors=[str(exc)],
            latency_ms=round((perf_counter() - started) * 1_000),
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        return ExtractionOutcome(execution)
    except Exception as exc:  # provider SDK/network errors are adapter-specific
        execution = ModelExecution(
            run_id=document.run_id,
            document_id=document.id,
            task=EXTRACTION_TASK,
            provider=provider.provider_name,
            model=provider.model_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
            raw_output=None,
            validation_status=ValidationStatus.UNAVAILABLE,
            validation_errors=[f"Provider failed with {type(exc).__name__}."],
            latency_ms=round((perf_counter() - started) * 1_000),
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        return ExtractionOutcome(execution)

    latency_ms = round((perf_counter() - started) * 1_000)
    raw_output = provider_response.raw_output
    try:
        extraction = ExtractionEnvelope.model_validate_json(raw_output)
        validation_errors = validate_provenance(extraction, list(document.passages))
    except ValidationError as exc:
        extraction = None
        validation_errors = format_validation_errors(exc)

    if extraction is None or validation_errors:
        execution = ModelExecution(
            run_id=document.run_id,
            document_id=document.id,
            task=EXTRACTION_TASK,
            provider=provider.provider_name,
            model=provider.model_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
            raw_output=raw_output,
            validation_status=ValidationStatus.INVALID,
            validation_errors=validation_errors,
            latency_ms=latency_ms,
            input_tokens=provider_response.input_tokens,
            output_tokens=provider_response.output_tokens,
            cost_usd=provider_response.cost_usd,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        return ExtractionOutcome(execution)

    execution = ModelExecution(
        run_id=document.run_id,
        document_id=document.id,
        task=EXTRACTION_TASK,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=prompt_version,
        input_hash=input_hash,
        raw_output=raw_output,
        validation_status=ValidationStatus.ACCEPTED,
        validation_errors=[],
        latency_ms=latency_ms,
        input_tokens=provider_response.input_tokens,
        output_tokens=provider_response.output_tokens,
        cost_usd=provider_response.cost_usd,
    )
    session.add(execution)
    await session.flush()

    passages_by_ordinal = {passage.ordinal: passage for passage in document.passages}
    entities_by_local_id = {}
    for candidate in extraction.entities:
        entity = await resolve_entity(session, candidate)
        entities_by_local_id[candidate.local_id] = entity

        for mention in candidate.mentions:
            passage = passages_by_ordinal[mention.passage_ordinal]
            session.add(
                EntityMention(
                    entity_id=entity.id,
                    passage_id=passage.id,
                    model_execution_id=execution.id,
                    surface_text=mention.surface_text,
                    start_offset=mention.start_offset,
                    end_offset=mention.end_offset,
                    confidence=mention.confidence,
                )
            )

    claims_count = 0
    evidence_count = 0
    for candidate in extraction.claims:
        subject = (
            entities_by_local_id[candidate.subject_local_id] if candidate.subject_local_id else None
        )
        claim = Claim(
            model_execution_id=execution.id,
            subject_entity_id=subject.id if subject else None,
            predicate=candidate.predicate,
            object_value=candidate.object_value,
            qualifiers=candidate.qualifiers,
            normalized_text=candidate.normalized_text,
            extraction_confidence=candidate.extraction_confidence,
        )
        session.add(claim)
        await session.flush()
        claims_count += 1

        for evidence in candidate.evidence:
            passage = passages_by_ordinal[evidence.passage_ordinal]
            session.add(
                EvidenceLink(
                    claim_id=claim.id,
                    passage_id=passage.id,
                    stance=evidence.stance,
                    directness=evidence.directness,
                    extraction_confidence=evidence.extraction_confidence,
                    rationale=evidence.rationale,
                )
            )
            evidence_count += 1

    await session.commit()
    await session.refresh(execution)
    return ExtractionOutcome(
        execution=execution,
        entities_count=len({entity.id for entity in entities_by_local_id.values()}),
        claims_count=claims_count,
        evidence_links_count=evidence_count,
    )
