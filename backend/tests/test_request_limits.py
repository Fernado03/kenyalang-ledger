"""Request body cap (H4, docs/05_trd.md §5.6.2).

The upload route's own ``MAX_FILE_BYTES`` check runs *after* the multipart body
has been buffered and *after* authentication, so an unauthenticated caller could
stream an arbitrarily large body into the process. The cap has to sit in front
of routing, which is what ``BodyLimitMiddleware`` does.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import MAX_REQUEST_BYTES, BodyLimitMiddleware


def test_oversized_content_length_is_rejected_before_routing(
    client: TestClient,
) -> None:
    """A declared length over the cap is refused without reading the body.

    The path is a real upload route with a valid-looking client id, so the only
    reason to reject is the size — not a 404 or a missing auth header.
    """
    response = client.post(
        "/api/v1/clients/00000000-0000-0000-0000-000000000000/receipts/upload",
        headers={"content-length": str(MAX_REQUEST_BYTES + 1)},
        content=b"",
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_oversized_request_is_rejected_without_authentication(
    client: TestClient,
) -> None:
    """The cap is outermost: it does not depend on the auth dependency."""
    response = client.post(
        "/api/v1/clients/00000000-0000-0000-0000-000000000000/receipts/upload",
        headers={
            "content-length": str(MAX_REQUEST_BYTES + 1),
            # Deliberately no ACCOUNTANT_HEADER.
        },
        content=b"",
    )

    # 401 would mean auth ran first; the cap must win.
    assert response.status_code == 413


def test_invalid_content_length_is_a_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/clients/00000000-0000-0000-0000-000000000000/receipts/upload",
        headers={"content-length": "not-a-number"},
        content=b"",
    )

    assert response.status_code == 400


def test_normal_requests_are_unaffected(client: TestClient) -> None:
    """Small bodies still route normally — the middleware is not a blanket block."""
    response = client.get("/api/health/live")

    assert response.status_code == 200


def test_small_upload_reaches_the_route(client: TestClient) -> None:
    """A realistic upload is not rejected by the cap.

    The route answers 401/404/422 for a bogus client, all of which prove it was
    reached; a 413 would mean the middleware misfired.
    """
    response = client.post(
        "/api/v1/clients/00000000-0000-0000-0000-000000000000/receipts/upload",
        files=[("files", ("a.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"))],
    )

    assert response.status_code != 413


def test_streamed_body_without_content_length_is_counted() -> None:
    """A chunked request cannot dodge the cap by omitting Content-Length."""
    seen: dict[str, object] = {}

    async def app(scope, receive, send):
        # Drain the body the way a real endpoint would.
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        seen["read"] = True

    middleware = BodyLimitMiddleware(app, max_bytes=8)

    import asyncio

    async def run() -> None:
        chunks = iter(
            [
                {"type": "http.request", "body": b"0123456789", "more_body": True},
                {"type": "http.request", "body": b"", "more_body": False},
            ]
        )

        async def receive():
            return next(chunks)

        async def send(message):
            seen.setdefault("messages", []).append(message)

        await middleware({"type": "http"}, receive, send)

    asyncio.run(run())

    # The body never finished being read, and the caller got a 413.
    assert "read" not in seen
    messages = seen["messages"]
    assert messages[0]["status"] == 413
