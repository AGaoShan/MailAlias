"""mail.com 接入层错误类型。"""

from __future__ import annotations


class MailComError(Exception):
    """mail.com 接入层基础异常。"""

    code = "UPSTREAM_ERROR"
    http_status = 502

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status = status


class MailComAuthError(MailComError):
    """mail.com 账号会话失效。

    注意：这里刻意不使用 401，避免与前端“登录态失效”混淆。
    """

    code = "ACCOUNT_SESSION_INVALID"
    http_status = 409


class MailComInvalidCredentialsError(MailComError):
    """邮箱或密码错误，或账号需要人工安全验证。"""

    code = "INVALID_CREDENTIALS"
    http_status = 422


class MailComApiError(MailComError):
    code = "UPSTREAM_ERROR"
    http_status = 502


class MailComNotFoundError(MailComError):
    code = "NOT_FOUND"
    http_status = 404


class MailComValidationError(MailComError):
    code = "VALIDATION_ERROR"
    http_status = 400


class MailComAliasLimitError(MailComValidationError):
    code = "ALIAS_LIMIT_REACHED"
    http_status = 409


class MailComAliasExistsError(MailComValidationError):
    code = "ALIAS_EXISTS"
    http_status = 409


class MailComDomainUnavailableError(MailComValidationError):
    code = "DOMAIN_UNAVAILABLE"
    http_status = 422

    def __init__(self, message: str, domains: list[str] | None = None) -> None:
        super().__init__(message)
        self.domains = domains or []


class MailComNotDeletableError(MailComValidationError):
    code = "ALIAS_NOT_DELETABLE"
    http_status = 422


class MailComTimeoutError(MailComError):
    code = "UPSTREAM_TIMEOUT"
    http_status = 504

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class MailComRateLimitedError(MailComError):
    code = "RATE_LIMITED"
    http_status = 429
