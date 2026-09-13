"""别名服务：创建/删除/列表/域名/默认发件人，并维护取件地址绑定。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.orm import Session

from ..config import settings
from ..mailcom import (
    MailComAliasClient,
    MailComAliasExistsError,
    MailComAliasLimitError,
    MailComError,
    PickupResolver,
    SettingsAlias,
    split_alias_address,
)
from ..mailcom.resilience import WriteRateLimiter
from ..models import Account, Alias, PickupBinding
from ..schemas import AliasOut
from .session_manager import acquire_client, invalidate_settings_session

T = TypeVar("T")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class AliasService:
    def __init__(self, db: Session, resolver: PickupResolver, write_limiter: WriteRateLimiter) -> None:
        self.db = db
        self.resolver = resolver
        self.write_limiter = write_limiter

    def _to_out(self, alias: Alias) -> AliasOut:
        binding = alias.binding
        return AliasOut(
            id=alias.id,
            account_id=alias.account_id,
            account_email=alias.account.email if alias.account else "",
            address=alias.address,
            local_part=alias.local_part,
            domain=alias.domain,
            display_name=alias.display_name,
            is_default_sender=alias.is_default_sender,
            deletable=alias.deletable,
            state=alias.state,
            pickup_url=binding.pickup_url if binding else self.resolver.build(alias.account.account_key, alias.address),
            created_at=_iso(alias.created_at) or "",
            last_fetched_at=_iso(binding.last_fetched_at) if binding else None,
        )

    def list_by_account(self, account_id: int) -> list[AliasOut]:
        aliases = self.db.query(Alias).filter(Alias.account_id == account_id).order_by(Alias.id.asc()).all()
        return [self._to_out(alias) for alias in aliases]

    def find_alias(self, alias_id: int) -> Alias | None:
        return self.db.get(Alias, alias_id)

    async def _upstream_client(self, account: Account) -> MailComAliasClient:
        """优先复用已持久化的会话；没有会话时才登录，并写回。"""
        return await acquire_client(self.db, account)

    async def _with_client(
        self,
        account: Account,
        operation: Callable[[MailComAliasClient], Awaitable[T]],
    ) -> T:
        """执行一次 CATS 操作；若因令牌失效(401)失败，则重新登录后重试一次。

        对齐 SDK：正常情况直接使用缓存令牌，不做前置探活；
        只有真正被上游拒绝时才处理失效。
        """
        client = await self._upstream_client(account)
        try:
            return await operation(client)
        except MailComError as exc:
            if getattr(exc, "status", None) not in (401, 403):
                raise
        finally:
            await client.close()

        # 令牌被拒：清空会话后重新登录，再试一次
        invalidate_settings_session(self.db, account)
        client = await self._upstream_client(account)
        try:
            return await operation(client)
        finally:
            await client.close()

    async def domains(self, account_id: int) -> list[str]:
        account = self.db.get(Account, account_id)
        if account is None:
            raise MailComError(f"账号不存在：{account_id}")
        return await self._with_client(account, lambda client: client.available_domains())

    async def create(self, account_id: int, address: str) -> AliasOut:
        account = self.db.get(Account, account_id)
        if account is None:
            raise MailComError(f"账号不存在：{account_id}")

        local_part, domain, normalized = split_alias_address(address)

        async with self.write_limiter.lock(f"account:{account_id}"):
            await self.write_limiter.wait(f"account:{account_id}")

            existing = self.db.query(Alias).filter(Alias.account_id == account_id, Alias.address == normalized).first()
            if existing is not None:
                raise MailComAliasExistsError(f"别名已存在：{normalized}")

            count = self.db.query(Alias).filter(Alias.account_id == account_id).count()
            if count >= settings.max_aliases_per_account:
                raise MailComAliasLimitError("别名数量已达上限")

            try:
                created = await self._with_client(
                    account,
                    lambda client: client.create_alias(normalized, max_aliases=settings.max_aliases_per_account),
                )
            except MailComAliasExistsError:
                existing = (
                    self.db.query(Alias).filter(Alias.account_id == account_id, Alias.address == normalized).first()
                )
                if existing is not None:
                    return self._to_out(existing)
                raise

            alias = self._upsert_alias(account, created)
            pickup_url = self.resolver.build(account.account_key, alias.address)
            self.db.add(PickupBinding(alias_id=alias.id, pickup_url=pickup_url))
            self.db.commit()
            self.db.refresh(alias)
            return self._to_out(alias)

    def _upsert_alias(self, account: Account, settings_alias: SettingsAlias) -> Alias:
        local_part, domain, normalized = split_alias_address(settings_alias.address)
        alias = self.db.query(Alias).filter(Alias.account_id == account.id, Alias.address == normalized).first()
        if alias is None:
            alias = Alias(account_id=account.id, address=normalized, local_part=local_part, domain=domain)
            self.db.add(alias)
        alias.display_name = settings_alias.display_name
        alias.is_default_sender = settings_alias.default_sender_address
        alias.deletable = settings_alias.deletable
        alias.state = settings_alias.state
        self.db.flush()
        return alias

    async def sync_from_upstream(self, account_id: int) -> list[AliasOut]:
        """从 mail.com 拉取别名列表并同步到本地（创建时使用 create，列表刷新时使用）。"""
        account = self.db.get(Account, account_id)
        if account is None:
            raise MailComError(f"账号不存在：{account_id}")
        upstream = await self._with_client(account, lambda client: client.list_aliases())

        for settings_alias in upstream:
            alias = self._upsert_alias(account, settings_alias)
            if alias.binding is None:
                pickup_url = self.resolver.build(account.account_key, alias.address)
                self.db.add(PickupBinding(alias_id=alias.id, pickup_url=pickup_url))
        self.db.commit()
        return self.list_by_account(account_id)

    async def delete(self, alias_id: int) -> None:
        alias = self.db.get(Alias, alias_id)
        if alias is None:
            return
        account = alias.account

        async with self.write_limiter.lock(f"account:{account.id}"):
            await self.write_limiter.wait(f"account:{account.id}")
            await self._with_client(account, lambda client: client.delete_alias(alias.address))

            self.db.delete(alias)
            self.db.commit()

    async def set_default_sender(self, alias_id: int, sender: str) -> AliasOut:
        alias = self.db.get(Alias, alias_id)
        if alias is None:
            raise MailComError(f"别名不存在：{alias_id}")
        account = alias.account

        async with self.write_limiter.lock(f"account:{account.id}"):
            await self.write_limiter.wait(f"account:{account.id}")
            updated = await self._with_client(
                account,
                lambda client: client.set_default_sender(alias.address, sender),
            )
            alias.is_default_sender = updated.default_sender_address
            alias.display_name = updated.display_name
            self.db.commit()
            self.db.refresh(alias)
            return self._to_out(alias)

    async def set_display_name(self, alias_id: int, display_name: str) -> AliasOut:
        alias = self.db.get(Alias, alias_id)
        if alias is None:
            raise MailComError(f"别名不存在：{alias_id}")
        account = alias.account

        async with self.write_limiter.lock(f"account:{account.id}"):
            await self.write_limiter.wait(f"account:{account.id}")
            updated = await self._with_client(
                account,
                lambda client: client.set_display_name(alias.address, display_name),
            )
            alias.display_name = updated.display_name
            self.db.commit()
            self.db.refresh(alias)
            return self._to_out(alias)
