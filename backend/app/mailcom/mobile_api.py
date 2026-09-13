"""mail.com 移动 API（HSP2）接入：登录、列邮件、取正文、标记已读。

移植自 maildotcom-sdk 的 MailComClient 中与本系统取件相关的部分。
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import httpx

from .errors import MailComApiError, MailComAuthError, MailComError
from .verification_code import extract_verification_code

OAUTH_BASE_URL = "https://oauth2.mail.com"
MOBSI_BASE_URL = "https://mobsi.mail.com/rest/MobSI"
HSP2_BASE_URL = "https://hsp2.mail.com/service"

APP_USER_AGENT = (
    "mailcom.android.androidmail/9.8.0 Dalvik/2.1.0 (Linux; U; Android 13; SM-S908E Build/TQ2B.230505.005.A1)"
)
WEBVIEW_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; SM-S908E Build/TQ2B.230505.005.A1; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Mobile Safari/537.36 "
    "[APPNME/mailcom.android.androidmail;APPVS/9.8.0;APPTNME/andall]"
)
APP_HEADERS = {
    "Accept-Charset": "utf-8",
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "User-Agent": APP_USER_AGENT,
    "X-Ui-App": "mailcom.android.androidmail/9.8.0",
}
ANDROID_CLIENT_ID = "mailcom_mailapp_android"
ANDROID_REDIRECT_URI = "com.mail.androidmail.redirect://authorization_code_grant"
ANDROID_BASIC_AUTH = "Basic bWFpbGNvbV9tYWlsYXBwX2FuZHJvaWQ6a2luMmxTU2tVUXRRQ0NsWG9YZklOaEp1bUc2SmQwM0taNVdMN05KOQ=="
FULL_ACCESS_SCOPE = (
    "mailbox_user_full_access mailbox_user_status_access hsp_user_full_access "
    "onlinestorage_user_meta_read onlinestorage_user_meta_write foo bar"
)
DEFAULT_EXCLUDED_FOLDERS = ("TRASH", "DRAFTS", "OUTBOX")
MESSAGES_MIME = "application/vnd.ui.trinity.messages+json"
BODY_HTML = "text/vnd.ui.insecure+html; removeCharsetMetaInfo=true"
BODY_PREVIEW_SSE = "text/event-stream; length=300; builder=html"
BATCH_UPDATE = "application/vnd.ui.trinity.message.batchupdate-v2+json"
BATCH_UPDATE_RESULT = "application/vnd.ui.trinity.message.batchupdate.result-v2+json"


def _parse_sse_json(text: str) -> list[dict]:
    """解析 SSE 响应中的 JSON data 行（对齐 SDK 的 parseSseJsonData）。"""
    payloads: list[dict] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [line[len("data:") :].strip() for line in block.split("\n") if line.startswith("data:")]
        if not data_lines:
            continue
        raw = "\n".join(data_lines).strip()
        if not raw.startswith("{") and not raw.startswith("["):
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
        elif isinstance(parsed, list):
            payloads.extend(item for item in parsed if isinstance(item, dict))
    return payloads


def _base64_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _escape_condition_value(value: str) -> str:
    """转义条件查询中的特殊字符（对齐 SDK 的 escapeMailConditionValue）。"""
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _parse_mail_id(uri: str) -> str:
    if not uri:
        return uri
    if "/" in uri:
        return uri.rsplit("/", 1)[-1]
    return uri


@dataclass
class MobileSession:
    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None
    cookies: dict[str, str] = field(default_factory=dict)


@dataclass
class Message:
    id: str
    from_addr: str
    to: list[str]
    subject: str
    date: str
    preview: str = ""
    read: bool = True
    has_attachments: bool = False
    folder: str = ""
    mail_uri: str = ""
    code: str | None = None


def _normalize_date(value: object) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            ts = float(value) / 1000 if value > 1e11 else float(value)
            return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return str(value)
    except (ValueError, OSError, OverflowError):
        return str(value)


class MobileClient:
    """单账号移动 API 客户端，负责取件相关的邮件读取。"""

    def __init__(
        self,
        email: str,
        password: str | None,
        *,
        timeout: float = 30.0,
        session: MobileSession | None = None,
        proxy: str | None = None,
    ) -> None:
        self.email = email
        self.password = password
        self.timeout = timeout
        self.session = session
        self._logged_in = False
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            proxy=proxy,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self) -> MobileSession:
        """确保已登录。

        对齐 SDK 的 login()：仅在这里做一次令牌校验，
        之后同一实例内重复调用直接复用，不再探活。
        """
        if self._logged_in and self.session is not None:
            return self.session
        if self.session and self.session.access_token and await self._validate_token(self.session.access_token):
            self._logged_in = True
            return self.session
        if self.session and self.session.refresh_token:
            try:
                session = await self._refresh(self.session.refresh_token)
                self._logged_in = True
                return session
            except MailComError:
                pass
        if not self.password:
            raise MailComAuthError("Password is required when no valid cached session exists.")
        session = await self._login_android_oauth()
        self._logged_in = True
        return session

    async def _validate_token(self, token: str) -> bool:
        try:
            response = await self._client.request(
                "HEAD",
                f"{MOBSI_BASE_URL}/UserData",
                headers={**APP_HEADERS, "Accept": "application/json", "Authorization": f"Bearer {token}"},
            )
            return response.status_code < 400
        except httpx.HTTPError:
            return False

    async def _refresh(self, refresh_token: str) -> MobileSession:
        response = await self._client.post(
            f"{OAUTH_BASE_URL}/token",
            headers={
                **APP_HEADERS,
                "Accept": "*/*",
                "Authorization": ANDROID_BASIC_AUTH,
                "Content-Type": 'application/x-www-form-urlencoded;charset="UTF-8"',
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": FULL_ACCESS_SCOPE,
            },
        )
        data = response.json() if response.content else {}
        if not response.is_success or not data.get("access_token"):
            raise MailComAuthError(data.get("error_description") or data.get("error") or "token refresh failed")
        session = MobileSession(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or refresh_token,
            expires_at=None,
        )
        # 必须写回实例，否则 _auth_headers() 仍会发送旧令牌导致 401
        self.session = session
        return session

    async def _login_android_oauth(self) -> MobileSession:
        verifier = _base64_url(secrets.token_bytes(48))
        challenge = _base64_url(hashlib.sha256(verifier.encode()).digest())
        state = _base64_url(secrets.token_bytes(48))
        cookies: dict[str, str] = {}

        params = {
            "client_id": ANDROID_CLIENT_ID,
            "redirect_uri": ANDROID_REDIRECT_URI,
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "login_hint": self.email,
            "code_challenge_method": "S256",
        }
        authorize_url = f"{OAUTH_BASE_URL}/authorize?{urlencode(params)}"
        authorize = await self._webview(authorize_url, cookies)
        login_app_url = self._required_location(authorize, "authorize redirect")
        authcode_context = httpx.URL(login_app_url).params.get("authcode-context")
        if not authcode_context:
            raise MailComAuthError("Android OAuth login did not return authcode-context.")

        await self._webview(login_app_url, cookies)

        login_failed = (
            "https://auth.mail.com/loginapp/oauth2?status=login_failed"
            f"&login_hint={self.email}&authcode-context={authcode_context}"
        )
        login_form = {
            "password": self.password,
            "service": "oauth2",
            "successURL": f"{OAUTH_BASE_URL}/authcode?authcode-context={authcode_context}",
            "loginFailedURL": login_failed,
            "loginErrorURL": "https://auth.mail.com/login/error",
            "statistics": "",
            "username": self.email,
        }
        login = await self._webview(
            "https://login.mail.com/login",
            cookies,
            method="POST",
            data=login_form,
            extra_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://auth.mail.com",
                "Referer": login_app_url,
            },
        )
        authcode_url = self._required_location(login, "login redirect")
        authcode = await self._webview(authcode_url, cookies)
        app_redirect = self._required_location(authcode, "authcode redirect")
        redirect_url = httpx.URL(app_redirect)
        code = redirect_url.params.get("code")
        if not code:
            raise MailComAuthError("Android OAuth login did not return authorization code.")
        if redirect_url.params.get("state") != state:
            raise MailComAuthError("Android OAuth state mismatch.")

        token_response = await self._client.post(
            f"{OAUTH_BASE_URL}/token",
            headers={
                **APP_HEADERS,
                "Accept": "*/*",
                "Authorization": ANDROID_BASIC_AUTH,
                "Content-Type": 'application/x-www-form-urlencoded;charset="UTF-8"',
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": ANDROID_REDIRECT_URI,
                "client_id": ANDROID_CLIENT_ID,
                "code_verifier": verifier,
            },
        )
        token = token_response.json() if token_response.content else {}
        if not token.get("access_token") or not token.get("refresh_token"):
            raise MailComAuthError(token.get("error_description") or token.get("error") or "token exchange failed")
        self.session = MobileSession(
            access_token=token["access_token"],
            refresh_token=token["refresh_token"],
            expires_at=None,
        )
        # 与 SDK 一致：授权码换取的令牌尚不能直接用于 HSP2，需再刷新一次拿到可用令牌
        return await self._refresh(token["refresh_token"])

    async def _webview(
        self,
        url: str,
        cookies: dict[str, str],
        *,
        method: str = "GET",
        data: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {
            "User-Agent": WEBVIEW_USER_AGENT,
            "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
        }
        if extra_headers:
            headers.update(extra_headers)
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        response = await self._client.request(method, url, headers=headers, data=data)
        for raw in response.headers.get_list("set-cookie"):
            pair = raw.split(";")[0]
            if "=" in pair:
                key, _, value = pair.partition("=")
                cookies[key] = value
        return response

    def _required_location(self, response: httpx.Response, label: str) -> str:
        location = response.headers.get("location")
        if not location:
            raise MailComAuthError(f"Android OAuth {label} did not include Location header.")
        return location

    async def _auth_headers(self) -> dict[str, str]:
        if not self.session or not self.session.access_token:
            await self.login()
        assert self.session is not None
        return {**APP_HEADERS, "Accept": "application/json", "Authorization": f"Bearer {self.session.access_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        retry_headers = kwargs.pop("retry_headers", {})
        headers = {**await self._auth_headers(), **dict(kwargs.pop("headers", {}))}
        response = await self._client.request(method, url, headers=headers, **kwargs)

        # 对齐 SDK：401 时优先用 refresh_token 续期，仅在无法刷新时才全量登录。
        if response.status_code in (401, 403):
            refreshed = await self._reauthenticate()
            if refreshed:
                headers = {**await self._auth_headers(), **retry_headers}
                response = await self._client.request(method, url, headers=headers, **kwargs)

        if response.status_code >= 400:
            raise MailComApiError(
                f"{method} {url} failed with {response.status_code}",
                status=response.status_code,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        return response

    async def _reauthenticate(self) -> bool:
        """令牌被拒后的恢复：先刷新，失败再全量登录。返回是否成功拿到新令牌。"""
        if self.session and self.session.refresh_token:
            try:
                await self._refresh(self.session.refresh_token)
                self._logged_in = True
                return True
            except MailComError:
                pass
        if not self.password:
            return False
        try:
            await self._login_android_oauth()
            self._logged_in = True
            return True
        except MailComError:
            return False

    async def list_messages(
        self,
        amount: int = 25,
        *,
        unread_only: bool = False,
        recipient: str | None = None,
    ) -> list[Message]:
        """列出邮件。

        recipient 非空时，仅返回**投递到该地址的邮件**（按 To 头过滤），
        避免别名取件时把主邮箱的全部邮件都暴露出去。
        """
        await self.login()
        headers = {"Accept": MESSAGES_MIME}
        params = {
            "absoluteURI": "false",
            "orderBy": "INTERNALDATE desc",
            "amount": str(amount),
            "tagsShowAll": "true",
        }

        conditions: list[str] = []
        if unread_only:
            conditions.append("mail.flag.unseen:true")
        if recipient:
            conditions.append(f"mail.header:to:{_escape_condition_value(recipient)}")
        if conditions:
            params["condition"] = " ".join(conditions)

        folder_uris = await self._incoming_folder_ids()
        messages: list[Message] = []
        for folder_id in folder_uris:
            url = f"{HSP2_BASE_URL}/msgsrv/Mailbox/primaryMailbox/Folder/{folder_id}/Mail?{urlencode(params)}"
            response = await self._request("GET", url, headers=headers)
            text = response.text.strip()
            if not text:
                continue
            try:
                data = response.json()
            except ValueError:
                continue
            for item in data.get("mail", []):
                messages.append(self._to_message(item))
        messages.sort(key=lambda item: item.date, reverse=True)
        messages = messages[:amount]

        # 列表接口不返回正文摘要，需单独调用 bodypreviews 接口补全，
        # 否则前端只能看到主题（验证码就在摘要里）。
        if messages:
            previews = await self._fetch_previews([message.id for message in messages])
            for message in messages:
                message.preview = previews.get(message.id, "")
                # 从主题与摘要中提取验证码，便于前端直接展示
                message.code = extract_verification_code(message.subject, message.preview)

        return messages

    async def _fetch_previews(self, mail_ids: list[str]) -> dict[str, str]:
        """批量获取邮件正文摘要（SSE 响应）。失败时返回空，不影响列表。"""
        if not mail_ids:
            return {}
        url = f"{HSP2_BASE_URL}/msgsrv/Mailbox/primaryMailbox/Mail/bodypreviews"
        try:
            response = await self._request(
                "POST",
                url,
                headers={
                    "Accept": BODY_PREVIEW_SSE,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content="&".join(f"mailIdentifier={quote(str(mid), safe='')}" for mid in mail_ids),
            )
        except MailComError:
            return {}

        previews: dict[str, str] = {}
        for payload in _parse_sse_json(response.text):
            identifier = payload.get("mailIdentifier")
            if identifier:
                previews[str(identifier)] = str(payload.get("preview") or "")
        return previews

    async def _incoming_folder_ids(self) -> list[str]:
        url = f"{HSP2_BASE_URL}/msgsrv/Mailbox/primaryMailbox/folders?absoluteURI=false"
        response = await self._request(
            "GET",
            url,
            headers={"Accept": "application/vnd.ui.trinity.folders-v5+json"},
        )
        data = response.json()
        excluded = {item.upper() for item in DEFAULT_EXCLUDED_FOLDERS}
        result: list[str] = []

        def walk(folders: list[dict]) -> None:
            for folder in folders:
                folder_type = (folder.get("attribute") or {}).get("folderType", "")
                folder_id = folder.get("folderIdentifier", "")
                if folder_id and folder_type and folder_type.upper() not in excluded:
                    result.append(folder_id)
                walk(folder.get("folders") or [])

        walk(data.get("folders") or [])
        return result

    def _to_message(self, item: dict) -> Message:
        header = item.get("mailHeader") or {}
        attribute = item.get("attribute") or {}
        attachments = (item.get("attachments") or {}).get("attachment") or []
        to_list = header.get("to") or []
        if isinstance(to_list, str):
            to_list = [to_list]
        return Message(
            id=_parse_mail_id(attribute.get("mailIdentifier") or item.get("mailURI") or ""),
            from_addr=header.get("from", ""),
            to=list(to_list),
            subject=header.get("subject", ""),
            date=_normalize_date(header.get("date")),
            preview=item.get("preview", ""),
            read=attribute.get("read", True),
            has_attachments=bool(attachments),
            folder=attribute.get("folderType", ""),
            mail_uri=item.get("mailURI", ""),
        )

    async def get_body(self, mail_id: str, *, fmt: str = "html", mark_read: bool = False) -> str:
        await self.login()
        accept = "text/plain" if fmt == "text" else BODY_HTML
        url = f"{HSP2_BASE_URL}/msgsrv/Mailbox/primaryMailbox/Mail/{mail_id}/Body?absoluteURI=false"
        response = await self._request("GET", url, headers={"Accept": accept})
        if mark_read:
            await self.mark_read(mail_id)
        return response.text

    async def mark_read(self, mail_ids: str | list[str]) -> None:
        ids = [mail_ids] if isinstance(mail_ids, str) else mail_ids
        await self.login()
        url = f"{HSP2_BASE_URL}/msgsrv/Mailbox/primaryMailbox/MailBatchUpdate"
        await self._request(
            "POST",
            url,
            headers={"Accept": BATCH_UPDATE_RESULT, "Content-Type": BATCH_UPDATE},
            json={
                "read": True,
                "mailURIs": [f"mail/{_parse_mail_id(item)}" if "/" not in item else item for item in ids],
            },
        )
