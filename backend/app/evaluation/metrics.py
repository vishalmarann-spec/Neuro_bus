import json
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable
from typing import TypeVar

from pydantic import ValidationError

from app.domain.extraction import (
    EntityCandidate,
    ExtractionEnvelope,
    normalized_entity_name,
    validate_provenance,
)
from app.domain.provenance import segment_passages
from app.evaluation.models import GoldCase, ModelPrediction, ModelScorecard, PRFScore

KeyT = TypeVar("KeyT", bound=Hashable)


def entity_key(entity: EntityCandidate) -> tuple[str, str]:
    return entity.entity_type.value, normalized_entity_name(entity.canonical_name)


def entity_map(extraction: ExtractionEnvelope) -> dict[str, tuple[str, str]]:
    return {entity.local_id: entity_key(entity) for entity in extraction.entities}


def claim_key(extraction: ExtractionEnvelope, index: int) -> tuple:
    claim = extraction.claims[index]
    entities = entity_map(extraction)
    subject = entities.get(claim.subject_local_id) if claim.subject_local_id else None
    return (
        subject,
        claim.predicate,
        json.dumps(claim.object_value, sort_keys=True, separators=(",", ":")),
        json.dumps(claim.qualifiers, sort_keys=True, separators=(",", ":")),
    )


def entity_keys(extraction: ExtractionEnvelope) -> Counter:
    return Counter(entity_key(entity) for entity in extraction.entities)


def mention_keys(extraction: ExtractionEnvelope) -> Counter:
    items = []
    for entity in extraction.entities:
        parent = entity_key(entity)
        for mention in entity.mentions:
            items.append(
                (
                    parent,
                    mention.passage_ordinal,
                    mention.start_offset,
                    mention.end_offset,
                    mention.surface_text,
                )
            )
    return Counter(items)


def claim_keys(extraction: ExtractionEnvelope) -> Counter:
    return Counter(claim_key(extraction, index) for index in range(len(extraction.claims)))


def evidence_keys(extraction: ExtractionEnvelope) -> Counter:
    items = []
    for index, claim in enumerate(extraction.claims):
        parent = claim_key(extraction, index)
        for evidence in claim.evidence:
            items.append((parent, evidence.passage_ordinal, evidence.stance.value))
    return Counter(items)


def counter_counts(gold: Counter, predicted: Counter) -> tuple[int, int, int]:
    true_positive = sum((gold & predicted).values())
    false_positive = sum((predicted - gold).values())
    false_negative = sum((gold - predicted).values())
    return true_positive, false_positive, false_negative


def prf(true_positive: int, false_positive: int, false_negative: int) -> PRFScore:
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = true_positive / precision_denominator if precision_denominator else 1.0
    recall = true_positive / recall_denominator if recall_denominator else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRFScore(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
    )


def _accumulate(
    totals: list[int],
    gold: ExtractionEnvelope,
    predicted: ExtractionEnvelope,
    key_function: Callable[[ExtractionEnvelope], Counter],
) -> None:
    counts = counter_counts(key_function(gold), key_function(predicted))
    for index, value in enumerate(counts):
        totals[index] += value


def score_models(
    cases: list[GoldCase],
    predictions: list[ModelPrediction],
) -> list[ModelScorecard]:
    cases_by_id = {case.case_id: case for case in cases}
    if len(cases_by_id) != len(cases):
        raise ValueError("Gold case_id values must be unique.")

    predictions_by_model: dict[str, dict[str, ModelPrediction]] = defaultdict(dict)
    for prediction in predictions:
        if prediction.case_id not in cases_by_id:
            raise ValueError(f"Prediction references unknown case {prediction.case_id}.")
        if prediction.case_id in predictions_by_model[prediction.model_id]:
            raise ValueError(
                f"Duplicate prediction for {prediction.model_id}/{prediction.case_id}."
            )
        predictions_by_model[prediction.model_id][prediction.case_id] = prediction

    scorecards: list[ModelScorecard] = []
    empty = ExtractionEnvelope()
    for model_id, model_predictions in sorted(predictions_by_model.items()):
        entity_totals = [0, 0, 0]
        mention_totals = [0, 0, 0]
        claim_totals = [0, 0, 0]
        evidence_totals = [0, 0, 0]
        valid_cases = 0

        for case in cases:
            prediction = model_predictions.get(case.case_id)
            predicted = empty
            if prediction is not None:
                try:
                    candidate = ExtractionEnvelope.model_validate_json(prediction.raw_output)
                    spans = segment_passages(case.document.raw_content)
                    if not validate_provenance(candidate, spans):
                        predicted = candidate
                        valid_cases += 1
                except ValidationError:
                    pass
            _accumulate(entity_totals, case.gold, predicted, entity_keys)
            _accumulate(mention_totals, case.gold, predicted, mention_keys)
            _accumulate(claim_totals, case.gold, predicted, claim_keys)
            _accumulate(evidence_totals, case.gold, predicted, evidence_keys)

        entity_score = prf(*entity_totals)
        mention_score = prf(*mention_totals)
        claim_score = prf(*claim_totals)
        evidence_score = prf(*evidence_totals)
        latency_values = [
            item.latency_ms for item in model_predictions.values() if item.latency_ms is not None
        ]
        input_values = [
            item.input_tokens
            for item in model_predictions.values()
            if item.input_tokens is not None
        ]
        output_values = [
            item.output_tokens
            for item in model_predictions.values()
            if item.output_tokens is not None
        ]
        cost_values = [
            item.cost_usd for item in model_predictions.values() if item.cost_usd is not None
        ]
        predicted_claim_count = claim_score.true_positive + claim_score.false_positive
        scorecards.append(
            ModelScorecard(
                model_id=model_id,
                cases_total=len(cases),
                cases_with_prediction=len(model_predictions),
                schema_and_provenance_valid_rate=(valid_cases / len(cases) if cases else 1.0),
                entity=entity_score,
                mention=mention_score,
                claim=claim_score,
                evidence_link=evidence_score,
                citation_correctness=evidence_score.precision,
                false_claim_rate=(
                    claim_score.false_positive / predicted_claim_count
                    if predicted_claim_count
                    else 0.0
                ),
                average_latency_ms=(
                    sum(latency_values) / len(latency_values) if latency_values else None
                ),
                total_input_tokens=sum(input_values) if input_values else None,
                total_output_tokens=sum(output_values) if output_values else None,
                total_cost_usd=sum(cost_values) if cost_values else None,
            )
        )
    return scorecards
