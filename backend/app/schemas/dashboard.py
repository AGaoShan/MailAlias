from __future__ import annotations

from pydantic import BaseModel


class AliasCapacity(BaseModel):
    used: int
    limit: int


class RecentFetch(BaseModel):
    pickup_url: str
    alias: str
    message_count: int
    fetched_at: str


class DashboardStats(BaseModel):
    account_count: int
    alias_count: int
    mapping_count: int
    alias_capacity: AliasCapacity
    recent_fetches: list[RecentFetch]
