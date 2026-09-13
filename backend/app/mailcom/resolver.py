"""取件地址生成与反解。"""

from __future__ import annotations

from urllib.parse import quote, unquote, urlparse

PICKUP_PATH = "/api/v1/pickup"


class PickupResolver:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def build(self, account_key: str, alias_address: str) -> str:
        return f"{self.base}{PICKUP_PATH}/{quote(account_key, safe='')}/{quote(alias_address, safe='')}"

    def parse(self, pickup_url: str) -> tuple[str, str]:
        """从取件地址解析 (account_key, alias_address)。accepted 形式：完整 URL 或 /api/v1/pickup/... 路径。"""
        path = urlparse(pickup_url).path if "://" in pickup_url else pickup_url
        segments = [segment for segment in path.split("/") if segment]
        try:
            index = segments.index("pickup")
        except ValueError as exc:
            raise ValueError(f"Not a pickup url: {pickup_url}") from exc
        remaining = segments[index + 1 :]
        if len(remaining) != 2:
            raise ValueError(f"Invalid pickup url: {pickup_url}")
        return unquote(remaining[0]), unquote(remaining[1])
