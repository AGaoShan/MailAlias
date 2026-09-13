"""会话持久化与复用逻辑测试（不触达真实 mail.com）。"""

from __future__ import annotations

import asyncio

from app.services.session_manager import _session_for, load_cookies


def test_load_cookies_none() -> None:
    assert load_cookies(None) == {}


def test_load_cookies_valid_json() -> None:
    assert load_cookies('{"a": "1", "b": "2"}') == {"a": "1", "b": "2"}


def test_load_cookies_invalid_json() -> None:
    assert load_cookies("not-json") == {}


def test_load_cookies_non_dict() -> None:
    assert load_cookies('["a", "b"]') == {}


def test_load_cookies_coerces_types() -> None:
    assert load_cookies('{"n": 1}') == {"n": "1"}


def test_session_lock_is_stable_per_account() -> None:
    """同一账号必须始终拿到同一把锁（登录去重的前提）。"""
    first = _session_for(1)
    second = _session_for(1)
    assert first is second
    assert first.lock is second.lock


def test_session_lock_differs_across_accounts() -> None:
    assert _session_for(101) is not _session_for(102)


def test_session_lock_serializes_concurrent_logins() -> None:
    """并发调用时，锁应保证临界区串行执行。"""
    order: list[str] = []
    lock = _session_for(999).lock

    async def worker(tag: str) -> None:
        async with lock:
            order.append(f"enter-{tag}")
            await asyncio.sleep(0.01)
            order.append(f"exit-{tag}")

    async def main() -> None:
        await asyncio.gather(worker("a"), worker("b"))

    asyncio.run(main())
    # 串行执行：进入与退出严格配对，不会出现 a-enter, b-enter 交错
    assert order[0].startswith("enter-")
    assert order[1].startswith("exit-")
    assert order[2].startswith("enter-")
    assert order[3].startswith("exit-")


def test_generation_increments_per_login_state() -> None:
    """每个账号独立维护登录代次。"""
    first = _session_for(501)
    second = _session_for(502)
    first.generation += 1
    assert first.generation == 1
    assert second.generation == 0


def test_mobile_login_is_idempotent_without_password() -> None:
    """已持有效会话时，重复 login() 不应再次触发网络请求。"""
    from app.mailcom.mobile_api import MobileClient, MobileSession

    client = MobileClient("a@mail.com", None, session=MobileSession(access_token="t", refresh_token="r"))
    calls: list[str] = []

    async def fake_validate(token: str) -> bool:
        calls.append(token)
        return True

    client._validate_token = fake_validate  # type: ignore[method-assign]

    async def main() -> None:
        await client.login()
        await client.login()
        await client.close()

    asyncio.run(main())
    assert calls == ["t"], f"login() 应只校验一次，实际 {calls}"


def test_concurrent_logins_share_single_attempt() -> None:
    """并发请求只应触发一次登录（无论成功还是失败）。"""
    import logging

    from app.database import SessionLocal
    from app.mailcom import MailComAliasClient
    from app.models import Account, SessionToken
    from app.services import session_manager as sm

    logging.disable(logging.CRITICAL)
    calls: list[str] = []
    real_login = MailComAliasClient.login.__func__

    class _FakeClient:
        def __init__(self, token: str) -> None:
            self._token = token

        @property
        def access_token(self) -> str:
            return self._token

        @property
        def cookies(self) -> dict[str, str]:
            return {"c": "1"}

        async def close(self) -> None:
            return None

    async def fake_login(cls, email, password, timeout=30.0):  # noqa: ANN001, ANN202
        calls.append(email)
        await asyncio.sleep(0.2)
        return _FakeClient("TOKEN_1")

    MailComAliasClient.login = classmethod(fake_login)
    try:
        async def main() -> None:
            db = SessionLocal()
            account = db.query(Account).first()
            if account is None:
                db.close()
                return
            token_row = db.query(SessionToken).filter(SessionToken.account_id == account.id).first()
            if token_row is not None:
                token_row.settings_token = None
                token_row.settings_cookies = None
                db.commit()
            db.close()

            async def worker() -> None:
                session = SessionLocal()
                try:
                    acc = session.query(Account).first()
                    if acc is not None:
                        client = await sm.acquire_client(session, acc)
                        await client.close()
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    session.close()

            await asyncio.gather(*(worker() for _ in range(5)))

        asyncio.run(main())
    finally:
        MailComAliasClient.login = classmethod(real_login)
        logging.disable(logging.NOTSET)

    assert len(calls) <= 1, f"并发登录次数应 <= 1，实际 {len(calls)}"
