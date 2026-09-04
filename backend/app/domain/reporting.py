import json
from collections.abc import Iterable
from typing import Any

from app.core.models import ClusterLabel, EvidenceStance, InsightStatus
from app.domain.provenance import sha256_text

REPORT_GENERATION_VERSION = "cited-report.v1"
REPORTABLE_LABELS = frozenset(
    {
        ClusterLabel.WELL_SUPPORTED,
        ClusterLabel.SUPPORTED,
        ClusterLabel.EMERGING,
        ClusterLabel.DISPUTED,
    }
)


def validate_statement_citations(
    label: ClusterLabel,
    stances: Iterable[EvidenceStance],
) -> list[str]:
    resolved = list(stances)
    errors: list[str] = []
    if not resolved:
        errors.append("A report statement must cite at least one evidence link.")
        return errors
    if EvidenceStance.SUPPORTS not in resolved:
        errors.append("A report statement must cite supporting evidence.")
    if label == ClusterLabel.DISPUTED and EvidenceStance.CONTRADICTS not in resolved:
        errors.append("A disputed report statement must cite contradicting evidence.")
    unsupported = sorted(
        {
            stance.value
            for stance in resolved
            if stance
            not in {
                EvidenceStance.SUPPORTS,
                EvidenceStance.CONTRADICTS,
            }
        }
    )
    if unsupported:
        errors.append(f"Report citations cannot use these stances: {', '.join(unsupported)}.")
    return errors


def calculate_report_confidence(values: Iterable[float]) -> float:
    resolved = list(values)
    if not resolved:
        raise ValueError("A report requires at least one statement confidence value.")
    return sum(resolved) / len(resolved)


def calculate_report_status(labels: Iterable[ClusterLabel]) -> InsightStatus:
    resolved = set(labels)
    if ClusterLabel.DISPUTED in resolved or ClusterLabel.EMERGING in resolved:
        return InsightStatus.NEEDS_REVIEW
    return InsightStatus.READY


def report_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)
