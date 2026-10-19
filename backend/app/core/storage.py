"""Tenant-scoped receipt blob storage (docs/05_trd.md §5.6.1).

Files land under ``<root>/tenants/{client_id}/{receipt_id}{ext}`` so a tenant's
receipts are physically partitioned, mirroring the ``storage_path`` column format
(``'tenants/{client_id}/{receipt_id}.webp'``) in docs/06_schema_api.md §6.1.2.

The client-supplied filename is never used to build the path -- only its
extension is, after sanitizing -- so a crafted upload name cannot escape the
tenant directory.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Final
from uuid import UUID

STORAGE_ROOT_ENV: Final = "KENYALANG_STORAGE_ROOT"
DEFAULT_STORAGE_ROOT: Final = "storage"

_EXTENSION_RE: Final = re.compile(r"^\.[a-z0-9]{1,8}$")


def storage_root() -> Path:
    """Resolve the blob root; overridable for tests and container volumes."""
    return Path(os.getenv(STORAGE_ROOT_ENV, "").strip() or DEFAULT_STORAGE_ROOT)


def safe_extension(filename: str) -> str:
    """Derive a filesystem-safe extension from an upload name, defaulting to ``.bin``."""
    extension = Path(filename or "").suffix.lower()
    return extension if _EXTENSION_RE.match(extension) else ".bin"


def safe_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize a client-supplied filename for persistence as metadata.

    Strips either platform's path separators and controls; caps metadata at 255 characters.
    """
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable())
    return name[: min(max_length, 255)] or "receipt"


def receipt_storage_path(client_id: UUID, receipt_id: UUID, filename: str) -> str:
    """Relative storage path for a receipt blob, as persisted in ``receipts.storage_path``."""
    return f"tenants/{client_id}/{receipt_id}{safe_extension(filename)}"


def save_receipt_file(
    client_id: UUID, receipt_id: UUID, filename: str, payload: bytes
) -> str:
    """Write the upload to tenant storage and return its relative path.

    Written to a temp name and atomically renamed so a crash mid-write cannot
    leave a truncated file that later looks like a valid receipt.
    """
    relative = receipt_storage_path(client_id, receipt_id, filename)
    destination = storage_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        temporary.write_bytes(payload)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return relative


def delete_receipt_file(relative_path: str) -> None:
    """Remove a stored blob, ignoring an already-missing file."""
    (storage_root() / relative_path).unlink(missing_ok=True)


def load_receipt_file(relative_path: str) -> bytes:
    """Read a stored blob by its relative path, refusing to escape the root.

    The path originates from the database, but it is still validated: a corrupted
    or tampered ``storage_path`` must never become an arbitrary file read.
    """
    root = storage_root().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("receipt path escapes the storage root")
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate.read_bytes()


__all__ = [
    "DEFAULT_STORAGE_ROOT",
    "STORAGE_ROOT_ENV",
    "delete_receipt_file",
    "load_receipt_file",
    "receipt_storage_path",
    "safe_extension",
    "safe_filename",
    "save_receipt_file",
    "storage_root",
]
