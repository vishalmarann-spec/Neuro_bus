import pytest

from app.core.models import ClusterLabel, EvidenceStance, InsightStatus
from app.domain.reporting import (
    calculate_report_confidence,
    calculate_report_status,
    validate_statement_citations,
)
from app.services.report_exports import compact_text, escape_markdown, quote_markdown


def test_supported_statement_requires_supporting_evidence() -> None:
    errors = validate_statement_citations(
        ClusterLabel.SUPPORTED,
        [EvidenceStance.CONTRADICTS],
    )

    assert errors == ["A report statement must cite supporting evidence."]


def test_disputed_statement_requires_both_sides() -> None:
    assert validate_statement_citations(
        ClusterLabel.DISPUTED,
        [EvidenceStance.SUPPORTS],
    ) == ["A disputed report statement must cite contradicting evidence."]
    assert (
        validate_statement_citations(
            ClusterLabel.DISPUTED,
            [EvidenceStance.SUPPORTS, EvidenceStance.CONTRADICTS],
        )
        == []
    )


def test_contextual_evidence_cannot_be_a_report_citation() -> None:
    errors = validate_statement_citations(
        ClusterLabel.EMERGING,
        [EvidenceStance.SUPPORTS, EvidenceStance.CONTEXTUAL],
    )

    assert errors == ["Report citations cannot use these stances: contextual."]


def test_report_confidence_and_review_status_are_deterministic() -> None:
    assert calculate_report_confidence([0.8, 0.6]) == pytest.approx(0.7)
    assert calculate_report_status([ClusterLabel.SUPPORTED]) == InsightStatus.READY
    assert (
        calculate_report_status([ClusterLabel.SUPPORTED, ClusterLabel.EMERGING])
        == InsightStatus.NEEDS_REVIEW
    )


def test_markdown_export_escapes_untrusted_source_text() -> None:
    assert escape_markdown("<script>*claim*</script>") == ("\\<script\\>\\*claim\\*\\</script\\>")
    assert compact_text("Title\n# injected heading") == "Title # injected heading"
    assert quote_markdown("Evidence\n# not a heading") == ("> Evidence\n> \\# not a heading")
