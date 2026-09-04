import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    AnalysisRun,
    Claim,
    ClaimCluster,
    ClaimClusterScore,
    ClaimReviewStatus,
    Document,
    Entity,
    EvidenceLink,
    ModelExecution,
    Passage,
    Source,
    ValidationStatus,
)
from app.domain.provenance import sha256_text
from app.domain.scoring import (
    SCORING_VERSION,
    EvidenceInput,
    aggregate_cluster,
    calculate_evidence_quality,
    calculate_freshness,
    calculate_source_trust,
    calculate_specificity,
)


@dataclass(frozen=True, slots=True)
class ReasoningRecord:
    cluster: ClaimCluster
    score: ClaimClusterScore


def structured_signature(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def claim_cluster_identity(claim: Claim, subject: Entity | None) -> tuple[str, str, str, str]:
    subject_signature = (
        f"{subject.entity_type.value}:{subject.normalized_name}" if subject else "none"
    )
    return (
        subject_signature,
        claim.predicate.casefold(),
        structured_signature(claim.object_value),
        structured_signature(claim.qualifiers),
    )


def cluster_key(identity: tuple[str, str, str, str]) -> str:
    return sha256_text("|".join(identity))


async def reason_over_run(session: AsyncSession, run_id) -> list[ReasoningRecord]:
    query_result = await session.execute(
        select(Claim, EvidenceLink, Passage, Document, Source, Entity)
        .join(EvidenceLink, EvidenceLink.claim_id == Claim.id)
        .join(Passage, EvidenceLink.passage_id == Passage.id)
        .join(Document, Passage.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .join(ModelExecution, Claim.model_execution_id == ModelExecution.id)
        .outerjoin(Entity, Claim.subject_entity_id == Entity.id)
        .where(
            Document.run_id == run_id,
            ModelExecution.validation_status == ValidationStatus.ACCEPTED,
            Claim.review_status != ClaimReviewStatus.REJECTED,
        )
        .order_by(Claim.created_at, EvidenceLink.id)
    )
    rows = query_result.all()
    unique_documents = {(document.content_hash, document.id) for _, _, _, document, _, _ in rows}
    content_counts = Counter(content_hash for content_hash, _ in unique_documents)

    grouped_rows = defaultdict(list)
    for row in rows:
        claim, _, _, _, _, subject = row
        grouped_rows[claim_cluster_identity(claim, subject)].append(row)

    existing_result = await session.execute(
        select(ClaimCluster).where(ClaimCluster.run_id == run_id)
    )
    existing_by_key = {cluster.cluster_key: cluster for cluster in existing_result.scalars().all()}
    active_keys = {cluster_key(identity) for identity in grouped_rows}

    all_claims_result = await session.execute(
        select(Claim)
        .join(ModelExecution, Claim.model_execution_id == ModelExecution.id)
        .join(Document, ModelExecution.document_id == Document.id)
        .where(Document.run_id == run_id)
    )
    active_claim_ids = {claim.id for claim, *_ in rows}
    all_claims = list(all_claims_result.scalars())
    for claim in all_claims:
        if claim.id not in active_claim_ids:
            claim.cluster_id = None
    await session.flush()

    for stale_key in existing_by_key.keys() - active_keys:
        await session.delete(existing_by_key[stale_key])

    records: list[ReasoningRecord] = []
    for identity, cluster_rows in grouped_rows.items():
        first_claim, _, _, _, _, first_subject = cluster_rows[0]
        key = cluster_key(identity)
        cluster = existing_by_key.get(key)
        if cluster is None:
            cluster = ClaimCluster(
                run_id=run_id,
                cluster_key=key,
                canonical_text=first_claim.normalized_text,
                subject_entity_id=first_subject.id if first_subject else None,
                predicate=first_claim.predicate.casefold(),
                object_signature=identity[2],
                qualifiers_signature=identity[3],
            )
            session.add(cluster)
            await session.flush()
        else:
            cluster.canonical_text = first_claim.normalized_text
            cluster.subject_entity_id = first_subject.id if first_subject else None

        evidence_inputs: list[EvidenceInput] = []
        seen_claims = set()
        for claim, link, _, document, source, subject in cluster_rows:
            if claim.id not in seen_claims:
                claim.cluster_id = cluster.id
                seen_claims.add(claim.id)

            source_trust = calculate_source_trust(source.trust_profile)
            specificity = calculate_specificity(
                has_subject=subject is not None,
                object_value=claim.object_value,
                qualifiers=claim.qualifiers,
            )
            freshness = calculate_freshness(claim.predicate, document.published_at)
            quality = calculate_evidence_quality(
                source_profile=source.trust_profile,
                directness=link.directness,
                extraction_confidence=link.extraction_confidence,
                specificity=specificity,
                freshness=freshness,
            )
            components = {
                "used": quality.used,
                "missing": list(quality.missing),
                "source_trust": {
                    "value": source_trust.value if source_trust.used else None,
                    "used": source_trust.used,
                    "missing": list(source_trust.missing),
                },
            }
            link.quality_score = quality.value
            link.quality_components = components
            independence_group = (
                f"content:{document.content_hash}"
                if content_counts[document.content_hash] > 1
                else f"source:{source.id}"
            )
            evidence_inputs.append(
                EvidenceInput(
                    link_id=link.id,
                    stance=link.stance,
                    independence_group=independence_group,
                    quality=quality.value,
                    components=components,
                )
            )

        result = aggregate_cluster(evidence_inputs)
        score_result = await session.execute(
            select(ClaimClusterScore).where(ClaimClusterScore.cluster_id == cluster.id)
        )
        score = score_result.scalar_one_or_none()
        values = {
            "support_strength": result.support_strength,
            "contradiction_strength": result.contradiction_strength,
            "confidence": result.confidence,
            "label": result.label,
            "supporting_independent_sources": result.supporting_independent_sources,
            "evidence_count": result.evidence_count,
            "scoring_version": SCORING_VERSION,
            "explanation": {"contributions": list(result.contributions)},
            "calculated_at": datetime.now(UTC),
        }
        if score is None:
            score = ClaimClusterScore(cluster_id=cluster.id, **values)
            session.add(score)
        else:
            for name, value in values.items():
                setattr(score, name, value)
        records.append(ReasoningRecord(cluster=cluster, score=score))

    run = await session.get(AnalysisRun, run_id)
    if run is not None:
        run.metrics = {
            **run.metrics,
            "reasoning": {
                "scoring_version": SCORING_VERSION,
                "cluster_count": len(records),
                "included_claim_count": len(active_claim_ids),
                "excluded_claim_count": len(all_claims) - len(active_claim_ids),
                "evidence_link_count": len(rows),
                "calculated_at": datetime.now(UTC).isoformat(),
            },
        }
    await session.commit()
    for record in records:
        await session.refresh(record.cluster)
        await session.refresh(record.score)
    return records


async def load_reasoning_records(
    session: AsyncSession,
    run_id,
    *,
    disputed_only: bool = False,
) -> list[ReasoningRecord]:
    query = (
        select(ClaimCluster, ClaimClusterScore)
        .join(ClaimClusterScore, ClaimClusterScore.cluster_id == ClaimCluster.id)
        .where(ClaimCluster.run_id == run_id)
        .order_by(ClaimCluster.created_at, ClaimCluster.id)
    )
    if disputed_only:
        from app.core.models import ClusterLabel

        query = query.where(ClaimClusterScore.label == ClusterLabel.DISPUTED)
    result = await session.execute(query)
    return [ReasoningRecord(cluster=cluster, score=score) for cluster, score in result.all()]
