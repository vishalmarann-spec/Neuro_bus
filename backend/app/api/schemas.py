from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.core.models import QuestionStatus, RunState, SourceType


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    vertical: str = Field(default="university", min_length=1, max_length=80)

    @field_validator("name", "vertical")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProjectRead(APIModel):
    id: UUID
    name: str
    vertical: str
    created_at: datetime


class QuestionCreate(APIModel):
    text: str = Field(min_length=3)
    scope: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class QuestionRead(APIModel):
    id: UUID
    project_id: UUID
    text: str
    scope: dict[str, Any]
    status: QuestionStatus
    created_at: datetime


class RunCreate(APIModel):
    pipeline_version: str = Field(default="storage.v1", min_length=1, max_length=64)


class RunRead(APIModel):
    id: UUID
    question_id: UUID
    state: RunState
    pipeline_version: str
    metrics: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DocumentCapture(APIModel):
    url: HttpUrl
    publisher: str = Field(min_length=1, max_length=255)
    source_type: SourceType = SourceType.OTHER
    title: str | None = Field(default=None, max_length=500)
    raw_content: str = Field(min_length=1)
    published_at: datetime | None = None

    @field_validator("publisher", "raw_content")
    @classmethod
    def preserve_content_but_reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class SourceRead(APIModel):
    id: UUID
    canonical_domain: str
    publisher: str
    source_type: SourceType
    trust_profile: dict[str, Any]
    created_at: datetime


class PassageRead(APIModel):
    id: UUID
    document_id: UUID
    ordinal: int
    start_offset: int
    end_offset: int
    exact_text: str
    text_hash: str


class DocumentRead(APIModel):
    id: UUID
    run_id: UUID
    source_id: UUID
    original_url: str
    canonical_url: str
    title: str | None
    content_hash: str
    retrieved_at: datetime
    published_at: datetime | None
    parser_version: str


class DocumentCaptureRead(APIModel):
    source: SourceRead
    document: DocumentRead
    passages: list[PassageRead]
    duplicate: bool

