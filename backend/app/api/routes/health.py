from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings
from app.domain.health import LiveResponse, ReadyResponse
from app.services.readiness import ReadinessProbe

router = APIRouter(prefix="/health", tags=["system"])


def get_readiness_probe(request: Request) -> ReadinessProbe:
    return request.app.state.readiness_probe


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/live", response_model=LiveResponse)
async def live(settings: Annotated[Settings, Depends(get_app_settings)]) -> LiveResponse:
    return LiveResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready(
    response: Response,
    probe: Annotated[ReadinessProbe, Depends(get_readiness_probe)],
) -> ReadyResponse:
    dependencies = await probe()
    is_ready = bool(dependencies) and all(item.status == "available" for item in dependencies)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=dependencies,
    )
