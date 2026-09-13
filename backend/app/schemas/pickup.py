from __future__ import annotations

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    id: str
    from_addr: str = Field(serialization_alias="from", validation_alias="from")
    to: list[str]
    subject: str
    date: str
    preview: str
    read: bool
    has_attachments: bool
    folder: str

    model_config = {"populate_by_name": True}


class PickupResponse(BaseModel):
    pickup_url: str
    alias: str
    account_key: str
    messages: list[MessageOut]
    total: int
    stale: bool = False
    fetched_at: str


class PickupBodyOut(BaseModel):
    id: str
    format: str
    body: str


class BatchPickupRequest(BaseModel):
    pickup_urls: list[str] = Field(min_length=1)
    amount: int = Field(default=25, ge=1, le=100)


class PickupResult(BaseModel):
    pickup_url: str
    alias: str | None = None
    ok: bool
    messages: list[MessageOut] = Field(default_factory=list)
    error: dict | None = None


class PickupResolveRequest(BaseModel):
    pickup_url: str


class PickupResolveOut(BaseModel):
    account_key: str
    alias: str
    account_id: int
    account_email: str
    alias_id: int
