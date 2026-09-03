from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import DocumentCapture
from app.core.models import AnalysisRun, Document, Passage, Project, ResearchQuestion, Source
from app.domain.provenance import (
    canonical_domain,
    canonicalize_url,
    segment_passages,
    sha256_text,
)


async def get_project(session: AsyncSession, project_id: UUID) -> Project | None:
    return await session.get(Project, project_id)


async def get_question(session: AsyncSession, question_id: UUID) -> ResearchQuestion | None:
    return await session.get(ResearchQuestion, question_id)


async def get_run(session: AsyncSession, run_id: UUID) -> AnalysisRun | None:
    return await session.get(AnalysisRun, run_id)


async def get_document(session: AsyncSession, document_id: UUID) -> Document | None:
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.passages), selectinload(Document.source))
        .where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


async def capture_document(
    session: AsyncSession,
    run: AnalysisRun,
    payload: DocumentCapture,
) -> tuple[Source, Document, list[Passage], bool]:
    original_url = str(payload.url)
    normalized_url = canonicalize_url(original_url)
    domain = canonical_domain(normalized_url)
    content_hash = sha256_text(payload.raw_content)

    existing_result = await session.execute(
        select(Document)
        .options(selectinload(Document.passages), selectinload(Document.source))
        .where(
            Document.run_id == run.id,
            Document.canonical_url == normalized_url,
            Document.content_hash == content_hash,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing.source, existing, list(existing.passages), True

    source_result = await session.execute(
        select(Source).where(
            Source.canonical_domain == domain,
            Source.publisher == payload.publisher.strip(),
            Source.source_type == payload.source_type,
        )
    )
    source = source_result.scalar_one_or_none()
    if source is None:
        source = Source(
            canonical_domain=domain,
            publisher=payload.publisher.strip(),
            source_type=payload.source_type,
        )
        session.add(source)
        await session.flush()

    document = Document(
        run_id=run.id,
        source_id=source.id,
        original_url=original_url,
        canonical_url=normalized_url,
        title=payload.title,
        raw_content=payload.raw_content,
        content_hash=content_hash,
        retrieved_at=datetime.now(UTC),
        published_at=payload.published_at,
    )
    session.add(document)
    await session.flush()

    passages = [
        Passage(
            document_id=document.id,
            ordinal=span.ordinal,
            start_offset=span.start_offset,
            end_offset=span.end_offset,
            exact_text=span.exact_text,
            text_hash=span.text_hash,
        )
        for span in segment_passages(payload.raw_content)
    ]
    session.add_all(passages)
    await session.commit()

    for item in [source, document, *passages]:
        await session.refresh(item)
    return source, document, passages, False

