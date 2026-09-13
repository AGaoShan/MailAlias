from __future__ import annotations

from pydantic import BaseModel, Field


class AliasCreate(BaseModel):
    address: str = Field(min_length=3, max_length=255)


class AliasOut(BaseModel):
    id: int
    account_id: int
    account_email: str
    address: str
    local_part: str
    domain: str
    display_name: str | None = None
    is_default_sender: bool
    deletable: bool
    state: str
    pickup_url: str
    created_at: str
    last_fetched_at: str | None = None


class DefaultSenderUpdate(BaseModel):
    sender: str = Field(pattern="^(email|name-email)$")


class DisplayNameUpdate(BaseModel):
    display_name: str = Field(max_length=255)
