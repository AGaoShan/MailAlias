"""账号会话缓存与登录去重（对齐 maildotcom-sdk 的行为）。

设计原则（与 SDK 保持一致）：

1. **不每次操作都探活**：拿到令牌后直接使用，不再为每个请求调用 validate。
   只有在真正收到 401 时才处理失效。
2. **401 优先刷新**：移动端令牌有 refresh_token，先刷新；刷新失败才全量登录。
3. **内存缓存复用**：同一进程内复用已建立的客户端会话，避免重复登录。
4. **并发去重**：同一账号同一时刻只允许一个登录/刷新在跑（SDK 的 loginInFlight）。
5. **失败即弃**：登录/刷新失败时清空缓存，避免坏令牌反复触发请求。

并发安全要点（避免多个 401 同时触发并发登录）：

- 每个账号一把 `asyncio.Lock`，覆盖「判断是否需要登录 + 登录 + 写回」的完整区间。
- 使用**登录代次(_generation)**：某个请求携带的过期令牌只会使其自身那次代次失效，
  不会清掉其它请求刚登录得到的新令牌。只有「当前代次」的令牌被判定失效时才作废。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..mailcom import MailComAliasClient, MailComError
from ..models import Account, SessionToken
from . import session_state


@dataclass
class _AccountSession:
    """单个账号的内存会话状态。"""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # 当前令牌所属的登录代次；每次成功登录自增
    generation: int = 0
    # 正在进行的登录 future：并发等待者共享同一次登录结果（成功或失败）
    login_future: asyncio.Future | None = None
    # 最近一次登录失败：错误 + 失败时刻，用于短时间内合并后续请求，避免风暴
    last_error: MailComError | None = None
    last_error_at: float = 0.0


_sessions: dict[int, _AccountSession] = {}

# 登录失败后的冷却窗口（秒）：窗口内的并发/后续请求直接复用失败结论，
# 不再重复冲击上游，避免账号被 mail.com 风控。
_FAILURE_COOLDOWN = 15.0


def _session_for(account_id: int) -> _AccountSession:
    state = _sessions.get(account_id)
    if state is None:
        state = _AccountSession()
        _sessions[account_id] = state
    return state


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

    并发语义（关键）：

    - 同一账号所有请求共用一把锁；
    - 若已有登录正在进行，等待者**共享同一次登录结果**；
    - 登录失败后短时间内，后续请求会**直接复用该失败结论**，
      不会再次冲击上游，避免并发失败把账号打成风控。
    """
    state = _session_for(account.id)

    # 1) 已有登录在进行 → 等它，而不是排队后再登录一次
    pending = state.login_future
    if pending is not None and not pending.done():
        try:
            await asyncio.shield(pending)
        except MailComError as exc:
            raise exc from None
        except Exception:  # noqa: BLE001
            pass
        return await _reuse_or_login(db, account, state)

    # 2) 最近刚失败过 → 直接复用失败结论（冷却窗口内不重复登录）
    if _recent_failure(state):
        _raise_last_error(state)

    async with state.lock:
        db.expire_all()
        token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
        if token is not None and token.settings_token:
            _mark_state(db, account, session_state.ACTIVE)
            return MailComAliasClient.from_session(
                token.settings_token,
                load_cookies(token.settings_cookies),
                timeout=settings.mailcom_timeout,
            )
        # 双重检查：可能在等锁期间别人已经登录成功
        if _recent_failure(state):
            _raise_last_error(state)
        return await _login_with_shared_future(db, account, token, state)


def _recent_failure(state: _AccountSession) -> bool:
    """判断是否处于「刚失败不久」的冷却窗口内。"""
    if state.last_error is None:
        return False
    return (time.monotonic() - state.last_error_at) < _FAILURE_COOLDOWN


def _raise_last_error(state: _AccountSession) -> None:
    """抛出上次登录失败的错误（调用前需确保存在）。"""
    if state.last_error is not None:
        raise state.last_error
    raise MailComError("登录失败")


async def _reuse_or_login(
    db: Session,
    account: Account,
    state: _AccountSession,
) -> MailComAliasClient:
    """共享登录结束后：成功则复用令牌，失败则按冷却策略处理。"""
    if _recent_failure(state):
        _raise_last_error(state)
    async with state.lock:
        db.expire_all()
        token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
        if token is not None and token.settings_token:
            _mark_state(db, account, session_state.ACTIVE)
            return MailComAliasClient.from_session(
                token.settings_token,
                load_cookies(token.settings_cookies),
                timeout=settings.mailcom_timeout,
            )
        if _recent_failure(state):
            _raise_last_error(state)
        return await _login_with_shared_future(db, account, token, state)


async def _login_with_shared_future(
    db: Session,
    account: Account,
    token: SessionToken | None,
    state: _AccountSession,
) -> MailComAliasClient:
    """在锁内执行登录，并让并发等待者共享该次结果。"""
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    state.login_future = future
    state.last_error = None
    try:
        client = await _login_locked(db, account, token, state)
        if not future.done():
            future.set_result(True)
        state.last_error = None
        state.last_error_at = 0.0
        return client
    except MailComError as exc:
        state.last_error = exc
        state.last_error_at = time.monotonic()
        if not future.done():
            future.set_exception(exc)
        raise
    finally:
        state.login_future = None


def _mark_state(db: Session, account: Account, value: str) -> None:
    """更新账号登录状态并落库（状态未变化时不写库）。"""
    if account.session_state != value:
        account.session_state = value
        account.updated_at = datetime.now(UTC)
        db.commit()


async def _login_locked(
    db: Session,
    account: Account,
    token: SessionToken | None,
    state: _AccountSession,
) -> MailComAliasClient:
    """在已持有账号锁的前提下执行完整登录并持久化。

    进入时状态置为 `logging_in`，成功后置 `active`，失败置 `error`。
    """
    from ..security.crypto import decrypt_secret

    _mark_state(db, account, session_state.LOGGING_IN)
    try:
        password = decrypt_secret(account.password_enc)
        client = await MailComAliasClient.login(account.email, password, timeout=settings.mailcom_timeout)
    except MailComError:
        _mark_state(db, account, session_state.ERROR)
        raise

    try:
        store_settings_session(token, account, client, db)
        account.session_state = session_state.ACTIVE
        account.updated_at = datetime.now(UTC)
        db.commit()
        state.generation += 1
    except MailComError:
        db.rollback()
        _mark_state(db, account, session_state.ERROR)
        raise
    return client


async def reauthenticate(
    db: Session,
    account: Account,
    stale_token: str | None,
) -> MailComAliasClient:
    """令牌被拒后的恢复：作废旧会话并重新登录。

    只作废「仍在使用 stale_token」的会话：如果并发中的其它请求已经完成了一次
    新登录（令牌已变化），则直接复用新令牌，**不会重复登录**。
    若已有登录在跑，则共享其结果。
    """
    state = _session_for(account.id)

    existing = state.login_future
    if existing is not None and not existing.done():
        try:
            await asyncio.shield(existing)
        except Exception:  # noqa: BLE001
            pass
        return await _reuse_or_login(db, account, state)

    if _recent_failure(state):
        _raise_last_error(state)

    async with state.lock:
        db.expire_all()
        token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()

        # 令牌已被其它请求更新过（不同于我们失败时用的那个）→ 直接复用
        if token is not None and token.settings_token and token.settings_token != stale_token:
            _mark_state(db, account, session_state.ACTIVE)
            return MailComAliasClient.from_session(
                token.settings_token,
                load_cookies(token.settings_cookies),
                timeout=settings.mailcom_timeout,
            )

        if _recent_failure(state):
            _raise_last_error(state)

        # 确实还是失效的旧令牌：标记过期，清空后重新登录
        _mark_state(db, account, session_state.EXPIRED)
        if token is not None:
            token.settings_token = None
            token.settings_cookies = None
            token.updated_at = datetime.now(UTC)
            db.commit()

        return await _login_with_shared_future(db, account, token, state)


def mark_expired(db: Session, account: Account) -> None:
    """上游返回 401/403 时调用：把账号标记为「登录过期」。"""
    _mark_state(db, account, session_state.EXPIRED)


def invalidate_settings_session(db: Session, account: Account) -> None:
    """强制失效会话（用户主动退出或确认令牌不可用）。

    注意：收到 401 时应优先调用 `reauthenticate()`，它能在并发场景下避免重复登录。
    """
    token = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
    if token is None:
        return
    token.settings_token = None
    token.settings_cookies = None
    token.updated_at = datetime.now(UTC)
    db.commit()
    _mark_state(db, account, session_state.EXPIRED)


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
