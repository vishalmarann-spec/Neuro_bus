from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.domain.provenance import segment_passages
from app.evaluation.models import GoldCase, ModelPrediction
from app.providers.models import (
    ExtractionModelProvider,
    ExtractionPassage,
    ExtractionRequest,
)


async def run_case(
    provider: ExtractionModelProvider,
    case: GoldCase,
) -> ModelPrediction:
    spans = segment_passages(case.document.raw_content)
    request = ExtractionRequest(
        document_id=uuid5(NAMESPACE_URL, f"neuro-bus-evaluation:{case.case_id}"),
        title=case.document.title,
        canonical_url=case.document.source_url or f"fixture:{case.case_id}",
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
