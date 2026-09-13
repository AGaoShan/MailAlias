"""随机别名前缀生成测试。"""

from __future__ import annotations

import re

import pytest

from app.mailcom.generator import random_local_part

VALID = re.compile(r"^[a-z0-9._-]{3,62}$")


@pytest.mark.parametrize("length", [6, 10, 20, 40])
def test_length_is_respected(length: int) -> None:
    assert len(random_local_part(length)) == length


@pytest.mark.parametrize("length", [1, 3, 62, 100])
def test_length_within_bounds(length: int) -> None:
    value = random_local_part(length)
    assert 3 <= len(value) <= 62


def test_only_allowed_characters() -> None:
    for _ in range(50):
        assert VALID.match(random_local_part(12)), "包含 mail.com 不允许的字符"


def test_prefix_is_kept() -> None:
    for _ in range(20):
        value = random_local_part(12, prefix="tmp")
        assert value.startswith("tmp")


def test_prefix_invalid_chars_stripped() -> None:
    value = random_local_part(12, prefix="TM P@#$")
    assert value.startswith("tmp")


def test_no_leading_or_trailing_separator() -> None:
    for _ in range(100):
        value = random_local_part(12)
        assert value[0] not in ".-_", f"首字符是分隔符：{value}"
        assert value[-1] not in ".-_", f"尾字符是分隔符：{value}"


def test_values_are_random() -> None:
    values = {random_local_part(16) for _ in range(50)}
    assert len(values) > 40, "随机性不足，生成结果大量重复"


def test_prefix_longer_than_length_still_valid() -> None:
    # 前缀很长时，最终结果仍须符合 3-62 位约束
    value = random_local_part(8, prefix="a" * 30)
    assert 3 <= len(value) <= 62
    assert VALID.match(value)
