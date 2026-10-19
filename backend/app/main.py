"""ASGI application factory for Kenyalang Ledger."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.clients import API_VERSION, router as clients_router
from app.api.exports import router as exports_router
from app.api.receipts import router as receipts_router
from app.models import init_db

DESCRIPTION = (
    "Invoice and receipt digitizer for Malaysian micro-SMEs and accountants. "
    "Schema and API contracts: docs/06_schema_api.md."
)

INIT_DB_ATTEMPTS = 5
INIT_DB_DELAY_SECONDS = 1.0


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
        except Exception as exc:  # noqa: BLE001 - retried below, re-raised if final
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
        return response


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

    app.include_router(clients_router, prefix="/api")
    # Receipt ingestion lives under the documented /api/v1 prefix (§6.3.1); the
    # client routes above predate it and stay where step 1 put them.
    app.include_router(receipts_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
    return app


app = create_app()
