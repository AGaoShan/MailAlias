from __future__ import annotations

from pydantic import BaseModel


class MappingItem(BaseModel):
    alias_id: int
    account_id: int
    account_email: str
    alias_address: str
    pickup_url: str
    is_default_sender: bool
    last_fetched_at: str | None = None


class MappingListResponse(BaseModel):
    total: int
    items: list[MappingItem]
