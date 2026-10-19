"""Client workspace CRUD and health endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app.models.receipt import ReceiptStatus


ACCOUNTANT_BODY = {
    "business_name": "Kopitiam Uncle Lim",
    "registration_number": "202001012345",
    "sst_number": "W10-1808-32000018",
    "industry_category": "F&B",
}


def test_health_live_reports_process_without_authentication(
    test_app: TestClient,
) -> None:
    response = test_app.get("/api/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_health_ready_reports_database_connection(client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_health_ready_is_503_when_the_database_is_broken(
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


def _insert_receipt(client_id: str, status: ReceiptStatus) -> None:
    import uuid as _uuid

    from app.core.database import SessionLocal
    from app.models.receipt import Receipt

    with SessionLocal() as db:
        db.add(
            Receipt(
                id=_uuid.uuid4(),
                client_id=_uuid.UUID(client_id),
                original_filename="receipt.jpg",
                storage_path=f"tenants/{client_id}/receipt.jpg",
                mime_type="image/jpeg",
                file_size_bytes=64,
                status=status,
            )
        )
        db.commit()


def test_list_clients_counts_receipts_by_review_state(client: TestClient) -> None:
    client_id = client.post("/api/clients", json=ACCOUNTANT_BODY).json()["id"]
    for status in (
        ReceiptStatus.STATUS_NEEDS_REVIEW,
        ReceiptStatus.STATUS_AUTO_VERIFIED,
        ReceiptStatus.STATUS_VERIFIED,
        ReceiptStatus.STATUS_REJECTED,
    ):
        _insert_receipt(client_id, status)

    items = client.get("/api/clients").json()["items"]

    assert len(items) == 1
    assert items[0]["id"] == client_id
    assert items[0]["unreviewed_count"] == 1
    assert items[0]["verified_count"] == 2


def test_list_clients_counts_do_not_leak_across_workspaces(
    client: TestClient,
) -> None:
    """The grouped query must attribute each count to its own client."""
    busy_id = client.post("/api/clients", json=ACCOUNTANT_BODY).json()["id"]
    quiet_id = client.post(
        "/api/clients", json={**ACCOUNTANT_BODY, "business_name": "Quiet Shop"}
    ).json()["id"]

    for _ in range(3):
        _insert_receipt(busy_id, ReceiptStatus.STATUS_NEEDS_REVIEW)
    _insert_receipt(busy_id, ReceiptStatus.STATUS_AUTO_VERIFIED)
    _insert_receipt(quiet_id, ReceiptStatus.STATUS_NEEDS_REVIEW)
    _insert_receipt(quiet_id, ReceiptStatus.STATUS_VERIFIED)
    _insert_receipt(quiet_id, ReceiptStatus.STATUS_VERIFIED)

    items = {item["id"]: item for item in client.get("/api/clients").json()["items"]}

    assert items[busy_id]["unreviewed_count"] == 3
    assert items[busy_id]["verified_count"] == 1
    assert items[quiet_id]["unreviewed_count"] == 1
    assert items[quiet_id]["verified_count"] == 2
