from typing import Literal

from pydantic import BaseModel


class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"
    service: str
    version: str


class DependencyState(BaseModel):
    name: str
    status: Literal["available", "unavailable", "not_checked"]
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyState]
