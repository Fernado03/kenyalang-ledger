"""Client workspace CRUD and health endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi.testclient import TestClient


ACCOUNTANT_BODY = {
    "business_name": "Kopitiam Uncle Lim",
    "registration_number": "202001012345",
    "sst_number": "W10-1808-32000018",
    "industry_category": "F&B",
}


def test_health_reports_database_connection(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_create_client_persists_and_is_retrievable(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    """The core round-trip: an accountant creates a workspace, reads it back."""
    created = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert created.status_code == 201, created.text
    created_body = created.json()

    assert created_body["business_name"] == ACCOUNTANT_BODY["business_name"]
    assert created_body["registration_number"] == "202001012345"
    assert created_body["sst_number"] == "W10-1808-32000018"
    assert created_body["industry_category"] == "F&B"
    assert created_body["is_active"] is True
    # Ownership is taken from the session, never from the request body.
    assert created_body["accountant_id"] == str(accountant_id)
    assert uuid.UUID(created_body["id"])

    fetched = client.get(f"/api/clients/{created_body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created_body


def test_create_client_requires_authentication(test_app: TestClient) -> None:
    assert test_app.post("/api/clients", json=ACCOUNTANT_BODY).status_code == 401


def test_create_client_rejects_blank_business_name(client: TestClient) -> None:
    response = client.post(
        "/api/clients", json={**ACCOUNTANT_BODY, "business_name": ""}
    )

    assert response.status_code == 422


def test_list_clients_returns_only_own_workspaces(
    client: TestClient,
    test_app: TestClient,
    accountant_id: uuid.UUID,
    other_accountant_id: uuid.UUID,
) -> None:
    mine = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert mine.status_code == 201
    theirs = test_app.post(
        "/api/clients",
        json={**ACCOUNTANT_BODY, "business_name": "Rival Hardware"},
        headers={"X-Accountant-Id": str(other_accountant_id)},
    )
    assert theirs.status_code == 201

    items = client.get("/api/clients").json()["items"]

    assert [c["id"] for c in items] == [mine.json()["id"]]
    assert all(c["accountant_id"] == str(accountant_id) for c in items)


def test_get_client_hides_other_tenants_workspaces(
    client: TestClient, test_app: TestClient, other_accountant_id: uuid.UUID
) -> None:
    theirs = test_app.post(
        "/api/clients",
        json=ACCOUNTANT_BODY,
        headers={"X-Accountant-Id": str(other_accountant_id)},
    )
    foreign_id = theirs.json()["id"]

    assert client.get(f"/api/clients/{foreign_id}").status_code == 404
    assert (
        client.put(f"/api/clients/{foreign_id}", json={"is_active": False}).status_code
        == 404
    )
    assert client.delete(f"/api/clients/{foreign_id}").status_code == 404


def test_update_client_persists_partial_changes(client: TestClient) -> None:
    client_id = client.post("/api/clients", json=ACCOUNTANT_BODY).json()["id"]

    response = client.put(
        f"/api/clients/{client_id}", json={"industry_category": "RETAIL"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["industry_category"] == "RETAIL"
    # Fields absent from the payload are left untouched.
    assert body["business_name"] == ACCOUNTANT_BODY["business_name"]
    assert body["registration_number"] == "202001012345"


def test_delete_client_is_soft_and_keeps_row(client: TestClient) -> None:
    client_id = client.post("/api/clients", json=ACCOUNTANT_BODY).json()["id"]

    assert client.delete(f"/api/clients/{client_id}").status_code == 204

    body = client.get(f"/api/clients/{client_id}").json()
    assert body["is_active"] is False


def test_client_row_survives_a_fresh_session(
    client: TestClient, test_app: TestClient, accountant_id: uuid.UUID
) -> None:
    """The saved row is durable, not request-scoped state."""
    created = client.post("/api/clients", json=ACCOUNTANT_BODY).json()

    reread = test_app.get(
        f"/api/clients/{created['id']}", headers={"X-Accountant-Id": str(accountant_id)}
    )

    assert reread.status_code == 200
    assert reread.json()["business_name"] == ACCOUNTANT_BODY["business_name"]
    assert datetime.fromisoformat(reread.json()["created_at"]).tzinfo is not None
