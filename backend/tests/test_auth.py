"""Demo identity guard (``app.core.auth``) and the production startup refusal.

The ``X-Accountant-Id`` header is a forgeable demo identity, not authentication:
it is only honoured while ``KENYALANG_ENV`` is ``local`` or ``test``. These tests
pin that contract, including the factory's refusal to boot in production.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.auth import ACCOUNTANT_HEADER


def test_missing_accountant_header_is_401(test_app: TestClient) -> None:
    response = test_app.get("/api/clients")

    assert response.status_code == 401
    assert ACCOUNTANT_HEADER in response.json()["detail"]


def test_malformed_accountant_header_is_401(test_app: TestClient) -> None:
    response = test_app.get("/api/clients", headers={ACCOUNTANT_HEADER: "nope"})

    assert response.status_code == 401


def test_valid_uuid_header_lists_clients(
    test_app: TestClient, accountant_id: uuid.UUID
) -> None:
    response = test_app.get(
        "/api/clients", headers={ACCOUNTANT_HEADER: str(accountant_id)}
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.parametrize("environment", [None, "staging"])
def test_demo_auth_is_disabled_outside_local_and_test(
    test_app: TestClient,
    accountant_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
) -> None:
    if environment is None:
        monkeypatch.delenv("KENYALANG_ENV", raising=False)
    else:
        monkeypatch.setenv("KENYALANG_ENV", environment)

    response = test_app.get(
        "/api/clients", headers={ACCOUNTANT_HEADER: str(accountant_id)}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Demo authentication is disabled"


def test_create_app_refuses_to_run_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Imported lazily so importing this module never builds an app.
    from app.main import create_app

    monkeypatch.setenv("KENYALANG_ENV", "production")

    with pytest.raises(RuntimeError, match="must not run in production"):
        create_app()
