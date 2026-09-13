"""验证码提取测试。"""

from __future__ import annotations

import pytest

from app.mailcom.verification_code import extract_verification_code


@pytest.mark.parametrize(
    ("subject", "preview", "expected"),
    [
        ("", "Nhập mã xác minh tạm thời này để tiếp tục: 065474 Vui lòng", "065474"),
        ("Your verification code is 123456", "", "123456"),
        ("验证码：9876，请勿泄露", "", "9876"),
        ("你的驗證碼是 4321", "", "4321"),
        ("Your code: 065-474", "", "065474"),
        ("Code 12 34 56", "", "123456"),
        ("Your OTP is 4321", "", "4321"),
        ("PIN: 5566", "", "5566"),
        ("登录密码 8699", "", "8699"),
    ],
)
def test_extracts_code(subject: str, preview: str, expected: str) -> None:
    assert extract_verification_code(subject, preview) == expected


@pytest.mark.parametrize(
    ("subject", "preview"),
    [
        ("", "Order 1234567890 shipped on 2026-09-13 at 10:30"),
        ("Meeting on 2026-09-13", ""),
        ("Your order #123456789012", ""),
        ("", ""),
        ("Welcome to our service", "Thanks for signing up"),
    ],
)
def test_ignores_noise(subject: str, preview: str) -> None:
    assert extract_verification_code(subject, preview) is None


def test_prefers_labeled_code_over_other_numbers() -> None:
    text = "Order 5551234 confirmed. Your verification code is 246810"
    assert extract_verification_code("", text) == "246810"
