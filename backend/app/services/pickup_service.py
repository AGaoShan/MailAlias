"""取件服务：地址解析、调度取件、缓存、降级、逐地址批处理。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..mailcom import MailComError, Message, MobileClient, MobileSession, PickupResolver
from ..mailcom.errors import MailComAuthError, MailComNotFoundError
from ..mailcom.resilience import CircuitBreakerRegistry, CircuitOpenError
from ..mailcom.scheduler import PickupCache, PickupScheduler
from ..models import Account, Alias, FetchLog, PickupBinding, SessionToken
from ..schemas import MessageOut, PickupResult
from ..security.crypto import decrypt_secret
from .session_manager import (
    get_or_create_token_row,
    invalidate_mobile_session,
    load_mobile_session,
    store_mobile_session,
)


def _iso(value: datetime | None = None) -> str:
    value = value or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        **{"from": message.from_addr},
        to=message.to,
        subject=message.subject,
        date=message.date,
        preview=message.preview,
        read=message.read,
        has_attachments=message.has_attachments,
        folder=message.folder,
        code=message.code,
    )


def _message_dict(message: Message) -> dict:
    return {
        "id": message.id,
        "from": message.from_addr,
        "to": message.to,
        "subject": message.subject,
        "date": message.date,
        "preview": message.preview,
        "read": message.read,
        "has_attachments": message.has_attachments,
        "folder": message.folder,
        "code": message.code,
    }


class PickupService:
    def __init__(
        self,
        db: Session,
        resolver: PickupResolver,
        scheduler: PickupScheduler,
        cache: PickupCache,
        circuits: CircuitBreakerRegistry,
    ) -> None:
        self.db = db
        self.resolver = resolver
        self.scheduler = scheduler
        self.cache = cache
        self.circuits = circuits

    def resolve(self, pickup_url: str) -> tuple[Account, Alias]:
        account_key, alias_address = self.resolver.parse(pickup_url)
        account = self.db.query(Account).filter(Account.account_key == account_key).first()
        if account is None:
            raise MailComNotFoundError(f"账号标识不存在：{account_key}")
        alias = self.db.query(Alias).filter(Alias.account_id == account.id, Alias.address == alias_address).first()
        if alias is None:
            raise MailComNotFoundError(f"别名不存在：{alias_address}")
        return account, alias

    async def fetch(
        self,
        pickup_url: str,
        *,
        amount: int = 25,
        mark_read: bool = False,
        unread_only: bool = False,
        refresh: bool = False,
    ) -> tuple[list[Message], bool, str]:
        account, alias = self.resolve(pickup_url)
        cache_key = f"{account.id}:{pickup_url}:{amount}:{unread_only}"

        if not refresh:
            cached = self.cache.get_typed(cache_key, list)
            if cached is not None and len(cached) == 2:
                cached_messages, cached_at = cached
                if isinstance(cached_messages, list) and isinstance(cached_at, str):
                    return cached_messages, False, cached_at
        breaker = self.circuits.get(account.account_key)
        if not breaker.allow():
            stale = self._stale_result(pickup_url)
            if stale is not None:
                return stale[0], True, stale[1]
            raise CircuitOpenError("上游熔断中，请稍后重试", retry_after=breaker.retry_after())

        async def coro() -> list[Message]:
            client = await self._client_for(account)
            try:
                # 仅返回投递到该别名的邮件，避免泄露主邮箱全部邮件
                return await client.list_messages(amount, unread_only=unread_only, recipient=alias.address)
            finally:
                await client.close()

        try:
            messages = await self.scheduler.run(
                account.id, cache_key, coro, account_qps=settings.rate_limit_per_account_qps
            )
            breaker.on_success()
        except Exception as exc:  # noqa: BLE001
            breaker.on_failure()
            stale = self._stale_result(pickup_url)
            if stale is not None:
                return stale[0], True, stale[1]
            raise exc

        fetched_at = _iso()
        self.cache.set(cache_key, (messages, fetched_at))
        self._touch_binding(alias.id, fetched_at)
        self._log_fetch(pickup_url, alias.address, len(messages))

        if mark_read and messages:
            await self._mark_read(account, [message.id for message in messages])

        return messages, False, fetched_at

    async def get_body(self, pickup_url: str, message_id: str, fmt: str, mark_read: bool = False) -> str:
        account, _alias = self.resolve(pickup_url)
        client = await self._client_for(account)
        try:
            return await client.get_body(message_id, fmt=fmt, mark_read=mark_read)
        finally:
            await client.close()

    async def batch(self, pickup_urls: list[str], amount: int = 25) -> list[PickupResult]:
        results: list[PickupResult] = []
        cache_keys: dict[str, list[Message]] = {}
        for url in pickup_urls:
            alias_address: str | None = None
            try:
                account, alias = self.resolve(url)
                alias_address = alias.address
                messages, stale, _fetched_at = await self.fetch(url, amount=amount)
                cache_keys[url] = messages
                results.append(
                    PickupResult(
                        pickup_url=url,
                        alias=alias_address,
                        ok=not stale,
                        messages=[_message_out(message) for message in messages],
                    )
                )
            except MailComError as exc:
                results.append(
                    PickupResult(
                        pickup_url=url,
                        alias=alias_address,
                        ok=False,
                        error={"code": exc.code, "message": exc.message},
                    )
                )
        return results

    async def _client_for(self, account: Account) -> MobileClient:
        token = self.db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
        mobile_token, refresh_token = load_mobile_session(token)

        session = None
        if mobile_token:
            session = MobileSession(access_token=mobile_token, refresh_token=refresh_token or "")

        client = MobileClient(
            account.email, decrypt_secret(account.password_enc), timeout=settings.mailcom_timeout, session=session
        )
        try:
            await client.login()
        except MailComAuthError:
            invalidate_mobile_session(self.db, account)
            account.session_state = "expired"
            self.db.commit()
            raise

        if client.session is not None:
            row = token if token is not None else get_or_create_token_row(self.db, account)
            store_mobile_session(
                row,
                client.session.access_token,
                client.session.refresh_token,
                self.db,
            )
            if account.session_state != "active":
                account.session_state = "active"
                self.db.commit()
        return client

    async def _mark_read(self, account: Account, message_ids: list[str]) -> None:
        client = await self._client_for(account)
        try:
            await client.mark_read(message_ids)
        finally:
            await client.close()

    def _touch_binding(self, alias_id: int, fetched_at: str) -> None:
        binding = self.db.query(PickupBinding).filter(PickupBinding.alias_id == alias_id).first()
        if binding is not None:
            binding.last_fetched_at = datetime.now(UTC)
            self.db.commit()

    def _log_fetch(self, pickup_url: str, alias_address: str, count: int) -> None:
        self.db.add(
            FetchLog(
                pickup_url=pickup_url,
                alias_address=alias_address,
                message_count=count,
                fetched_at=datetime.now(UTC),
            )
        )
        self.db.commit()

    def _stale_result(self, pickup_url: str) -> tuple[list[Message], str] | None:
        log = (
            self.db.query(FetchLog)
            .filter(FetchLog.pickup_url == pickup_url)
            .order_by(FetchLog.fetched_at.desc())
            .first()
        )
        if log is None:
            return None
        return [], _iso(log.fetched_at)
