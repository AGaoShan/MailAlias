from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class AccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AccountOut(BaseModel):
    id: int
    account_key: str
    email: str
    enabled: bool
    alias_count: int
    alias_limit: int
    session_state: str
    created_at: str
    updated_at: str


class AccountVerifyOut(BaseModel):
    account_id: int
    session_state: str
    ok: bool


class DomainsOut(BaseModel):
    account_id: int
    domains: list[str]
