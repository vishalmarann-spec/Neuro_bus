from datetime import UTC, datetime
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.domain.provenance import segment_passages
from app.evaluation.models import (
    BenchmarkRunArtifact,
    BenchmarkRunFailure,
    GoldCase,
    ModelPrediction,
)
from app.evaluation.review import gold_case_fingerprint
from app.providers.models import (
    ExtractionModelProvider,
    ExtractionPassage,
    ExtractionRequest,
    ModelProviderUnavailable,
)


async def run_case(
    provider: ExtractionModelProvider,
    case: GoldCase,
) -> ModelPrediction:
    spans = segment_passages(case.document.raw_content)
    request = ExtractionRequest(
        document_id=uuid5(NAMESPACE_URL, f"neuro-bus-evaluation:{case.case_id}"),
        title=case.document.title,
        canonical_url=str(case.document.source_url or f"fixture:{case.case_id}"),
        passages=tuple(
            ExtractionPassage(
                ordinal=span.ordinal,
                passage_id=uuid5(NAMESPACE_URL, f"{case.case_id}:passage:{span.ordinal}"),
                text=span.exact_text,
            )
            for span in spans
        ),
    )
    started = perf_counter()
    response = await provider.extract(request)
    elapsed_ms = round((perf_counter() - started) * 1_000)
    return ModelPrediction(
        case_id=case.case_id,
        model_id=f"{provider.provider_name}/{provider.model_name}",
        raw_output=response.raw_output,
        latency_ms=elapsed_ms,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
    )


async def run_benchmark(
    provider: ExtractionModelProvider,
    cases: list[GoldCase],
) -> list[ModelPrediction]:
    return [await run_case(provider, case) for case in cases]


async def run_benchmark_artifact(
    provider: ExtractionModelProvider,
    cases: list[GoldCase],
    *,
    diagnostic_only: bool,
    pricing_basis: str | None = None,
) -> BenchmarkRunArtifact:
    started_at = datetime.now(UTC)
    predictions: list[ModelPrediction] = []
    failures: list[BenchmarkRunFailure] = []
    for case in cases:
        case_started = perf_counter()
        try:
            predictions.append(await run_case(provider, case))
        except ModelProviderUnavailable as error:
            failures.append(
                BenchmarkRunFailure(
                    case_id=case.case_id,
                    error_code="provider_unavailable",
                    message=str(error),
                    latency_ms=round((perf_counter() - case_started) * 1_000),
                )
            )
        except Exception as error:  # provider-specific failures must not leak details
            failures.append(
                BenchmarkRunFailure(
                    case_id=case.case_id,
                    error_code="provider_error",
                    message=f"Provider failed with {type(error).__name__}.",
                    latency_ms=round((perf_counter() - case_started) * 1_000),
                )
            )

    return BenchmarkRunArtifact(
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=provider.prompt_version,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        diagnostic_only=diagnostic_only,
        pricing_basis=pricing_basis,
        case_fingerprints={case.case_id: gold_case_fingerprint(case) for case in cases},
        predictions=predictions,
        failures=failures,
    )
