from collections.abc import Awaitable, Callable

from sqlalchemy import text

from app.core.database import SessionFactory
from app.domain.health import DependencyState

ReadinessProbe = Callable[[], Awaitable[list[DependencyState]]]


async def unconfigured_probe() -> list[DependencyState]:
    """Be explicit until database and Redis adapters provide real probes."""

    return [
        DependencyState(
            name="postgres",
            status="not_checked",
            detail="Database adapter is the next implementation slice.",
        ),
        DependencyState(
            name="redis",
            status="not_checked",
            detail="Worker adapter is not configured yet.",
        ),
    ]


def database_probe(session_factory: SessionFactory) -> ReadinessProbe:
    async def probe() -> list[DependencyState]:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:  # dependency errors vary by database driver
            return [
                DependencyState(
                    name="postgres",
                    status="unavailable",
                    detail=type(exc).__name__,
                )
            ]
        return [DependencyState(name="postgres", status="available")]

    return probe
