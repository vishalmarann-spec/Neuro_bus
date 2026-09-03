from collections.abc import Awaitable, Callable

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

