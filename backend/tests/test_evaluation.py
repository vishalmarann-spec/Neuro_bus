import asyncio
from pathlib import Path

from app.domain.extraction import validate_provenance
from app.domain.provenance import segment_passages
from app.evaluation.io import load_gold_cases
from app.evaluation.metrics import score_models
from app.evaluation.models import ModelPrediction
from app.evaluation.runner import run_case
from app.providers.models import FakeModelProvider

GOLD_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "synthetic_smoke_v1.json"


def test_synthetic_gold_set_is_explicit_and_provenance_valid() -> None:
    cases = load_gold_cases(GOLD_PATH)

    assert len(cases) == 4
    assert all(case.fixture_type == "synthetic" for case in cases)
    assert all(case.document.source_url is None for case in cases)
    for case in cases:
        spans = segment_passages(case.document.raw_content)
        assert validate_provenance(case.gold, spans) == []


def test_perfect_predictions_receive_perfect_quality_scores() -> None:
    cases = load_gold_cases(GOLD_PATH)
    predictions = [
        ModelPrediction(
            case_id=case.case_id,
            model_id="fixture/perfect",
            raw_output=case.gold.model_dump_json(),
            latency_ms=100 + index,
            input_tokens=200,
            output_tokens=100,
            cost_usd=0.001,
        )
        for index, case in enumerate(cases)
    ]

    scorecard = score_models(cases, predictions)[0]

    assert scorecard.schema_and_provenance_valid_rate == 1.0
    assert scorecard.entity.f1 == 1.0
    assert scorecard.mention.f1 == 1.0
    assert scorecard.claim.f1 == 1.0
    assert scorecard.citation_correctness == 1.0
    assert scorecard.false_claim_rate == 0.0
    assert scorecard.total_input_tokens == 800
    assert scorecard.total_output_tokens == 400
    assert scorecard.total_cost_usd == 0.004


def test_invalid_and_missing_predictions_reduce_validity_and_recall() -> None:
    cases = load_gold_cases(GOLD_PATH)
    predictions = [
        ModelPrediction(
            case_id=cases[0].case_id,
            model_id="fixture/invalid",
            raw_output='{"entities": "invalid", "claims": []}',
        )
    ]

    scorecard = score_models(cases, predictions)[0]

    assert scorecard.cases_with_prediction == 1
    assert scorecard.schema_and_provenance_valid_rate == 0.0
    assert scorecard.entity.recall == 0.0
    assert scorecard.claim.recall == 0.0


def test_runner_records_provider_usage_metadata() -> None:
    case = load_gold_cases(GOLD_PATH)[0]
    provider = FakeModelProvider(
        case.gold.model_dump_json(),
        input_tokens=250,
        output_tokens=90,
        cost_usd=0.002,
    )

    prediction = asyncio.run(run_case(provider, case))

    assert prediction.model_id == "fake/fixture-v1"
    assert prediction.case_id == case.case_id
    assert prediction.input_tokens == 250
    assert prediction.output_tokens == 90
    assert prediction.cost_usd == 0.002
    assert provider.call_count == 1
