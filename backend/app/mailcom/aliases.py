"""mail.com 别名操作：创建/删除/列表/域名/默认发件人（CATS 设置接口）。

移植自 maildotcom-sdk 的 MailComWebAliasAddon。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .domains import MAILCOM_ALIAS_DOMAIN_SET
from .errors import (
    MailComAliasExistsError,
    MailComAliasLimitError,
    MailComDomainUnavailableError,
    MailComError,
    MailComNotDeletableError,
    MailComValidationError,
)
from .web_alias import MailComHttp, SettingsSession, open_settings_session, settings_request

MAILCOM_ALIAS_LIMIT = 10
MAILCOM_ALIAS_LIMIT_MESSAGE = (
    "The maximum number of Alias Addresses has been created. This e-mail-address could not be created"
)

_LIST_ACCEPT = "application/vnd.ui.trinity.mailaddress.list-v5+json"
_MINIMAL_ACCEPT = "application/vnd.ui.trinity.minimalmailaddress-v3+json"
_VALIDATION_RESPONSE = "application/vnd.ui.trinity.email-address-validation-response+json"
_VALIDATION_REQUEST = "application/vnd.ui.trinity.email-address-validation-request+json"


@dataclass
class SettingsAlias:
    address: str
    display_name: str | None = None
    deletable: bool = True
    default_sender_address: bool = False
    default_receiver_address: bool = False
    pgp_enabled: bool = False
    state: str = "ACTIVE"
    type: str | None = None
    entry_date: str | None = None
    self_href: str | None = None
    raw: dict | None = None

    @classmethod
    def from_json(cls, data: dict) -> SettingsAlias:
        links = data.get("_links") or {}
        self_link = links.get("self") or {}
        return cls(
            address=data.get("address", ""),
            display_name=data.get("displayName"),
            deletable=data.get("deletable", True),
            default_sender_address=data.get("defaultSenderAddress", False),
            default_receiver_address=data.get("defaultReceiverAddress", False),
            pgp_enabled=data.get("pgpEnabled", False),
            state=data.get("state", "ACTIVE"),
            type=data.get("type"),
            entry_date=data.get("entryDate"),
            self_href=self_link.get("href"),
            raw=data,
        )


def split_alias_address(value: str) -> tuple[str, str, str]:
    trimmed = value.strip().lower()
    parts = trimmed.split("@")
    if len(parts) > 2 or not parts[0]:
        raise MailComValidationError(f"别名地址格式不正确：{value}")
    local_part = parts[0]
    domain = parts[1] if len(parts) == 2 and parts[1] else "mail.com"
    if domain not in MAILCOM_ALIAS_DOMAIN_SET:
        raise MailComDomainUnavailableError(f"不支持该别名域名：{domain}")
    if not re.fullmatch(r"[a-z0-9._-]{3,62}", local_part):
        raise MailComValidationError("别名前缀需为 3-62 位，仅允许小写字母、数字、点、下划线、连字符")
    return local_part, domain, f"{local_part}@{domain}"


def _alias_identifier(alias: SettingsAlias) -> str:
    href = alias.self_href
    if href:
        marker = "emailaddresses/"
        index = href.lower().find(marker)
        if index >= 0:
            return href[index + len(marker) :]
    return alias.address


def _minimal_alias(alias: SettingsAlias, patch: dict | None = None) -> dict:
    raw = dict(alias.raw or {})
    raw.update(patch or {})
    result: dict = {"address": raw.get("address", alias.address)}
    for key in (
        "type",
        "entryDate",
        "displayName",
        "deletable",
        "pgpEnabled",
        "defaultSenderAddress",
        "defaultReceiverAddress",
        "state",
    ):
        if raw.get(key) is not None or (key in raw and raw.get(key) is None and key == "displayName"):
            if key in raw:
                result[key] = raw[key]
    return result


class MailComAliasClient:
    """封装单个 mail.com 账号的别名相关操作。"""

    def __init__(self, http: MailComHttp, session: SettingsSession) -> None:
        self._http = http
        self._session = session
        # 实例内缓存：批量创建时避免每个别名都重复拉取列表与域名
        self._aliases_cache: list[SettingsAlias] | None = None
        self._domains_cache: list[str] | None = None

    def invalidate_cache(self) -> None:
        self._aliases_cache = None

    @classmethod
    async def login(cls, email: str, password: str, timeout: float = 30.0) -> MailComAliasClient:
        http = MailComHttp(timeout=timeout)
        session = await open_settings_session(email, password, http)
        return cls(http, session)

    @classmethod
    def from_session(
        cls,
        access_token: str,
        cookies: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> MailComAliasClient:
        """用已持久化的 settings token + Cookie 直接构造客户端，避免重复登录。"""
        http = MailComHttp(timeout=timeout)
        if cookies:
            http.cookies.load(cookies)
        session = SettingsSession(access_token=access_token, cookies=dict(cookies or {}))
        return cls(http, session)

    async def verify_session(self) -> bool:
        """轻量校验当前 settings token 是否仍然有效。

        仅把明确的鉴权失败（401/403）视为失效；
        网络抖动、5xx、限流等瞬时问题不应导致丢弃有效会话、触发全量重登。
        """
        try:
            await self.list_aliases()
            return True
        except MailComError as exc:
            status = getattr(exc, "status", None)
            return status not in (401, 403)

    @property
    def access_token(self) -> str:
        return self._session.access_token

    @property
    def cookies(self) -> dict[str, str]:
        return dict(self._http.cookies.dump())

    async def close(self) -> None:
        await self._http.close()

    async def list_aliases(self, *, use_cache: bool = True) -> list[SettingsAlias]:
        if use_cache and self._aliases_cache is not None:
            return self._aliases_cache
        response = await settings_request(
            self._http,
            self._session.access_token,
            "/mailaccount/primary/emailAddresses?absoluteURI=false&q.state.in=ACTIVE&q.type.in=MANAGED%2CDOMAIN_HOSTING",
            accept=_LIST_ACCEPT,
            content_type=_LIST_ACCEPT,
        )
        data = response.json()
        aliases = [SettingsAlias.from_json(item) for item in data.get("mailaddresslist", [])]
        self._aliases_cache = aliases
        return aliases

    async def available_domains(self, *, use_cache: bool = True) -> list[str]:
        if use_cache and self._domains_cache is not None:
            return self._domains_cache
        response = await settings_request(
            self._http,
            self._session.access_token,
            "/domains?absoluteURI=false&q.state.eq=ACTIVE&q.legacySupport.eq=true",
            accept="application/json",
            content_type="application/json",
        )
        server_domains = {
            item.get("domain", "").strip().lower() for item in response.json().get("domains", []) if item.get("domain")
        }
        from .domains import MAILCOM_ALIAS_DOMAINS

        domains = [domain for domain in MAILCOM_ALIAS_DOMAINS if domain in server_domains]
        self._domains_cache = domains
        return domains

    async def _validate_address_available(self, address: str) -> None:
        response = await settings_request(
            self._http,
            self._session.access_token,
            "/mailaccount/emailAddressValidations?absoluteURI=false",
            method="POST",
            accept=_VALIDATION_RESPONSE,
            content_type=_VALIDATION_REQUEST,
            body=[address],
        )
        if response.json():
            raise MailComValidationError(f"Alias address is not available: {address}")

    async def find_alias(self, address: str) -> SettingsAlias | None:
        normalized = address.lower()
        for alias in await self.list_aliases():
            if alias.address.lower() == normalized:
                return alias
        return None

    async def create_alias(
        self,
        address: str,
        *,
        max_aliases: int = MAILCOM_ALIAS_LIMIT,
    ) -> SettingsAlias:
        """创建别名。

        会基于上游真实别名列表做额度与重复校验；该列表在实例内缓存，
        因此同一批量会话中多次创建不会重复拉取（仅创建后失效一次）。
        """
        _local_part, domain, normalized = split_alias_address(address)
        if domain not in MAILCOM_ALIAS_DOMAIN_SET:
            raise MailComDomainUnavailableError(f"Alias domain is not supported by mail.com: {domain}")

        aliases = await self.list_aliases()
        if len(aliases) >= max_aliases:
            raise MailComAliasLimitError(MAILCOM_ALIAS_LIMIT_MESSAGE)
        if any(alias.address.lower() == normalized for alias in aliases):
            raise MailComAliasExistsError(f"Alias already exists: {normalized}")

        available = await self.available_domains()
        if domain not in available:
            raise MailComDomainUnavailableError(f"Alias domain is not available: {domain}", domains=available)

        await self._validate_address_available(normalized)
        await settings_request(
            self._http,
            self._session.access_token,
            "/mailaccount/primary/emailAddresses?absoluteURI=false",
            method="POST",
            accept=_MINIMAL_ACCEPT,
            content_type=_MINIMAL_ACCEPT,
            body={
                "address": normalized,
                "deletable": True,
                "pgpEnabled": False,
                "defaultSenderAddress": False,
                "defaultReceiverAddress": False,
                "state": "ACTIVE",
            },
        )
        # 上游已返回成功，直接在本地缓存中补一条，
        # 避免再拉一次完整列表（这是批量创建的主要耗时来源之一）。
        created = SettingsAlias(
            address=normalized,
            display_name=None,
            deletable=True,
            default_sender_address=False,
            default_receiver_address=False,
            pgp_enabled=False,
            state="ACTIVE",
        )
        if self._aliases_cache is not None:
            self._aliases_cache.append(created)
        return created

    async def delete_alias(self, address: str) -> None:
        _lp, _domain, normalized = split_alias_address(address)
        alias = await self.find_alias(normalized)
        if alias is None:
            raise MailComValidationError(f"Alias not found: {normalized}")
        if alias.deletable is False:
            raise MailComNotDeletableError(f"Alias is not allowed for deletion: {normalized}")

        await settings_request(
            self._http,
            self._session.access_token,
            f"/mailaccount/primary/emailAddressesRemovals/{normalized}/removals?absoluteURI=false",
            method="POST",
            accept="text/plain;charset=UTF-8",
            content_type="text/plain;charset=UTF-8",
        )
        # 上游已接受删除，本地缓存同步移除，避免再拉一次列表
        if self._aliases_cache is not None:
            self._aliases_cache = [item for item in self._aliases_cache if item.address.lower() != normalized]

    async def set_default_sender(self, address: str, sender: str = "email") -> SettingsAlias:
        _lp, _domain, normalized = split_alias_address(address)
        alias = await self.find_alias(normalized)
        if alias is None:
            raise MailComValidationError(f"Alias not found: {normalized}")
        if sender == "name-email" and not (alias.display_name or "").strip():
            raise MailComValidationError(f"Default sender option not available for {normalized}: name-email")

        patch: dict = {"defaultSenderAddress": True}
        if sender == "email":
            patch["displayName"] = ""
        payload = _minimal_alias(alias, patch)
        identifier = _alias_identifier(alias)
        await settings_request(
            self._http,
            self._session.access_token,
            f"/emailAddresses/{identifier}?absoluteURI=false",
            method="PUT",
            accept=_MINIMAL_ACCEPT,
            content_type=_MINIMAL_ACCEPT,
            body=payload,
        )
        updated = await self.find_alias(normalized)
        if updated is None or not updated.default_sender_address:
            raise MailComValidationError(f"Default sender was not updated: {normalized}")
        return updated

    async def set_display_name(self, address: str, display_name: str) -> SettingsAlias:
        _lp, _domain, normalized = split_alias_address(address)
        alias = await self.find_alias(normalized)
        if alias is None:
            raise MailComValidationError(f"Alias not found: {normalized}")
        payload = _minimal_alias(alias, {"displayName": display_name})
        identifier = _alias_identifier(alias)
        await settings_request(
            self._http,
            self._session.access_token,
            f"/emailAddresses/{identifier}?absoluteURI=false",
            method="PUT",
            accept=_MINIMAL_ACCEPT,
            content_type=_MINIMAL_ACCEPT,
            body=payload,
        )
        updated = await self.find_alias(normalized)
        if updated is None:
            raise MailComValidationError(f"Alias not found after update: {normalized}")
        return updated
