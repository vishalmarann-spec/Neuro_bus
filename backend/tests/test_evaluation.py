import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.extraction import validate_provenance
from app.domain.provenance import segment_passages, sha256_text
from app.evaluation.io import load_gold_cases
from app.evaluation.metrics import score_models
from app.evaluation.models import GoldCase, ModelPrediction
from app.evaluation.runner import run_case
from app.providers.models import FakeModelProvider

GOLD_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "synthetic_smoke_v1.json"
PUBLIC_PILOT_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "public_pilot_v1.json"
PUBLIC_BATCH_2_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "public_batch_2_v1.json"
PUBLIC_BATCH_3_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "public_batch_3_v1.json"
PUBLIC_BATCH_4_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "public_batch_4_v1.json"


def test_synthetic_gold_set_is_explicit_and_provenance_valid() -> None:
    cases = load_gold_cases(GOLD_PATH)

    assert len(cases) == 4
    assert all(case.fixture_type == "synthetic" for case in cases)
    assert all(case.document.source_url is None for case in cases)
    for case in cases:
        spans = segment_passages(case.document.raw_content)
        assert validate_provenance(case.gold, spans) == []


def test_public_pilot_has_verified_metadata_hashes_and_provenance() -> None:
    cases = load_gold_cases(PUBLIC_PILOT_PATH)

    assert len(cases) == 10
    assert len({case.document.source_url for case in cases}) == 10
    assert {case.document.source_type.value for case in cases} >= {
        "university",
        "government",
        "industry",
    }
    for case in cases:
        assert case.fixture_type == "public_excerpt"
        assert case.excerpt_policy == "short_public_excerpt"
        assert case.review_status == "assistant_verified"
        assert case.reviewer == "codex_web_verification"
        assert case.document.source_url is not None
        assert case.document.source_url.startswith("https://")
        assert case.document.publisher
        assert case.document.retrieved_at is not None
        assert case.reviewed_at is not None
        assert len(case.document.raw_content.split()) <= 25
        assert case.document.content_hash == sha256_text(case.document.raw_content)
        spans = segment_passages(case.document.raw_content)
        assert validate_provenance(case.gold, spans) == []


def test_second_public_batch_includes_difficult_and_negative_cases() -> None:
    cases = load_gold_cases(PUBLIC_BATCH_2_PATH)

    assert len(cases) == 10
    assert len({case.document.source_url for case in cases}) == 10
    assert sum(case.difficulty.value == "adversarial" for case in cases) == 4
    assert sum("negative_no_claim" in case.task_tags for case in cases) == 2
    for case in cases:
        assert case.review_status == "assistant_verified"
        assert case.document.content_hash == sha256_text(case.document.raw_content)
        assert len(case.document.raw_content.split()) <= 25
        assert validate_provenance(case.gold, segment_passages(case.document.raw_content)) == []


def test_third_public_batch_expands_decision_and_methodology_coverage() -> None:
    cases = load_gold_cases(PUBLIC_BATCH_3_PATH)

    assert len(cases) == 20
    assert len({case.document.source_url for case in cases}) == 20
    assert sum(case.difficulty.value == "adversarial" for case in cases) == 7
    assert sum("negative_no_claim" in case.task_tags for case in cases) == 2
    assert {tag.value for case in cases for tag in case.task_tags} >= {
        "accreditation",
        "admissions",
        "employer_demand",
        "methodology_caveat",
        "research_trend",
    }
    for case in cases:
        assert case.review_status == "assistant_verified"
        assert case.reviewer == "codex_web_verification"
        assert case.document.content_hash == sha256_text(case.document.raw_content)
        assert len(case.document.raw_content.split()) <= 25
        assert validate_provenance(case.gold, segment_passages(case.document.raw_content)) == []


def test_fourth_public_batch_reaches_selection_coverage_floor() -> None:
    cases = load_gold_cases(PUBLIC_BATCH_4_PATH)

    assert len(cases) == 60
    assert len({case.document.source_url for case in cases}) == 60
    assert sum(case.difficulty.value == "adversarial" for case in cases) == 15
    assert sum("negative_no_claim" in case.task_tags for case in cases) == 6
    assert {tag.value for case in cases for tag in case.task_tags} >= {
        "admissions",
        "curriculum",
        "employer_demand",
        "labour_market",
        "methodology_caveat",
        "negative_no_claim",
        "research_trend",
        "skills_demand",
    }
    for case in cases:
        assert case.review_status == "assistant_verified"
        assert case.reviewer == "codex_web_verification"
        assert case.document.content_hash == sha256_text(case.document.raw_content)
        assert len(case.document.raw_content.split()) <= 25
        assert validate_provenance(case.gold, segment_passages(case.document.raw_content)) == []


def test_public_case_rejects_changed_excerpt_with_stale_hash() -> None:
    payload = load_gold_cases(PUBLIC_PILOT_PATH)[0].model_dump(mode="json")
    payload["document"]["raw_content"] += " Changed."

    with pytest.raises(ValidationError, match="content_hash does not match"):
        GoldCase.model_validate(payload)


def test_public_case_rejects_missing_verification_metadata() -> None:
    payload = load_gold_cases(PUBLIC_PILOT_PATH)[0].model_dump(mode="json")
    payload["document"]["retrieved_at"] = None

    with pytest.raises(ValidationError, match="retrieved_at"):
        GoldCase.model_validate(payload)


def test_public_case_rejects_missing_task_tags() -> None:
    payload = load_gold_cases(PUBLIC_PILOT_PATH)[0].model_dump(mode="json")
    payload["task_tags"] = []

    with pytest.raises(ValidationError, match="at least one benchmark task tag"):
        GoldCase.model_validate(payload)


def test_negative_tag_and_gold_claims_are_mutually_exclusive() -> None:
    payload = load_gold_cases(PUBLIC_PILOT_PATH)[0].model_dump(mode="json")
    payload["task_tags"] = ["negative_no_claim"]

    with pytest.raises(ValidationError, match="must not contain gold claims"):
        GoldCase.model_validate(payload)


def test_public_case_rejects_excerpt_over_word_limit() -> None:
    payload = load_gold_cases(PUBLIC_PILOT_PATH)[0].model_dump(mode="json")
    payload["document"]["raw_content"] = " ".join(["word"] * 26)
    payload["document"]["content_hash"] = sha256_text(payload["document"]["raw_content"])
    payload["gold"] = {"entities": [], "claims": []}

    with pytest.raises(ValidationError, match="at most 25 words"):
        GoldCase.model_validate(payload)


def test_gold_case_rejects_invalid_mention_offsets() -> None:
    payload = load_gold_cases(PUBLIC_PILOT_PATH)[0].model_dump(mode="json")
    payload["gold"]["entities"][0]["mentions"][0]["start_offset"] = 0

    with pytest.raises(ValidationError, match="Gold provenance is invalid"):
        GoldCase.model_validate(payload)


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
