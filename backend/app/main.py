"""ASGI application factory for Kenyalang Ledger."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.clients import API_VERSION
from app.api.clients import router as clients_router
from app.api.dashboard import router as dashboard_router
from app.api.exports import router as exports_router
from app.api.receipts import router as receipts_router
from app.models import init_db

DESCRIPTION = (
    "Invoice and receipt digitizer for Malaysian micro-SMEs and accountants. "
    "Schema and API contracts: docs/06_schema_api.md."
)

INIT_DB_ATTEMPTS = 5
INIT_DB_DELAY_SECONDS = 1.0

# docs/05_trd.md §5.6.2: 50MB ceiling for a whole upload request. The upload
# route re-checks per file, but only after the body has been buffered and the
# caller authenticated, so the cap has to exist in front of the app as well.
MAX_REQUEST_BYTES = 50 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create the schema, tolerating a database that is still starting up.

    There are no migrations in this demo: ``init_db`` runs ``create_all`` plus
    additive guards. A local Postgres can accept connections a moment after the
    API container starts, so retry briefly rather than crash-looping.
    """
    last_error: Exception | None = None
    for attempt in range(1, INIT_DB_ATTEMPTS + 1):
        try:
            init_db()
            break
        except Exception as exc:
            last_error = exc
            if attempt == INIT_DB_ATTEMPTS:
                raise
            await asyncio.sleep(INIT_DB_DELAY_SECONDS)
    else:  # pragma: no cover - loop always breaks or raises
        raise RuntimeError("database initialization failed") from last_error
    yield
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforce production security headers on every response (§5 Transport & headers)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none';"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "private, no-store"
        return response


class BodyLimitMiddleware:
    """Reject oversized request bodies before routing, auth or buffering.

    FastAPI only sees a file's size after ``UploadFile`` has spooled the whole
    multipart body, and the upload route's own ``MAX_FILE_BYTES`` check runs
    after authentication. That ordering lets an unauthenticated caller stream
    an arbitrarily large body into the process (H4). This middleware runs
    outermost, so it rejects on the ``Content-Length`` header before any of that
    work happens, and also counts the bytes actually received so a chunked
    request with no declared length cannot slip through.

    Implemented as pure ASGI rather than ``BaseHTTPMiddleware``: the latter
    wraps ``receive`` in a queue and would still let Starlette pull the body
    through before the rejection is observed.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                await _send_plain(send, 400, "invalid Content-Length")
                return
            if length > self.max_bytes:
                await _send_plain(send, 413, "request body too large")
                return

        received = 0
        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            # If the route already started a response, the status line is gone
            # and there is nothing honest left to send; otherwise report 413.
            if not started:
                await _send_plain(send, 413, "request body too large")


class _BodyTooLarge(Exception):
    """Internal signal: the streamed body exceeded the cap."""


async def _send_plain(send: Send, status_code: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def create_app() -> FastAPI:
    if os.getenv("KENYALANG_ENV", "").strip().lower() == "production":
        raise RuntimeError("Kenyalang Ledger demo auth must not run in production")

    app = FastAPI(
        title="Kenyalang Ledger API",
        description=DESCRIPTION,
        version=API_VERSION,
        lifespan=lifespan,
    )

    # Production security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS configuration
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "KENYALANG_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Added last => outermost, so an oversized body is rejected before CORS,
    # routing, auth or any buffering happens.
    app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

    app.include_router(clients_router, prefix="/api")
    # Receipt ingestion lives under the documented /api/v1 prefix (§6.3.1); the
    # client routes above predate it and stay where step 1 put them.
    app.include_router(receipts_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    return app


app = create_app()
