from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.services.readiness import ReadinessProbe, unconfigured_probe


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.readiness_probe = readiness_probe or unconfigured_probe
        yield

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Traceable, confidence-aware evidence intelligence.",
        lifespan=lifespan,
    )
    application.include_router(health_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
