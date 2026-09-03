from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.health import DependencyState
from app.main import create_app
from app.services.readiness import unconfigured_probe


def test_liveness_returns_service_identity() -> None:
    app = create_app(
        settings=Settings(app_env="test", app_name="Test Neuro_Bus", app_version="test-version")
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "Test Neuro_Bus",
        "version": "test-version",
    }


def test_readiness_is_honest_before_adapters_exist() -> None:
    app = create_app(settings=Settings(app_env="test"), readiness_probe=unconfigured_probe)

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert {item["status"] for item in response.json()["dependencies"]} == {"not_checked"}


def test_readiness_succeeds_when_required_dependencies_are_available() -> None:
    async def available_probe() -> list[DependencyState]:
        return [
            DependencyState(name="postgres", status="available"),
            DependencyState(name="redis", status="available"),
        ]

    app = create_app(settings=Settings(app_env="test"), readiness_probe=available_probe)

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
