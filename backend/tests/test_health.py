"""Health probe contract: liveness is process-only, readiness checks the database."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_is_ok_without_authentication(test_app: TestClient) -> None:
    response = test_app.get("/api/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_ready_reports_the_sqlite_database(client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "connected"
    assert body["dialect"] == "sqlite"


def test_ready_is_503_when_the_database_is_unavailable(
    test_app: TestClient, auth_headers: dict[str, str]
) -> None:
    from sqlalchemy.exc import OperationalError

    from app.core.database import get_db

    class BrokenSession:
        bind = None

        def execute(self, *_args, **_kwargs):
            raise OperationalError(
                "SELECT 1", {}, Exception("connection refused")
            )

    test_app.app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = test_app.get("/api/health/ready", headers=auth_headers)
    finally:
        test_app.app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"


def test_health_is_not_an_endpoint(test_app: TestClient) -> None:
    assert test_app.get("/api/health").status_code == 404
