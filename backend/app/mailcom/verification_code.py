"""从邮件主题/正文中提取验证码。

不同服务的验证码格式差异很大，按优先级尝试多种模式，
并尽量避开日期、金额、订单号等干扰数字。
"""

from __future__ import annotations

import re

# 提示词附近的数字优先级最高（中/英/越多语言常见写法）
_CODE_WITH_LABEL = re.compile(
    r"(?:"
    r"code|otp|pin|password|verification|verify|security|"
    r"mã|ma|contraseña|código|codigo|verifizierung|bestätigungscode|"
    r"код|пароль|كود|رمز|認証|コード|인증|코드|验证码|驗證碼|口令|动态码|动态密码"
    r")"
    r"[\s:：\-—is]*"
    r"([0-9]{4,8})",
    re.IGNORECASE,
)

# 通用：独立的 4-8 位数字（允许被空格/连字符分隔，如 065 474）
_STANDALONE_CODE = re.compile(r"(?<![0-9A-Za-z])([0-9]{4,8})(?![0-9A-Za-z])")

# 形如 065-474 / 06 54 74 / 12 34 56 的分组验证码
_GROUPED_CODE = re.compile(r"(?<!\d)(\d{2,4})[\s\-](\d{2,4})(?:[\s\-](\d{2,4}))?(?!\d)")

# 需要排除的干扰：日期、时间、金额、长数字（订单号/手机号）
_NOISE_PATTERNS = (
    re.compile(r"\b(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b"),  # 日期
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"),  # 时间
    re.compile(r"\b\d{9,}\b"),  # 9 位以上（订单号、手机号）
)


def extract_verification_code(*texts: str) -> str | None:
    """从给定文本中提取验证码；找不到返回 None。

    优先取带提示词（code/验证码/OTP 等）的数字，其次取独立数字。
    """
    for text in texts:
        if not text:
            continue
        cleaned = _strip_noise(text)

        labeled = _CODE_WITH_LABEL.search(cleaned)
        if labeled:
            return labeled.group(1)

        grouped = _GROUPED_CODE.search(cleaned)
        if grouped:
            digits = "".join(part for part in grouped.groups() if part)
            if 4 <= len(digits) <= 8:
                return digits

        standalone = _STANDALONE_CODE.search(cleaned)
        if standalone:
            return standalone.group(1)

    return None


def _strip_noise(text: str) -> str:
    """移除明显会造成误判的片段（日期、时间、超长数字）。"""
    result = text
    for pattern in _NOISE_PATTERNS:
        result = pattern.sub(" ", result)
    return result
