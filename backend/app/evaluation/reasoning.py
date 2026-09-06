import json
from uuid import NAMESPACE_URL, uuid5

from app.domain.provenance import canonical_domain, sha256_text
from app.domain.scoring import (
    SCORING_VERSION,
    EvidenceInput,
    aggregate_cluster,
    calculate_evidence_quality,
    calculate_specificity,
)
from app.evaluation.models import (
    GoldCase,
    ReasoningEvaluationReport,
    ReasoningScenario,
    ReasoningScenarioResult,
)
from app.evaluation.review import gold_case_fingerprint


def evaluation_source_group(case: GoldCase) -> str:
    document = case.document
    if document.source_url is None or document.publisher is None or document.source_type is None:
        raise ValueError(f"Reasoning case {case.case_id} lacks real-source metadata.")
    identity = json.dumps(
        {
            "domain": canonical_domain(document.source_url),
            "publisher": " ".join(document.publisher.split()).casefold(),
            "source_type": document.source_type.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"source:{sha256_text(identity)}"


def evaluate_reasoning_scenarios(
    scenarios: list[ReasoningScenario],
    cases: list[GoldCase],
) -> ReasoningEvaluationReport:
    cases_by_id = {case.case_id: case for case in cases}
    if len(cases_by_id) != len(cases):
        raise ValueError("Gold case_id values must be unique.")

    results: list[ReasoningScenarioResult] = []
    referenced_cases: list[GoldCase] = []
    for scenario in scenarios:
        inputs: list[EvidenceInput] = []
        for reference in scenario.evidence:
            case = cases_by_id.get(reference.case_id)
            if case is None:
                raise ValueError(
                    f"Reasoning scenario {scenario.scenario_id} references unknown case "
                    f"{reference.case_id}."
                )
            current_fingerprint = gold_case_fingerprint(case)
            if reference.case_fingerprint != current_fingerprint:
                raise ValueError(
                    f"Reasoning scenario {scenario.scenario_id} has a stale fingerprint for "
                    f"{reference.case_id}."
                )
            try:
                claim = case.gold.claims[reference.claim_index]
            except IndexError as error:
                raise ValueError(
                    f"Reasoning scenario {scenario.scenario_id} references missing claim "
                    f"{reference.claim_index} in {reference.case_id}."
                ) from error
            try:
                evidence = claim.evidence[reference.evidence_index]
            except IndexError as error:
                raise ValueError(
                    f"Reasoning scenario {scenario.scenario_id} references missing evidence "
                    f"{reference.evidence_index} in {reference.case_id}."
                ) from error

            specificity = calculate_specificity(
                has_subject=claim.subject_local_id is not None,
                object_value=claim.object_value,
                qualifiers=claim.qualifiers,
            )
            quality = calculate_evidence_quality(
                source_profile={},
                directness=evidence.directness,
                extraction_confidence=evidence.extraction_confidence,
                specificity=specificity,
                freshness=None,
            )
            source_group = evaluation_source_group(case)
            inputs.append(
                EvidenceInput(
                    link_id=uuid5(
                        NAMESPACE_URL,
                        f"{scenario.scenario_id}:{reference.case_id}:"
                        f"{reference.claim_index}:{reference.evidence_index}",
                    ),
                    stance=reference.stance,
                    independence_group=source_group,
                    quality=quality.value,
                    components={
                        "case_id": case.case_id,
                        "case_fingerprint": current_fingerprint,
                        "source_url": case.document.source_url,
                        "publisher": case.document.publisher,
                        "annotation_rationale": reference.annotation_rationale,
                        "quality_used": quality.used,
                        "quality_missing": list(quality.missing),
                    },
                    independence_reasons=(source_group,),
                )
            )
            referenced_cases.append(case)

        score = aggregate_cluster(inputs)
        passed = (
            score.label == scenario.expected_label
            and score.supporting_independent_sources
            == scenario.expected_supporting_independent_sources
        )
        results.append(
            ReasoningScenarioResult(
                scenario_id=scenario.scenario_id,
                expected_label=scenario.expected_label,
                actual_label=score.label,
                expected_supporting_independent_sources=(
                    scenario.expected_supporting_independent_sources
                ),
                actual_supporting_independent_sources=score.supporting_independent_sources,
                support_strength=score.support_strength,
                contradiction_strength=score.contradiction_strength,
                confidence=score.confidence,
                passed=passed,
                contributions=list(score.contributions),
            )
        )

    diagnostic_only = any(
        scenario.review_status != "human_verified" for scenario in scenarios
    ) or any(case.review_status != "human_verified" for case in referenced_cases)
    passed_count = sum(result.passed for result in results)
    return ReasoningEvaluationReport(
        scoring_version=SCORING_VERSION,
        diagnostic_only=diagnostic_only,
        scenarios_total=len(results),
        scenarios_passed=passed_count,
        label_accuracy=passed_count / len(results) if results else 1.0,
        results=results,
    )
