from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    AnalysisRun,
    Claim,
    ClaimCluster,
    ClaimClusterScore,
    ClaimReviewStatus,
    ClusterLabel,
    Document,
    EvidenceLink,
    EvidenceStance,
    Insight,
    InsightCitation,
    InsightStatement,
    Passage,
    ResearchQuestion,
    Source,
)
from app.domain.reporting import (
    REPORT_GENERATION_VERSION,
    REPORTABLE_LABELS,
    calculate_report_confidence,
    calculate_report_status,
    report_fingerprint,
    validate_statement_citations,
)


class InsightBuildError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CitationRecord:
    citation: InsightCitation
    link: EvidenceLink
    passage: Passage
    document: Document
    source: Source


@dataclass(frozen=True, slots=True)
class StatementRecord:
    statement: InsightStatement
    citations: tuple[CitationRecord, ...]


@dataclass(frozen=True, slots=True)
class InsightBundle:
    insight: Insight
    statements: tuple[StatementRecord, ...]


@dataclass(frozen=True, slots=True)
class InsightGenerationOutcome:
    bundle: InsightBundle
    idempotent: bool


@dataclass(frozen=True, slots=True)
class StatementDraft:
    cluster: ClaimCluster
    score: ClaimClusterScore
    claim: Claim
    evidence: tuple[tuple[EvidenceLink, Passage, Document, Source], ...]


def _citation_sort_key(
    item: tuple[EvidenceLink, Claim, Passage, Document, Source],
) -> tuple[int, float, str]:
    link, _, _, _, _ = item
    stance_order = 0 if link.stance == EvidenceStance.SUPPORTS else 1
    return stance_order, -(link.quality_score or 0.0), str(link.id)


async def _build_statement_draft(
    session: AsyncSession,
    cluster: ClaimCluster,
    score: ClaimClusterScore,
) -> StatementDraft | None:
    evidence_result = await session.execute(
        select(EvidenceLink, Claim, Passage, Document, Source)
        .join(Claim, EvidenceLink.claim_id == Claim.id)
        .join(Passage, EvidenceLink.passage_id == Passage.id)
        .join(Document, Passage.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .where(
            Claim.cluster_id == cluster.id,
            Claim.review_status != ClaimReviewStatus.REJECTED,
            EvidenceLink.stance.in_([EvidenceStance.SUPPORTS, EvidenceStance.CONTRADICTS]),
        )
    )
    rows = sorted(evidence_result.all(), key=_citation_sort_key)
    supporting = [item for item in rows if item[0].stance == EvidenceStance.SUPPORTS]
    contradicting = [item for item in rows if item[0].stance == EvidenceStance.CONTRADICTS]
    selected = [*supporting, *contradicting]
    errors = validate_statement_citations(score.label, [item[0].stance for item in selected])
    if errors:
        return None

    representative = sorted(
        {item[1].id: item[1] for item in selected}.values(),
        key=lambda claim: (-claim.extraction_confidence, claim.created_at, str(claim.id)),
    )[0]
    return StatementDraft(
        cluster=cluster,
        score=score,
        claim=representative,
        evidence=tuple(
            (link, passage, document, source) for link, _, passage, document, source in selected
        ),
    )


def _draft_fingerprint_payload(drafts: list[StatementDraft]) -> dict:
    return {
        "generation_version": REPORT_GENERATION_VERSION,
        "statements": [
            {
                "cluster_id": str(draft.cluster.id),
                "claim_id": str(draft.claim.id),
                "text": draft.claim.normalized_text,
                "label": draft.score.label.value,
                "confidence": draft.score.confidence,
                "scoring_version": draft.score.scoring_version,
                "evidence_link_ids": [str(item[0].id) for item in draft.evidence],
            }
            for draft in drafts
        ],
    }


async def generate_insight(
    session: AsyncSession,
    run_id: UUID,
) -> InsightGenerationOutcome:
    run_result = await session.execute(
        select(AnalysisRun, ResearchQuestion)
        .join(ResearchQuestion, AnalysisRun.question_id == ResearchQuestion.id)
        .where(AnalysisRun.id == run_id)
    )
    run_row = run_result.one_or_none()
    if run_row is None:
        raise InsightBuildError("RESOURCE_NOT_FOUND", "Analysis run was not found.")
    run, question = run_row

    cluster_result = await session.execute(
        select(ClaimCluster, ClaimClusterScore)
        .join(ClaimClusterScore, ClaimClusterScore.cluster_id == ClaimCluster.id)
        .where(ClaimCluster.run_id == run_id)
    )
    cluster_rows = cluster_result.all()
    if not cluster_rows:
        if "reasoning" in run.metrics:
            raise InsightBuildError(
                "INSUFFICIENT_EVIDENCE",
                "Reasoning completed, but no reportable scored claims remain.",
            )
        raise InsightBuildError(
            "REASONING_REQUIRED",
            "No scored claim clusters exist. Run multi-source reasoning first.",
        )

    reportable = sorted(
        (item for item in cluster_rows if item[1].label in REPORTABLE_LABELS),
        key=lambda item: (-item[1].confidence, item[0].predicate, str(item[0].id)),
    )
    drafts: list[StatementDraft] = []
    for cluster, score in reportable:
        draft = await _build_statement_draft(session, cluster, score)
        if draft is not None:
            drafts.append(draft)

    if not drafts:
        raise InsightBuildError(
            "INSUFFICIENT_EVIDENCE",
            "No reportable cluster has the required supporting citations.",
        )

    fingerprint = report_fingerprint(_draft_fingerprint_payload(drafts))
    existing_result = await session.execute(
        select(Insight).where(
            Insight.run_id == run_id,
            Insight.fingerprint == fingerprint,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        bundle = await load_insight_bundle(session, existing.id)
        if bundle is None:  # pragma: no cover - protected by the query above
            raise RuntimeError("Persisted insight could not be reloaded.")
        return InsightGenerationOutcome(bundle=bundle, idempotent=True)

    labels = [draft.score.label for draft in drafts]
    confidence = calculate_report_confidence(draft.score.confidence for draft in drafts)
    insight = Insight(
        run_id=run_id,
        title=f"Evidence report: {question.text}"[:500],
        conclusion="\n".join(draft.claim.normalized_text for draft in drafts),
        confidence=confidence,
        status=calculate_report_status(labels),
        generation_version=REPORT_GENERATION_VERSION,
        fingerprint=fingerprint,
        explanation={
            "included_cluster_count": len(drafts),
            "excluded_weak_cluster_count": sum(
                1 for _, score in cluster_rows if score.label not in REPORTABLE_LABELS
            ),
            "excluded_without_supporting_citations_count": len(reportable) - len(drafts),
            "disputed_cluster_count": sum(1 for label in labels if label == ClusterLabel.DISPUTED),
            "confidence_method": "unweighted mean of included cluster confidence values",
            "statement_source": "stored normalized claims only",
        },
    )
    session.add(insight)
    await session.flush()

    for statement_order, draft in enumerate(drafts):
        statement = InsightStatement(
            insight_id=insight.id,
            cluster_id=draft.cluster.id,
            claim_id=draft.claim.id,
            text=draft.claim.normalized_text,
            label=draft.score.label,
            confidence=draft.score.confidence,
            display_order=statement_order,
        )
        session.add(statement)
        await session.flush()
        session.add_all(
            InsightCitation(
                statement_id=statement.id,
                evidence_link_id=link.id,
                display_order=citation_order,
            )
            for citation_order, (link, _, _, _) in enumerate(draft.evidence)
        )

    await session.commit()
    bundle = await load_insight_bundle(session, insight.id)
    if bundle is None:  # pragma: no cover - protected by the insert above
        raise RuntimeError("Created insight could not be reloaded.")
    return InsightGenerationOutcome(bundle=bundle, idempotent=False)


async def load_insight_bundle(
    session: AsyncSession,
    insight_id: UUID,
) -> InsightBundle | None:
    insight = await session.get(Insight, insight_id)
    if insight is None:
        return None
    statement_result = await session.execute(
        select(InsightStatement)
        .where(InsightStatement.insight_id == insight_id)
        .order_by(InsightStatement.display_order, InsightStatement.id)
    )
    statement_records: list[StatementRecord] = []
    for statement in statement_result.scalars():
        citation_result = await session.execute(
            select(InsightCitation, EvidenceLink, Passage, Document, Source)
            .join(EvidenceLink, InsightCitation.evidence_link_id == EvidenceLink.id)
            .join(Passage, EvidenceLink.passage_id == Passage.id)
            .join(Document, Passage.document_id == Document.id)
            .join(Source, Document.source_id == Source.id)
            .where(InsightCitation.statement_id == statement.id)
            .order_by(InsightCitation.display_order, InsightCitation.id)
        )
        citations = tuple(
            CitationRecord(
                citation=citation,
                link=link,
                passage=passage,
                document=document,
                source=source,
            )
            for citation, link, passage, document, source in citation_result.all()
        )
        statement_records.append(StatementRecord(statement=statement, citations=citations))
    return InsightBundle(insight=insight, statements=tuple(statement_records))
