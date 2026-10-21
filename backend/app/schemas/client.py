"""Pydantic schemas for the client workspace endpoints (docs/06_schema_api.md §6.3.5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ClientBase(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=255)
    registration_number: Optional[str] = Field(None, max_length=64)  # SSM / BRN
    sst_number: Optional[str] = Field(None, max_length=64)  # SST registration no.
    industry_category: Optional[str] = Field(None, max_length=64)


class ClientCreate(ClientBase):
    """``POST /api/clients`` body. ``accountant_id`` comes from the auth session."""


class ClientUpdate(BaseModel):
    """``PUT /api/clients/{client_id}`` body — every field optional."""

    business_name: Optional[str] = Field(None, min_length=1, max_length=255)
    registration_number: Optional[str] = Field(None, max_length=64)
    sst_number: Optional[str] = Field(None, max_length=64)
    industry_category: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None


class ClientRead(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    accountant_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClientSummary(ClientRead):
    """Client row plus the aggregates the clients list needs.

    Carrying both counts here removes the frontend's per-client receipt fetch.
    """

    unreviewed_count: int = 0
    verified_count: int = 0
    # Every receipt, whatever its status: the dashboard's "Total receipts".
    total_count: int = 0


class ClientListResponse(BaseModel):
    items: list[ClientSummary]


class HealthLiveResponse(BaseModel):
    """Process liveness: no database access."""

    status: str
    version: str


class HealthResponse(BaseModel):
    """Readiness: the API can serve traffic because the database answered."""

    status: str
    database: str
    dialect: str
    version: str


__all__ = [
    "ClientBase",
    "ClientCreate",
    "ClientListResponse",
    "ClientRead",
    "ClientSummary",
    "ClientUpdate",
    "HealthLiveResponse",
    "HealthResponse",
]
