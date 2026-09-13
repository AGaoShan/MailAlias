"""路由通用工具：mail.com 错误 -> HTTP 响应。"""

from __future__ import annotations

from fastapi import HTTPException

from ..mailcom import MailComDomainUnavailableError, MailComError


def to_http_exception(exc: MailComError) -> HTTPException:
    detail: dict = {"code": exc.code, "message": exc.message}
    if isinstance(exc, MailComDomainUnavailableError) and exc.domains:
        detail["extra"] = {"domains": exc.domains}
    retry_after = getattr(exc, "retry_after", None)
    headers = None
    if retry_after:
        headers = {"Retry-After": str(int(retry_after))}
    elif exc.http_status == 429:
        headers = {"Retry-After": "1"}
    return HTTPException(status_code=exc.http_status, detail=detail, headers=headers)
