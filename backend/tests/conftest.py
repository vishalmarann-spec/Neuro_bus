import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.models import Base
from app.main import create_app


@pytest.fixture
def session_factory(tmp_path):
    database_path = tmp_path / "neuro_bus_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    yield factory
    asyncio.run(engine.dispose())


@pytest.fixture
def client(session_factory) -> Iterator[TestClient]:
    app = create_app(settings=Settings(app_env="test"), session_factory=session_factory)
    with TestClient(app) as test_client:
        yield test_client
