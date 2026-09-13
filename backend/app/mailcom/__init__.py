from .aliases import (
    MAILCOM_ALIAS_LIMIT,
    MAILCOM_ALIAS_LIMIT_MESSAGE,
    MailComAliasClient,
    SettingsAlias,
    split_alias_address,
)
from .domains import MAILCOM_ALIAS_DOMAIN_SET, MAILCOM_ALIAS_DOMAINS
from .errors import (
    MailComAliasExistsError,
    MailComAliasLimitError,
    MailComApiError,
    MailComAuthError,
    MailComDomainUnavailableError,
    MailComError,
    MailComInvalidCredentialsError,
    MailComNotDeletableError,
    MailComNotFoundError,
    MailComRateLimitedError,
    MailComTimeoutError,
    MailComValidationError,
)
from .mobile_api import Message, MobileClient, MobileSession
from .resolver import PickupResolver

__all__ = [
    "MAILCOM_ALIAS_LIMIT",
    "MAILCOM_ALIAS_LIMIT_MESSAGE",
    "MailComAliasClient",
    "SettingsAlias",
    "split_alias_address",
    "MAILCOM_ALIAS_DOMAINS",
    "MAILCOM_ALIAS_DOMAIN_SET",
    "MailComError",
    "MailComAuthError",
    "MailComInvalidCredentialsError",
    "MailComApiError",
    "MailComValidationError",
    "MailComAliasLimitError",
    "MailComAliasExistsError",
    "MailComDomainUnavailableError",
    "MailComNotDeletableError",
    "MailComNotFoundError",
    "MailComTimeoutError",
    "MailComRateLimitedError",
    "MobileClient",
    "MobileSession",
    "Message",
    "PickupResolver",
]
