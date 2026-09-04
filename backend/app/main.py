from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes.extraction import router as extraction_router
from app.api.routes.health import router as health_router
from app.api.routes.reasoning import router as reasoning_router
from app.api.routes.storage import router as storage_router
from app.core.config import Settings, get_settings
from app.core.database import SessionFactory, create_database
from app.providers.models import DisabledModelProvider, ExtractionModelProvider
from app.services.readiness import ReadinessProbe, database_probe


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    session_factory: SessionFactory | None = None,
    model_provider: ExtractionModelProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    owned_engine: AsyncEngine | None = None
    if session_factory is None:
        owned_engine, resolved_session_factory = create_database(resolved_settings.database_url)
    else:
        resolved_session_factory = session_factory

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.session_factory = resolved_session_factory
        app.state.readiness_probe = readiness_probe or database_probe(resolved_session_factory)
        app.state.model_provider = model_provider or DisabledModelProvider()
        try:
            yield
        finally:
            if owned_engine is not None:
                await owned_engine.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Traceable, confidence-aware evidence intelligence.",
        lifespan=lifespan,
    )
    application.include_router(health_router, prefix=resolved_settings.api_v1_prefix)
    application.include_router(storage_router, prefix=resolved_settings.api_v1_prefix)
    application.include_router(extraction_router, prefix=resolved_settings.api_v1_prefix)
    application.include_router(reasoning_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
