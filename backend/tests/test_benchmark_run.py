import asyncio
from pathlib import Path

from app.evaluation.io import (
    load_benchmark_run,
    load_gold_cases,
    load_predictions,
    save_benchmark_run,
)
from app.evaluation.runner import run_benchmark_artifact
from app.providers.models import (
    ExtractionModelResponse,
    ExtractionRequest,
    ModelProviderUnavailable,
)

GOLD_PATH = Path(__file__).parents[1] / "evaluation" / "gold" / "public_pilot_v1.json"


class PartiallyFailingProvider:
    provider_name = "test-provider"
    model_name = "test-model"
    prompt_version = "claim-extractor.test.v1"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, request: ExtractionRequest) -> ExtractionModelResponse:
        self.calls += 1
        if self.calls == 2:
            raise ModelProviderUnavailable("Temporary test outage.")
        return ExtractionModelResponse(
            raw_output='{"entities":[],"claims":[]}',
            input_tokens=20,
            output_tokens=5,
        )


def test_benchmark_run_preserves_results_failures_and_fingerprints(tmp_path: Path) -> None:
    cases = load_gold_cases(GOLD_PATH)[:2]
    artifact = asyncio.run(
        run_benchmark_artifact(
            PartiallyFailingProvider(),
            cases,
            diagnostic_only=True,
            pricing_basis="Test rates only.",
        )
    )
    output = tmp_path / "run.json"

    save_benchmark_run(output, artifact)
    loaded = load_benchmark_run(output)

    assert loaded.provider == "test-provider"
    assert loaded.model == "test-model"
    assert loaded.prompt_version == "claim-extractor.test.v1"
    assert loaded.diagnostic_only
    assert set(loaded.case_fingerprints) == {case.case_id for case in cases}
    assert len(loaded.predictions) == 1
    assert len(loaded.failures) == 1
    assert loaded.failures[0].error_code == "provider_unavailable"
    assert load_predictions(output) == loaded.predictions


def test_benchmark_run_refuses_to_overwrite_existing_artifact(tmp_path: Path) -> None:
    artifact = asyncio.run(
        run_benchmark_artifact(
            PartiallyFailingProvider(),
            load_gold_cases(GOLD_PATH)[:1],
            diagnostic_only=True,
        )
    )
    output = tmp_path / "run.json"

    save_benchmark_run(output, artifact)

    try:
        save_benchmark_run(output, artifact)
    except FileExistsError:
        pass
    else:
        raise AssertionError("save_benchmark_run should fail closed on an existing file")
