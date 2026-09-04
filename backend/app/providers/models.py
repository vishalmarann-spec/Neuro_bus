from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExtractionPassage:
    ordinal: int
    passage_id: UUID
    text: str


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    document_id: UUID
    title: str | None
    canonical_url: str
    passages: tuple[ExtractionPassage, ...]


class ModelProviderUnavailable(RuntimeError):
    pass


class ExtractionModelProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def extract(self, request: ExtractionRequest) -> str: ...


class DisabledModelProvider:
    provider_name = "disabled"
    model_name = "disabled"

    async def extract(self, request: ExtractionRequest) -> str:
        raise ModelProviderUnavailable(
            "No extraction model is configured. Set a provider before running extraction."
        )


class FakeModelProvider:
    """Deterministic test adapter; never enabled by production configuration."""

    provider_name = "fake"
    model_name = "fixture-v1"

    def __init__(self, raw_output: str) -> None:
        self.raw_output = raw_output
        self.call_count = 0

    async def extract(self, request: ExtractionRequest) -> str:
        self.call_count += 1
        return self.raw_output
