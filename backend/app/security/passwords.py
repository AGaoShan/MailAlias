"""密码哈希与校验。"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 260_000
_ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS)
    return f"pbkdf2_{_ALGORITHM}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        name = algorithm.replace("pbkdf2_", "")
        expected = hashlib.pbkdf2_hmac(name, password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        return hmac.compare_digest(expected.hex(), digest)
    except (ValueError, AttributeError):
        return False
