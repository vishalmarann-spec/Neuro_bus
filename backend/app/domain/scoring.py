import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.models import ClusterLabel, EvidenceStance

SCORING_VERSION = "claim-confidence.v2"
SOURCE_TRUST_WEIGHTS = {
    "identity_accountability": 0.25,
    "primary_source_proximity": 0.25,
    "method_transparency": 0.20,
    "domain_relevance": 0.15,
    "historical_reliability": 0.15,
}
EVIDENCE_WEIGHTS = {
    "source_trust": 0.30,
    "directness": 0.25,
    "extraction_confidence": 0.20,
    "specificity": 0.15,
    "freshness": 0.10,
}


@dataclass(frozen=True, slots=True)
class WeightedScore:
    value: float
    used: dict[str, float]
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    link_id: UUID
    stance: EvidenceStance
    independence_group: str
    quality: float
    components: dict[str, Any]
    independence_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClusterScoreResult:
    support_strength: float
    contradiction_strength: float
    confidence: float
    label: ClusterLabel
    supporting_independent_sources: int
    evidence_count: int
    contributions: tuple[dict[str, Any], ...]


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def weighted_mean(
    components: dict[str, float | None],
    weights: dict[str, float],
) -> WeightedScore:
    used: dict[str, float] = {}
    for name, value in components.items():
        if name not in weights or value is None or isinstance(value, bool):
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric_value):
            used[name] = clamp(numeric_value)
    denominator = sum(weights[name] for name in used)
    value = sum(used[name] * weights[name] for name in used) / denominator if denominator else 0.5
    missing = tuple(name for name in weights if name not in used)
    return WeightedScore(value=value, used=used, missing=missing)


def calculate_source_trust(profile: dict[str, Any]) -> WeightedScore:
    components = {name: profile.get(name) for name in SOURCE_TRUST_WEIGHTS}
    return weighted_mean(components, SOURCE_TRUST_WEIGHTS)


def calculate_specificity(
    has_subject: bool,
    object_value: dict,
    qualifiers: dict,
) -> float:
    return clamp(
        (0.3 if has_subject else 0.0)
        + (0.4 if object_value else 0.0)
        + (0.3 if qualifiers else 0.0)
    )


def calculate_freshness(
    predicate: str,
    published_at: datetime | None,
    as_of: datetime | None = None,
) -> float | None:
    if published_at is None:
        return None
    lower_predicate = predicate.casefold()
    half_life_days = None
    if any(token in lower_predicate for token in ("price", "tuition", "fee")):
        half_life_days = 180
    elif any(token in lower_predicate for token in ("demand", "trend", "employment")):
        half_life_days = 365
    if half_life_days is None:
        return None
    resolved_as_of = as_of or datetime.now(UTC)
    resolved_published = (
        published_at.replace(tzinfo=UTC) if published_at.tzinfo is None else published_at
    )
    age_days = max(0.0, (resolved_as_of - resolved_published).total_seconds() / 86_400)
    return 0.5 ** (age_days / half_life_days)


def calculate_evidence_quality(
    *,
    source_profile: dict[str, Any],
    directness: float,
    extraction_confidence: float,
    specificity: float,
    freshness: float | None,
) -> WeightedScore:
    source_trust = calculate_source_trust(source_profile)
    source_value = source_trust.value if source_trust.used else None
    return weighted_mean(
        {
            "source_trust": source_value,
            "directness": directness,
            "extraction_confidence": extraction_confidence,
            "specificity": specificity,
            "freshness": freshness,
        },
        EVIDENCE_WEIGHTS,
    )


def _combined_strength(values: list[float]) -> float:
    return 1.0 - math.prod(1.0 - clamp(value) for value in values)


def aggregate_cluster(evidence: list[EvidenceInput]) -> ClusterScoreResult:
    grouped: dict[tuple[EvidenceStance, str], list[EvidenceInput]] = {}
    for item in evidence:
        grouped.setdefault((item.stance, item.independence_group), []).append(item)

    support_values: list[float] = []
    contradiction_values: list[float] = []
    contributions: list[dict[str, Any]] = []
    supporting_groups: set[str] = set()
    for (stance, group), group_items in sorted(
        grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        ranked = sorted(group_items, key=lambda item: item.quality, reverse=True)
        for index, item in enumerate(ranked):
            independence_weight = 1.0 if index == 0 else 0.25
            weighted_quality = item.quality * independence_weight
            if stance == EvidenceStance.SUPPORTS:
                support_values.append(weighted_quality)
                supporting_groups.add(group)
            elif stance == EvidenceStance.CONTRADICTS:
                contradiction_values.append(weighted_quality)
            contributions.append(
                {
                    "link_id": str(item.link_id),
                    "stance": stance.value,
                    "independence_group": group,
                    "independence_reasons": list(item.independence_reasons),
                    "independence_weight": independence_weight,
                    "quality": item.quality,
                    "weighted_quality": weighted_quality,
                    "components": item.components,
                }
            )

    support = _combined_strength(support_values)
    contradiction = _combined_strength(contradiction_values)
    confidence = support * (1.0 - contradiction)
    if contradiction >= 0.55:
        label = ClusterLabel.DISPUTED
    elif confidence >= 0.75 and len(supporting_groups) >= 2:
        label = ClusterLabel.WELL_SUPPORTED
    elif confidence >= 0.55:
        label = ClusterLabel.SUPPORTED
    elif confidence >= 0.35:
        label = ClusterLabel.EMERGING
    else:
        label = ClusterLabel.WEAK

    return ClusterScoreResult(
        support_strength=support,
        contradiction_strength=contradiction,
        confidence=confidence,
        label=label,
        supporting_independent_sources=len(supporting_groups),
        evidence_count=len(evidence),
        contributions=tuple(contributions),
    )
