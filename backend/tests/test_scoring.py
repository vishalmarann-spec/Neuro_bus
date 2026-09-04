from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.models import ClusterLabel, EvidenceStance
from app.domain.scoring import (
    EvidenceInput,
    aggregate_cluster,
    calculate_evidence_quality,
    calculate_freshness,
    calculate_source_trust,
)


def evidence(stance: EvidenceStance, group: str, quality: float) -> EvidenceInput:
    return EvidenceInput(
        link_id=uuid4(),
        stance=stance,
        independence_group=group,
        quality=quality,
        components={},
    )


def test_unknown_source_trust_is_explicit_not_invented() -> None:
    trust = calculate_source_trust({})
    quality = calculate_evidence_quality(
        source_profile={},
        directness=0.8,
        extraction_confidence=0.9,
        specificity=0.7,
        freshness=None,
    )

    assert trust.used == {}
    assert set(trust.missing) == {
        "identity_accountability",
        "primary_source_proximity",
        "method_transparency",
        "domain_relevance",
        "historical_reliability",
    }
    assert "source_trust" in quality.missing
    assert "freshness" in quality.missing


def test_invalid_source_trust_values_are_treated_as_missing() -> None:
    trust = calculate_source_trust(
        {
            "identity_accountability": "not-a-number",
            "primary_source_proximity": True,
            "method_transparency": float("nan"),
            "domain_relevance": 0.8,
        }
    )

    assert trust.value == 0.8
    assert trust.used == {"domain_relevance": 0.8}
    assert set(trust.missing) == {
        "identity_accountability",
        "primary_source_proximity",
        "method_transparency",
        "historical_reliability",
    }


def test_independent_support_can_be_well_supported() -> None:
    result = aggregate_cluster(
        [
            evidence(EvidenceStance.SUPPORTS, "source:a", 0.8),
            evidence(EvidenceStance.SUPPORTS, "source:b", 0.8),
        ]
    )

    assert result.support_strength == pytest.approx(0.96)
    assert result.supporting_independent_sources == 2
    assert result.label == ClusterLabel.WELL_SUPPORTED


def test_duplicate_evidence_is_discounted_and_not_independent() -> None:
    result = aggregate_cluster(
        [
            evidence(EvidenceStance.SUPPORTS, "content:same", 0.8),
            evidence(EvidenceStance.SUPPORTS, "content:same", 0.8),
        ]
    )

    assert result.support_strength == pytest.approx(0.84)
    assert result.supporting_independent_sources == 1
    assert result.label == ClusterLabel.SUPPORTED
    assert sorted(item["independence_weight"] for item in result.contributions) == [0.25, 1.0]


def test_strong_contradiction_makes_cluster_disputed() -> None:
    result = aggregate_cluster(
        [
            evidence(EvidenceStance.SUPPORTS, "source:a", 0.9),
            evidence(EvidenceStance.CONTRADICTS, "source:b", 0.7),
        ]
    )

    assert result.contradiction_strength == pytest.approx(0.7)
    assert result.confidence == pytest.approx(0.27)
    assert result.label == ClusterLabel.DISPUTED


def test_price_freshness_uses_versioned_half_life_rule() -> None:
    as_of = datetime(2026, 9, 4, tzinfo=UTC)
    published_at = as_of - timedelta(days=180)

    assert calculate_freshness("has_annual_tuition", published_at, as_of) == pytest.approx(0.5)
    assert calculate_freshness("launched_programme", published_at, as_of) is None
