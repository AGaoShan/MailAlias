from __future__ import annotations

from pydantic import BaseModel, Field


class AliasCreate(BaseModel):
    address: str = Field(min_length=3, max_length=255)


class AliasAutoCreate(BaseModel):
    """自动选号创建：只需别名（可含 @域名），后端自动挑还有额度的账号。"""

    address: str = Field(
        min_length=3,
        max_length=255,
        description="别名邮箱地址，如 my-alias@mail.com；或仅前缀 my-alias（默认 mail.com）",
    )
    account_id: int | None = Field(default=None, description="可选：指定账号，不填则自动选择")


class AliasBatchGenerate(BaseModel):
    """按数量随机生成并批量创建别名。"""

    count: int = Field(ge=1, le=100, description="要生成的数量")
    domain: str = Field(default="mail.com", description="后缀域名")
    account_id: int | None = Field(default=None, description="可选：指定账号，不填则自动分配")
    prefix: str = Field(default="", max_length=20, description="可选：固定前缀，便于识别")
    length: int = Field(default=10, ge=6, le=40, description="随机部分的长度")


class AliasBatchItem(BaseModel):
    address: str
    ok: bool
    alias: AliasOut | None = None
    error: dict | None = None


class AliasBatchResult(BaseModel):
    requested: int
    created: int
    failed: int
    items: list[AliasBatchItem]


class AliasDeleteRequest(BaseModel):
    alias_ids: list[int] = Field(min_length=1, description="要删除的别名 ID 列表")


class AliasDeleteItem(BaseModel):
    alias_id: int
    address: str
    ok: bool
    error: dict | None = None


class AliasDeleteResult(BaseModel):
    requested: int
    deleted: int
    failed: int
    items: list[AliasDeleteItem]


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
