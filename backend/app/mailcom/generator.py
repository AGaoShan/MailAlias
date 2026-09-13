"""随机别名前缀生成。

mail.com 规则：前缀 3-62 位，仅允许小写字母、数字、点、下划线、连字符。
"""

from __future__ import annotations

import secrets

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
# 可用的分隔符（不会连续出现，也不会作为首尾字符）
_SEPARATORS = ".-_"


def random_local_part(length: int = 10, *, prefix: str = "", separators: bool = True) -> str:
    """生成随机别名前缀。

    - 保证长度在 3-62 之间
    - 保证首尾是字母/数字（避免某些上游对首尾分隔符的兼容问题）
    - 保证小写（mail.com 大小写不敏感，统一小写避免重复）
    """
    normalized_prefix = "".join(char for char in prefix.strip().lower() if char in _ALPHABET or char in _SEPARATORS)[
        :20
    ]
    total = max(3, min(62, length))
    random_len = max(1, total - len(normalized_prefix))

    body_chars: list[str] = []
    previous_is_separator = normalized_prefix.endswith(tuple(_SEPARATORS)) if normalized_prefix else False
    for _ in range(random_len):
        if separators and not previous_is_separator and random_len > 4 and secrets.randbelow(5) == 0:
            body_chars.append(secrets.choice(_SEPARATORS))
            previous_is_separator = True
        else:
            body_chars.append(secrets.choice(_ALPHABET))
            previous_is_separator = False

    # 随机部分首尾不使用分隔符
    if body_chars and body_chars[0] in _SEPARATORS:
        body_chars[0] = secrets.choice(_ALPHABET)
    if body_chars and body_chars[-1] in _SEPARATORS:
        body_chars[-1] = secrets.choice(_ALPHABET)

    local_part = f"{normalized_prefix}{''.join(body_chars)}"
    local_part = local_part[:62]
    if len(local_part) < 3:
        local_part += "".join(secrets.choice(_ALPHABET) for _ in range(3 - len(local_part)))
    return local_part
