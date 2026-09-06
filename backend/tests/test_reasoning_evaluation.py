import sys
from pathlib import Path

import pytest

from app.evaluation.io import (
    load_gold_case_files,
    load_reasoning_scenarios,
    save_reasoning_report,
)
from app.evaluation.reasoning import evaluate_reasoning_scenarios
from app.evaluation.reasoning_cli import main as reasoning_cli_main

EVALUATION_ROOT = Path(__file__).parents[1] / "evaluation"
GOLD_PATHS = sorted((EVALUATION_ROOT / "gold").glob("public_*_v1.json"))
SCENARIO_PATH = EVALUATION_ROOT / "reasoning" / "real_diagnostic_v1.json"


def test_real_source_reasoning_diagnostic_covers_expected_labels() -> None:
    scenarios = load_reasoning_scenarios(SCENARIO_PATH)
    report = evaluate_reasoning_scenarios(scenarios, load_gold_case_files(GOLD_PATHS))

    assert len(scenarios) == 4
    assert report.diagnostic_only is True
    assert report.scoring_version == "claim-confidence.v2"
    assert report.scenarios_passed == report.scenarios_total == 4
    assert report.label_accuracy == 1.0
    assert {result.actual_label.value for result in report.results} == {
        "supported",
        "well_supported",
        "disputed",
        "weak",
    }


def test_reasoning_diagnostic_rejects_stale_case_fingerprint() -> None:
    scenarios = load_reasoning_scenarios(SCENARIO_PATH)
    payload = scenarios[0].model_dump(mode="json")
    payload["evidence"][0]["case_fingerprint"] = "sha256:" + "0" * 64
    changed = type(scenarios[0]).model_validate(payload)

    with pytest.raises(ValueError, match="stale fingerprint"):
        evaluate_reasoning_scenarios([changed], load_gold_case_files(GOLD_PATHS))


def test_reasoning_diagnostic_rejects_missing_claim_reference() -> None:
    scenarios = load_reasoning_scenarios(SCENARIO_PATH)
    payload = scenarios[0].model_dump(mode="json")
    payload["evidence"][0]["claim_index"] = 99
    changed = type(scenarios[0]).model_validate(payload)

    with pytest.raises(ValueError, match="missing claim 99"):
        evaluate_reasoning_scenarios([changed], load_gold_case_files(GOLD_PATHS))


def test_reasoning_report_refuses_accidental_overwrite(tmp_path: Path) -> None:
    report = evaluate_reasoning_scenarios(
        load_reasoning_scenarios(SCENARIO_PATH), load_gold_case_files(GOLD_PATHS)
    )
    output = tmp_path / "reasoning-report.json"

    save_reasoning_report(output, report)

    with pytest.raises(FileExistsError):
        save_reasoning_report(output, report)


def test_reasoning_cli_human_gate_fails_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "must-not-exist.json"
    arguments = ["reasoning_cli"]
    for gold_path in GOLD_PATHS:
        arguments.extend(("--gold", str(gold_path)))
    arguments.extend(
        (
            "--scenarios",
            str(SCENARIO_PATH),
            "--output",
            str(output),
            "--require-human-verified",
        )
    )
    monkeypatch.setattr(sys, "argv", arguments)

    with pytest.raises(SystemExit) as captured:
        reasoning_cli_main()

    assert captured.value.code == 2
    assert not output.exists()
