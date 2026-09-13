"""会话持久化与复用逻辑测试（不触达真实 mail.com）。"""

from __future__ import annotations

import asyncio

from app.services.session_manager import _login_lock, load_cookies


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


def test_login_lock_is_stable_per_account() -> None:
    """同一账号必须始终拿到同一把锁（登录去重的前提）。"""
    first = _login_lock(1)
    second = _login_lock(1)
    assert first is second


def test_login_lock_differs_across_accounts() -> None:
    assert _login_lock(101) is not _login_lock(102)


def test_login_lock_serializes_concurrent_logins() -> None:
    """并发调用时，锁应保证临界区串行执行。"""
    order: list[str] = []

    async def worker(tag: str) -> None:
        async with _login_lock(999):
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
