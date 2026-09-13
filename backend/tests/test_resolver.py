"""取件地址与别名地址的单元测试。"""

from __future__ import annotations

import pytest

from app.mailcom.aliases import split_alias_address
from app.mailcom.errors import MailComValidationError
from app.mailcom.resolver import PickupResolver


def test_build_and_parse_roundtrip() -> None:
    resolver = PickupResolver("http://localhost:8000")
    url = resolver.build("acc_ab12cd", "my-alias@mail.com")
    assert url == "http://localhost:8000/api/v1/pickup/acc_ab12cd/my-alias%40mail.com"
    assert resolver.parse(url) == ("acc_ab12cd", "my-alias@mail.com")


def test_parse_accepts_path_only() -> None:
    resolver = PickupResolver("http://host")
    assert resolver.parse("/api/v1/pickup/acc_x/a@mail.com") == ("acc_x", "a@mail.com")


def test_parse_rejects_invalid() -> None:
    resolver = PickupResolver("http://host")
    with pytest.raises(ValueError):
        resolver.parse("http://host/not-a-pickup-url")


def test_split_alias_address_normalizes() -> None:
    local, domain, address = split_alias_address("My-Alias@Mail.com")
    assert (local, domain, address) == ("my-alias", "mail.com", "my-alias@mail.com")


def test_split_alias_address_defaults_domain() -> None:
    assert split_alias_address("myalias")[2] == "myalias@mail.com"


def test_split_alias_address_rejects_short() -> None:
    with pytest.raises(MailComValidationError):
        split_alias_address("ab")


def test_split_alias_address_rejects_bad_chars() -> None:
    with pytest.raises(MailComValidationError):
        split_alias_address("bad alias@mail.com")
