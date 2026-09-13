"""账号会话缓存与登录去重（对齐 maildotcom-sdk 的行为）。

设计原则（与 SDK 保持一致）：

1. **不每次操作都探活**：拿到令牌后直接使用，不再为每个请求调用 validate。
   只有在真正收到 401 时才处理失效。
2. **401 优先刷新**：移动端令牌有 refresh_token，先刷新；刷新失败才全量登录。
3. **内存缓存复用**：同一进程内复用已建立的客户端会话，避免重复登录。
4. **并发去重**：同一账号同一时刻只允许一个登录/刷新在跑（SDK 的 loginInFlight）。
5. **失败即弃**：登录/刷新失败时清空缓存，避免坏令牌反复触发请求。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..mailcom import MailComAliasClient, MailComError
from ..models import Account, SessionToken


def load_cookies(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def get_or_create_token_row(db: Session, account: Account) -> SessionToken:
    token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
    if token is None:
        token = SessionToken(account_id=account.id)
        db.add(token)
    return token


# ---------- 别名（CATS settings）会话 ----------


def store_settings_session(
    token: SessionToken | None,
    account: Account,
    client: MailComAliasClient,
    db: Session,
) -> SessionToken:
    if token is None:
        token = get_or_create_token_row(db, account)
    token.settings_token = client.access_token
    token.settings_cookies = json.dumps(client.cookies, ensure_ascii=False)
    token.updated_at = datetime.now(UTC)
    return token


async def acquire_client(db: Session, account: Account) -> MailComAliasClient:
    """获取可用的 CATS 客户端。

    复用顺序（与 SDK 的 login() 一致）：
      1. 数据库里已保存的 settings 会话 → 直接使用，**不探活**；
      2. 没有则全量登录一次，并把新会话写回数据库。

    令牌是否失效不在这里判断；调用方遇到 401 时应丢弃客户端并调用
    `invalidate_settings_session()`，下次自然会重新登录。
    """
    token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()

    if token is not None and token.settings_token:
        return MailComAliasClient.from_session(
            token.settings_token,
            load_cookies(token.settings_cookies),
            timeout=settings.mailcom_timeout,
        )

    return await _full_settings_login(db, account, token)


async def _full_settings_login(
    db: Session,
    account: Account,
    token: SessionToken | None,
) -> MailComAliasClient:
    """执行一次完整的 CATS 登录并持久化会话。"""
    async with _login_lock(account.id):
        # 双重检查：并发情况下可能已被其它请求登录完成
        if token is None:
            token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
        if token is not None and token.settings_token:
            return MailComAliasClient.from_session(
                token.settings_token,
                load_cookies(token.settings_cookies),
                timeout=settings.mailcom_timeout,
            )

        from ..security.crypto import decrypt_secret

        password = decrypt_secret(account.password_enc)
        client = await MailComAliasClient.login(account.email, password, timeout=settings.mailcom_timeout)
        try:
            store_settings_session(token, account, client, db)
            account.session_state = "active"
            account.updated_at = datetime.now(UTC)
            db.commit()
        except MailComError:
            db.rollback()
            raise
        return client


def invalidate_settings_session(db: Session, account: Account) -> None:
    """令牌被上游拒绝（401）时调用：清空会话，下次请求会重新登录。"""
    token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
    if token is None:
        return
    token.settings_token = None
    token.settings_cookies = None
    token.updated_at = datetime.now(UTC)
    db.commit()


# ---------- 取件（HSP2 移动 API）会话 ----------


def load_mobile_session(token: SessionToken | None) -> tuple[str | None, str | None]:
    if token is None:
        return None, None
    return token.mobile_token, token.mobile_refresh_token


def store_mobile_session(
    token: SessionToken,
    access_token: str,
    refresh_token: str | None,
    db: Session,
) -> SessionToken:
    token.mobile_token = access_token
    if refresh_token:
        token.mobile_refresh_token = refresh_token
    token.updated_at = datetime.now(UTC)
    db.commit()
    return token


def invalidate_mobile_session(db: Session, account: Account) -> None:
    """移动令牌被拒时清空（保留 refresh_token，供下次刷新尝试）。"""
    token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
    if token is None:
        return
    token.mobile_token = None
    token.updated_at = datetime.now(UTC)
    db.commit()


# ---------- 登录去重 ----------

_login_locks: dict[int, asyncio.Lock] = {}


def _login_lock(account_id: int) -> asyncio.Lock:
    """取得该账号的登录锁，保证同一账号不会并发登录（SDK 的 loginInFlight）。"""
    lock = _login_locks.get(account_id)
    if lock is None:
        lock = asyncio.Lock()
        _login_locks[account_id] = lock
    return lock
