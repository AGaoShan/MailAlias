"""取件按收件人过滤的测试（确保别名只能看到自己的邮件）。"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from app.mailcom.mobile_api import MobileClient, MobileSession


class _FakeResponse:
    def __init__(self, payload: str, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.text = payload

    def json(self) -> object:
        import json

        return json.loads(self._payload)


def _build_client(recorded: list[str]) -> MobileClient:
    client = MobileClient("owner@mail.com", "pw", session=MobileSession(access_token="tok", refresh_token="ref"))

    async def fake_login() -> MobileSession:
        client._logged_in = True
        assert client.session is not None
        return client.session

    async def fake_folder_ids() -> list[str]:
        return ["INBOX"]

    async def fake_request(method: str, url: str, **kwargs) -> _FakeResponse:  # noqa: ANN003
        recorded.append(str(url))
        return _FakeResponse('{"mail": []}')

    client.login = fake_login  # type: ignore[method-assign]
    client._incoming_folder_ids = fake_folder_ids  # type: ignore[method-assign]
    client._request = fake_request  # type: ignore[method-assign]
    return client


def _condition_of(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return (query.get("condition") or [""])[0]


def test_list_messages_filters_by_recipient() -> None:
    recorded: list[str] = []
    client = _build_client(recorded)

    async def main() -> None:
        await client.list_messages(25, recipient="alias@mail.com")
        await client.close()

    asyncio.run(main())
    assert recorded, "应发出至少一次请求"
    assert _condition_of(recorded[0]) == "mail.header:to:alias@mail.com"


def test_list_messages_without_recipient_has_no_to_filter() -> None:
    recorded: list[str] = []
    client = _build_client(recorded)

    async def main() -> None:
        await client.list_messages(25)
        await client.close()

    asyncio.run(main())
    assert "mail.header:to" not in _condition_of(recorded[0])


def test_unread_and_recipient_conditions_combine() -> None:
    recorded: list[str] = []
    client = _build_client(recorded)

    async def main() -> None:
        await client.list_messages(25, unread_only=True, recipient="a@mail.com")
        await client.close()

    asyncio.run(main())
    condition = _condition_of(recorded[0])
    assert "mail.flag.unseen:true" in condition
    assert "mail.header:to:a@mail.com" in condition


def test_recipient_is_escaped() -> None:
    recorded: list[str] = []
    client = _build_client(recorded)

    async def main() -> None:
        await client.list_messages(25, recipient="weird:name@mail.com")
        await client.close()

    asyncio.run(main())
    # 冒号需转义，避免破坏条件语法
    assert _condition_of(recorded[0]) == "mail.header:to:weird\\:name@mail.com"


def test_parse_sse_json_extracts_preview() -> None:
    from app.mailcom.mobile_api import _parse_sse_json

    sse = (
        "id: 1\r\nevent: success\r\n"
        'data: {"mailIdentifier":"123","preview":"code 065474"}\r\n\r\n'
        ": noop (finally)\r\n\r\n"
    )
    payloads = _parse_sse_json(sse)
    assert payloads == [{"mailIdentifier": "123", "preview": "code 065474"}]


def test_parse_sse_json_ignores_non_json_and_empty() -> None:
    from app.mailcom.mobile_api import _parse_sse_json

    sse = "event: ping\ndata: not-json\n\n: comment only\n\n"
    assert _parse_sse_json(sse) == []


def test_parse_sse_json_handles_array_payload() -> None:
    from app.mailcom.mobile_api import _parse_sse_json

    sse = 'data: [{"mailIdentifier":"a"},{"mailIdentifier":"b"}]\n\n'
    assert _parse_sse_json(sse) == [{"mailIdentifier": "a"}, {"mailIdentifier": "b"}]
