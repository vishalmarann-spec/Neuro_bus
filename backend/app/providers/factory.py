from app.core.config import Settings
from app.providers.models import DisabledModelProvider, ExtractionModelProvider
from app.providers.openai_responses import OpenAIResponsesProvider


def create_model_provider(settings: Settings) -> ExtractionModelProvider:
    if settings.model_provider == "disabled":
        return DisabledModelProvider()
    if settings.model_provider == "openai":
        return OpenAIResponsesProvider(
            api_key=settings.model_api_key,
            model_name=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
            max_output_tokens=settings.model_max_output_tokens,
            input_cost_per_million_usd=settings.model_input_cost_per_million_usd,
            output_cost_per_million_usd=settings.model_output_cost_per_million_usd,
        )
    raise ValueError(f"Unsupported model provider: {settings.model_provider!r}.")
