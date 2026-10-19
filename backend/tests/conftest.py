"""Shared fixtures.

The API is exercised against the *real* session/engine wiring (``app.core.database``)
pointed at a throwaway SQLite file, so the test covers the same path as production
plus the documented SQLite fallback (docs/05_trd.md §5.1).
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

# Must precede the app imports below: app.core.database binds its engine at import time.
_TMP_DIR = tempfile.mkdtemp(prefix="kenyalang-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"
os.environ["KENYALANG_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import ACCOUNTANT_HEADER  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp_dir() -> Iterator[None]:
    yield
    engine.dispose()
    for leftover in Path(_TMP_DIR).glob("*"):
        leftover.unlink()
    os.rmdir(_TMP_DIR)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    """Create the schema once; the API lifespan would otherwise do it per test."""
    from app.models import init_db

    init_db()


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate every table after each test so cases stay order-independent."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def accountant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_accountant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_headers(accountant_id: uuid.UUID) -> dict[str, str]:
    return {ACCOUNTANT_HEADER: str(accountant_id)}


@pytest.fixture
def test_app() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def client(test_app: TestClient, auth_headers: dict[str, str]) -> TestClient:
    """TestClient pre-authenticated as ``accountant_id``."""
    test_app.headers.update(auth_headers)
    return test_app
