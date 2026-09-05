from pathlib import Path

import pytest

from app.evaluation.coverage import summarize_benchmark_coverage
from app.evaluation.io import load_gold_case_files

GOLD_ROOT = Path(__file__).parents[1] / "evaluation" / "gold"
PUBLIC_GOLD_PATHS = [
    GOLD_ROOT / "public_pilot_v1.json",
    GOLD_ROOT / "public_batch_2_v1.json",
    GOLD_ROOT / "public_batch_3_v1.json",
    GOLD_ROOT / "public_batch_4_v1.json",
]


def test_combined_public_corpus_has_declared_coverage() -> None:
    report = summarize_benchmark_coverage(load_gold_case_files(PUBLIC_GOLD_PATHS))

    assert report.case_count == 100
    assert report.claim_count == 91
    assert report.publisher_count == 40
    assert report.domain_count == 45
    assert report.source_type_counts == {
        "government": 26,
        "industry": 13,
        "other": 1,
        "research": 10,
        "university": 50,
    }
    assert report.negative_case_count == 10
    assert report.adversarial_case_count == 27
    assert set(report.task_tag_counts) == {
        "accreditation",
        "admissions",
        "curriculum",
        "duration",
        "education_trend",
        "employer_demand",
        "fee",
        "labour_market",
        "learning_outcome",
        "methodology_caveat",
        "negative_no_claim",
        "programme_status",
        "public_initiative",
        "research_trend",
        "skills_demand",
    }
    assert report.selection_ready
    assert report.failures == []


def test_combined_public_corpus_has_unique_cases_and_source_urls() -> None:
    cases = load_gold_case_files(PUBLIC_GOLD_PATHS)

    assert len({case.case_id for case in cases}) == 100
    assert len({case.document.source_url for case in cases}) == 100


def test_loading_multiple_gold_files_rejects_duplicate_case_ids() -> None:
    with pytest.raises(ValueError, match="unique across all input files"):
        load_gold_case_files([PUBLIC_GOLD_PATHS[0], PUBLIC_GOLD_PATHS[0]])
