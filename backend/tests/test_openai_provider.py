import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.providers.factory import create_model_provider
from app.providers.models import (
    DisabledModelProvider,
    ExtractionPassage,
    ExtractionRequest,
    ModelProviderUnavailable,
)
from app.providers.openai_responses import OpenAIResponsesProvider


def extraction_request(
    text: str = "Example University offers a data science programme.",
) -> ExtractionRequest:
    return ExtractionRequest(
        document_id=uuid4(),
        title="Data Science Programme",
        canonical_url="https://example.edu/data-science",
        passages=(ExtractionPassage(ordinal=0, passage_id=uuid4(), text=text),),
    )


def completed_response(raw_output: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": raw_output}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 25, "total_tokens": 125},
        },
    )


def test_openai_provider_uses_json_mode_and_records_usage_without_storing() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["client_request_id"] = request.headers["X-Client-Request-Id"]
        captured["body"] = json.loads(request.content)
        return completed_response('{"entities":[],"claims":[]}')

    provider = OpenAIResponsesProvider(
        api_key="test-secret-key",
        model_name="test-model",
        input_cost_per_million_usd=2.0,
        output_cost_per_million_usd=8.0,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.extract(extraction_request()))

    assert captured["authorization"] == "Bearer test-secret-key"
    assert captured["client_request_id"]
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["store"] is False
    assert captured["body"]["text"] == {"format": {"type": "json_object"}}
    assert "untrusted source data" in captured["body"]["instructions"]
    assert json.loads(captured["body"]["input"])["passages"][0]["ordinal"] == 0
    assert result.raw_output == '{"entities":[],"claims":[]}'
    assert result.input_tokens == 100
    assert result.output_tokens == 25
    assert result.cost_usd == pytest.approx(0.0004)
    assert "test-secret-key" not in repr(provider)


def test_openai_provider_http_failure_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret provider detail"}})

    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model_name="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelProviderUnavailable, match="HTTP 401") as captured:
        asyncio.run(provider.extract(extraction_request()))

    assert "secret provider detail" not in str(captured.value)


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"status": "incomplete", "output": []}, "did not complete"),
        (
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "not available"}],
                    }
                ],
            },
            "refused",
        ),
    ],
)
def test_openai_provider_rejects_incomplete_and_refused_outputs(
    payload: dict,
    expected: str,
) -> None:
    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model_name="test-model",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ModelProviderUnavailable, match=expected):
        asyncio.run(provider.extract(extraction_request()))


def test_provider_factory_defaults_disabled_and_requires_openai_configuration() -> None:
    assert isinstance(create_model_provider(Settings(app_env="test")), DisabledModelProvider)

    with pytest.raises(ValueError, match="API key"):
        create_model_provider(
            Settings(app_env="test", model_provider="openai", model_name="test-model")
        )

    with pytest.raises(ValueError, match="model name"):
        create_model_provider(
            Settings(app_env="test", model_provider="openai", model_api_key="test-key")
        )
