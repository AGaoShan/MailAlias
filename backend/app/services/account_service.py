"""账号服务：增删查、登录校验、会话维护。"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..mailcom import MailComAliasClient, MailComError
from ..models import Account
from ..schemas import AccountOut
from ..security.crypto import encrypt_secret
from .session_manager import acquire_client, store_settings_session


def _account_key(email: str) -> str:
    return f"acc_{secrets.token_hex(3)}"


def _iso(value: datetime | None) -> str:
    if value is None:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class AccountService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _to_out(self, account: Account) -> AccountOut:
        return AccountOut(
            id=account.id,
            account_key=account.account_key,
            email=account.email,
            enabled=account.enabled,
            alias_count=len(account.aliases),
            alias_limit=settings.max_aliases_per_account,
            session_state=account.session_state,
            created_at=_iso(account.created_at),
            updated_at=_iso(account.updated_at),
        )

    def list(self) -> list[AccountOut]:
        accounts = self.db.query(Account).order_by(Account.id.asc()).all()
        return [self._to_out(account) for account in accounts]

    def get(self, account_id: int) -> Account | None:
        return self.db.get(Account, account_id)

    def get_by_key(self, account_key: str) -> Account | None:
        return self.db.query(Account).filter(Account.account_key == account_key).first()

    async def add(self, email: str, password: str) -> AccountOut:
        normalized = email.strip().lower()
        existing = self.db.query(Account).filter(Account.email == normalized).first()
        if existing is not None:
            raise MailComError(f"账号已存在：{normalized}")

        client: MailComAliasClient | None = None
        try:
            client = await MailComAliasClient.login(normalized, password, timeout=settings.mailcom_timeout)
        finally:
            if client is not None:
                await client.close()

        account = Account(
            account_key=_account_key(normalized),
            email=normalized,
            password_enc=encrypt_secret(password),
            enabled=True,
            session_state="active",
        )
        self.db.add(account)
        self.db.flush()
        if client is not None:
            store_settings_session(None, account, client, self.db)
        self.db.commit()
        self.db.refresh(account)
        return self._to_out(account)

    def delete(self, account_id: int) -> None:
        account = self.db.get(Account, account_id)
        if account is None:
            return
        self.db.delete(account)
        self.db.commit()

    async def verify(self, account_id: int) -> AccountOut:
        account = self.db.get(Account, account_id)
        if account is None:
            raise MailComError(f"账号不存在：{account_id}")

        client: MailComAliasClient | None = None
        try:
            # 复用持久化会话；失效时才回退全量登录（acquire_client 内部已写回会话）
            client = await acquire_client(self.db, account)
            account.session_state = "active"
            account.updated_at = datetime.now(UTC)
        except MailComError:
            account.session_state = "error"
            account.updated_at = datetime.now(UTC)
            self.db.commit()
            raise
        finally:
            if client is not None:
                await client.close()
        self.db.commit()
        self.db.refresh(account)
        return self._to_out(account)
