"""别名服务：创建/删除/列表/域名/默认发件人，并维护取件地址绑定。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..mailcom import (
    MAILCOM_ALIAS_DOMAIN_SET,
    MailComAliasClient,
    MailComAliasExistsError,
    MailComAliasLimitError,
    MailComDomainUnavailableError,
    MailComError,
    PickupResolver,
    SettingsAlias,
    split_alias_address,
)
from ..mailcom.generator import random_local_part
from ..mailcom.resilience import WriteRateLimiter
from ..models import Account, Alias, DomainCache, PickupBinding
from ..schemas import AliasOut
from .session_manager import acquire_client, invalidate_settings_session

T = TypeVar("T")


@dataclass
class _BatchAccountState:
    """批量创建期间，单个账号复用的客户端与用量计数。"""

    account: Account
    used: int = 0
    client: MailComAliasClient | None = None


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

    async def domains(self, account_id: int, *, refresh: bool = False) -> list[str]:
        """获取账号可用域名。

        默认读本地缓存（避免每次都访问 mail.com）；refresh=True 时强制重新拉取。
        缓存不存在或已过期时自动回源。
        """
        account = self.db.get(Account, account_id)
        if account is None:
            raise MailComError(f"账号不存在：{account_id}")

        cache = self.db.query(DomainCache).filter(DomainCache.account_id == account_id).first()
        if not refresh and cache is not None and self._cache_fresh(cache):
            return self._decode_domains(cache.domains)

        fetched = await self._with_client(account, lambda client: client.available_domains())
        if fetched:
            self._save_domain_cache(account_id, cache, fetched)
            return fetched
        # 上游没返回时，退回旧缓存（若有）
        if cache is not None:
            return self._decode_domains(cache.domains)
        return []

    def _cache_fresh(self, cache: DomainCache) -> bool:
        fetched_at = cache.fetched_at
        if fetched_at is None:
            return False
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - fetched_at).total_seconds()
        return age < settings.domain_cache_ttl

    @staticmethod
    def _decode_domains(raw: str) -> list[str]:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return []
        if not isinstance(data, list):
            return []
        return [str(item) for item in data]

    def _save_domain_cache(self, account_id: int, cache: DomainCache | None, domains: list[str]) -> None:
        if cache is None:
            cache = DomainCache(account_id=account_id)
            self.db.add(cache)
        cache.domains = json.dumps(domains, ensure_ascii=False)
        cache.fetched_at = datetime.now(UTC)
        self.db.commit()

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

    async def create_auto(self, address: str, account_id: int | None = None) -> AliasOut:
        """自动选号创建：只需别名地址，自动挑选仍有别名额度的可用账号。

        - 指定 account_id 时只在该账号创建；
        - 否则按「剩余额度多 → 已有别名少 → id 小」的优先级选择账号；
        - 若别名已存在于某个账号，直接返回该别名（幂等）。
        """
        _local_part, _domain, normalized = split_alias_address(address)

        existing = self.db.query(Alias).filter(Alias.address == normalized).first()
        if existing is not None:
            return self._to_out(existing)

        account = self._select_account_for_alias(account_id)
        return await self.create(account.id, normalized)

    async def batch_generate(
        self,
        count: int,
        *,
        domain: str = "mail.com",
        account_id: int | None = None,
        prefix: str = "",
        length: int = 10,
    ) -> list[tuple[str, AliasOut | None, MailComError | None]]:
        """随机生成并批量创建别名。

        - 能建多少建多少：额度用尽后剩余的记为失败（附带原因），不中断
        - 返回 [(地址, 结果, 错误), ...]，顺序与请求一致
        """
        if domain not in MAILCOM_ALIAS_DOMAIN_SET:
            raise MailComDomainUnavailableError(f"不支持该别名域名：{domain}")

        # 先生成全部地址（本地去重）
        addresses: list[str] = []
        seen: set[str] = set()
        while len(addresses) < count:
            local_part = random_local_part(length, prefix=prefix)
            if local_part in seen:
                continue
            seen.add(local_part)
            addresses.append(f"{local_part}@{domain}")

        # 按账号聚合：同一账号复用客户端与用量计数，避免重复拉取列表/域名。
        state: dict[int, _BatchAccountState] = {}
        account_locks: dict[int, asyncio.Lock] = {}

        async def worker(address: str) -> tuple[str, AliasOut | None, MailComError | None]:
            try:
                account = self._pick_account_cached(account_id, state)
                lock = account_locks.setdefault(account.id, asyncio.Lock())
                # 同一账号内串行（避免并发写入触发风控），不同账号可并行
                async with lock:
                    alias = await self._create_on_account(account, address, state)
                return (address, alias, None)
            except MailComError as exc:
                return (address, None, exc)

        try:
            results = list(await asyncio.gather(*(worker(address) for address in addresses)))
        finally:
            for entry in state.values():
                if entry.client is not None:
                    await entry.client.close()

        return results

    def _pick_account_cached(
        self,
        account_id: int | None,
        state: dict[int, _BatchAccountState],
    ) -> Account:
        """选择账号，并复用其已建立的客户端与用量计数。"""
        if account_id is not None:
            account = self.db.get(Account, account_id)
            if account is None:
                raise MailComError(f"账号不存在：{account_id}")
            if not account.enabled:
                raise MailComError(f"账号已停用：{account.email}")
            entry = state.setdefault(account.id, _BatchAccountState(account=account))
            if entry.used >= settings.max_aliases_per_account:
                raise MailComAliasLimitError(f"账号 {account.email} 别名数量已达上限")
            return account

        accounts = self.db.query(Account).filter(Account.enabled.is_(True)).order_by(Account.id.asc()).all()
        if not accounts:
            raise MailComError("没有可用的账号，请先添加 mail.com 账号")

        db_counts: dict[int, int] = {
            int(account_id_value): int(total)
            for account_id_value, total in self.db.query(Alias.account_id, func.count(Alias.id))
            .group_by(Alias.account_id)
            .all()
        }
        for account in accounts:
            entry = state.setdefault(
                account.id,
                _BatchAccountState(account=account, used=db_counts.get(account.id, 0)),
            )
            entry.used = max(entry.used, db_counts.get(account.id, 0))

        candidates = [a for a in accounts if state[a.id].used < settings.max_aliases_per_account]
        if not candidates:
            raise MailComAliasLimitError("所有账号的别名数量都已达上限")

        candidates.sort(key=lambda account: (state[account.id].used, account.id))
        return candidates[0]

    async def _create_on_account(
        self,
        account: Account,
        address: str,
        state: dict[int, _BatchAccountState],
    ) -> AliasOut:
        """在指定账号上创建别名，复用客户端并滑动用量计数。"""
        entry = state[account.id]

        async with self.write_limiter.lock(f"account:{account.id}"):
            if entry.client is None:
                entry.client = await self._upstream_client(account)

            if entry.used >= settings.max_aliases_per_account:
                raise MailComAliasLimitError(f"账号 {account.email} 别名数量已达上限")

            await self.write_limiter.wait(f"account:{account.id}")
            # 注意：不使用本地计数跳过校验。mail.com 的别名可能由用户在网页端
            # 手动创建，本地计数并不可靠；必须让上游按真实数量校验，否则会撞 409。
            created = await entry.client.create_alias(
                address,
                max_aliases=settings.max_aliases_per_account,
            )

        alias = self._upsert_alias(account, created)
        pickup_url = self.resolver.build(account.account_key, alias.address)
        self.db.add(PickupBinding(alias_id=alias.id, pickup_url=pickup_url))
        self.db.commit()
        self.db.refresh(alias)
        entry.used += 1
        return self._to_out(alias)

    def _select_account_for_alias(self, account_id: int | None) -> Account:
        """选择用于创建别名的账号。"""
        if account_id is not None:
            account = self.db.get(Account, account_id)
            if account is None:
                raise MailComError(f"账号不存在：{account_id}")
            if not account.enabled:
                raise MailComError(f"账号已停用：{account.email}")
            used = self.db.query(Alias).filter(Alias.account_id == account.id).count()
            if used >= settings.max_aliases_per_account:
                raise MailComAliasLimitError(f"账号 {account.email} 别名数量已达上限")
            return account

        accounts = self.db.query(Account).filter(Account.enabled.is_(True)).order_by(Account.id.asc()).all()
        if not accounts:
            raise MailComError("没有可用的账号，请先添加 mail.com 账号")

        counts: dict[int, int] = {
            int(account_id_value): int(total)
            for account_id_value, total in self.db.query(Alias.account_id, func.count(Alias.id))
            .group_by(Alias.account_id)
            .all()
        }
        candidates = [account for account in accounts if counts.get(account.id, 0) < settings.max_aliases_per_account]
        if not candidates:
            raise MailComAliasLimitError("所有账号的别名数量都已达上限")

        # 剩余额度最多优先；相同则已有别名最少、账号 id 最小
        candidates.sort(
            key=lambda account: (
                -(settings.max_aliases_per_account - counts.get(account.id, 0)),
                counts.get(account.id, 0),
                account.id,
            )
        )
        return candidates[0]

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
