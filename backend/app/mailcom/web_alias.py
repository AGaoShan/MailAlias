"""mail.com HTTP 客户端：CookieJar、OAuth 桥接登录、CATS 设置接口、移动 API。

移植自 maildotcom-sdk（TanStack/TS 实现）到 httpx。
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from .errors import MailComApiError, MailComAuthError, MailComInvalidCredentialsError, MailComTimeoutError

WEB_OAUTH_CLIENT_ID = "mailcom_mailcheck_chrome"
WEB_OAUTH_REDIRECT_URI = "https://lpebgcnlaohcgdfhbffjajlnpifdkllg.chromiumapp.org/"
WEB_OAUTH_BASIC_AUTH = "Basic bWFpbGNvbV9tYWlsY2hlY2tfY2hyb21lOnRJWkNZWjFZOFFhNUt0MjJMVXJXSDJTc29td1VhV1F5dGszWWdNem4="
SETTINGS_OAUTH_BASIC_AUTH = "Basic bWFpbGNvbV9tYWlsc2V0X3Jvb3RfbGl2ZToqKioqKioq"
MAIL_SETTINGS_PARTNER_DATA = "eyJ1c2VjYXNlIjoiaW5ib3hfdW5yZWFkIiwiYXJncyI6W10sImlkIjoyLCJjYWxsZXJfYXBwIjoidG9vbGJhciIsImNhbGxlcl92ZXJzaW9uIjoiQ2hyb21lLzguMC41LjAifQ=="
SETTINGS_CATS_BASE_URL = "https://settings-cats.mail.com"
SETTINGS_OAUTH_BRIDGE_URL = "https://oauthbridge.navigator-lxa.mail.com/navigator/oauth2/token"
SETTINGS_OAUTH_GRANT_TYPE = "urn:mam:oauth:grant-type:spa"
SETTINGS_OAUTH_SCOPE = "mail_mailbox_w webmailer_setting_r webmailer_setting_w mail_confix_w"
SETTINGS_UI_APP = "mailcom.mailset-compose/1.0.5-build.322"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)


class CookieJar:
    def __init__(self) -> None:
        self._cookies: dict[str, str] = {}

    def add_from(self, response: httpx.Response) -> None:
        raw = response.headers.get_list("set-cookie")
        for cookie in raw:
            pair = cookie.split(";")[0]
            if not pair or "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            if key:
                self._cookies[key] = value

    def header(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in self._cookies.items())

    def load(self, data: dict[str, str]) -> None:
        self._cookies.update(data)

    def dump(self) -> dict[str, str]:
        return dict(self._cookies)


@dataclass
class SettingsSession:
    access_token: str
    cookies: dict[str, str] = field(default_factory=dict)


class MailComHttp:
    """底层 HTTP 会话封装，处理重定向、Cookie、超时与错误。"""

    def __init__(self, timeout: float = 30.0, proxy: str | None = None) -> None:
        self.timeout = timeout
        self.cookies = CookieJar()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            proxy=proxy,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        content: str | bytes | None = None,
        json: object = None,
        include_cookies: bool = True,
    ) -> httpx.Response:
        final_headers = {
            "User-Agent": WEB_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            final_headers.update(headers)
        if include_cookies:
            cookie = self.cookies.header()
            if cookie:
                final_headers["Cookie"] = cookie

        try:
            response = await self._client.request(
                method,
                url,
                headers=final_headers,
                data=data,
                content=content,
                json=json,
            )
        except httpx.TimeoutException as exc:
            raise MailComTimeoutError(f"mail.com request timed out: {url}") from exc
        except httpx.HTTPError as exc:
            raise MailComApiError(f"mail.com request failed: {url}: {exc}", retryable=True) from exc

        if include_cookies:
            self.cookies.add_from(response)

        if response.status_code >= 400:
            body = response.text[:300] if response.text else ""
            raise MailComApiError(
                f"{method} {url} failed with {response.status_code}{': ' + body if body else ''}",
                status=response.status_code,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        return response


def _redirect_location(response: httpx.Response, base_url: str) -> str:
    location = response.headers.get("location")
    if response.status_code not in range(300, 400) or not location:
        raise MailComAuthError(f"Expected mail.com redirect, got {response.status_code}.")
    return urljoin(base_url, location)


def _html_decode(value: str) -> str:
    return (
        value.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def _login_form_params(html: str, page_url: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", html, flags=re.IGNORECASE):
        name = re.search(r"\bname=([\"'])(.*?)\1", tag, flags=re.IGNORECASE)
        if not name:
            continue
        value_match = re.search(r"\bvalue=([\"'])(.*?)\1", tag, flags=re.IGNORECASE)
        params[name.group(2)] = _html_decode(value_match.group(2) if value_match else "")

    params.setdefault("service", "oauth2")
    if "successURL" not in params:
        query = dict(httpx.URL(page_url).params)
        authcode_context = query.get("authcode-context")
        if not authcode_context:
            raise MailComAuthError("mail.com login page did not include authcode-context.")
        params["successURL"] = f"https://oauth2.mail.com/authcode?authcode-context={authcode_context}"
        login_hint = query.get("login_hint", "")
        params["loginFailedURL"] = (
            "https://mlogin.mail.com/oauth2/?status=login-failed"
            f"&login_hint={login_hint}&authcode-context={authcode_context}"
        )
        params["loginErrorURL"] = "https://mlogin.mail.com/loginapplication/error/loginerror"
    return params


async def open_settings_session(email: str, password: str, http: MailComHttp) -> SettingsSession:
    """执行完整 OAuth 桥接登录，返回 CATS settings access token 与 Cookie。"""
    state = secrets.token_hex(12)
    auth_params = {
        "client_id": WEB_OAUTH_CLIENT_ID,
        "redirect_uri": WEB_OAUTH_REDIRECT_URI,
        "scope": "mailbox_user_status_access mailbox_user_full_access login",
        "response_type": "code",
        "hl": "en-US",
        "state": state,
        "login_hint": email,
    }
    authorize_url = str(httpx.URL("https://oauth2.mail.com/authorize", params=auth_params))
    authorize = await http.request(
        authorize_url,
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    mlogin_url = _redirect_location(authorize, authorize_url)
    mlogin = await http.request(
        mlogin_url,
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    login_params = _login_form_params(mlogin.text, mlogin_url)
    login_params["username"] = email
    login_params["password"] = password

    login = await http.request(
        "https://login.mail.com/login",
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://mlogin.mail.com",
            "Referer": mlogin_url,
        },
        data=login_params,
    )
    login_location = login.headers.get("location", "")
    # 密码错误 / 需要人工验证时，mail.com 会重定向到帮助页而非 authcode。
    if "support.mail.com" in login_location or "status=login-failed" in login_location:
        raise MailComInvalidCredentialsError("邮箱或密码错误，或该账号需要人工安全验证")
    authcode_url = _redirect_location(login, "https://login.mail.com/")
    authcode = await http.request(
        authcode_url,
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    callback_url = _redirect_location(authcode, "https://oauth2.mail.com/")
    callback = httpx.URL(callback_url)
    code = callback.params.get("code")
    if not code:
        raise MailComAuthError("mail.com web OAuth did not return an authorization code.")
    if callback.params.get("state") != state:
        raise MailComAuthError("mail.com web OAuth state mismatch.")

    token_response = await http.request(
        "https://oauth2.mail.com/token",
        method="POST",
        headers={
            "Authorization": WEB_OAUTH_BASIC_AUTH,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "client_id": WEB_OAUTH_CLIENT_ID,
            "redirect_uri": WEB_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    token = token_response.json()
    access_token = token.get("access_token")
    if not access_token:
        raise MailComAuthError("mail.com web OAuth did not return an access token.")

    oauth2login = await http.request(
        "https://login.mail.com/oauth2login",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "service": "mailint",
            "origin": "toolbar",
            "access_token": access_token,
            "successURL": "https://navigator-lxa.mail.com/login",
            "loginFailedURL": "http://www.mail.com/?status=nologin",
            "loginErrorURL": "http://www.mail.com/?status=nologin",
            "statistics": "",
            "partnerdata": MAIL_SETTINGS_PARTNER_DATA,
        },
    )
    navigator_url = httpx.URL(_redirect_location(oauth2login, "https://login.mail.com/"))
    await http.request(
        str(navigator_url),
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    # 对齐 SDK：仅替换 pathname，保留原有 query（partnerdata/origin/ott），再追加 tz
    navigator_url = navigator_url.copy_with(path="/halogin")
    navigator_url = navigator_url.copy_add_param("tz", "5.5")
    halogin = await http.request(
        str(navigator_url),
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    halogin_location = halogin.headers.get("location", "")
    if "status=nologin" in halogin_location or "support.mail.com" in halogin_location:
        raise MailComInvalidCredentialsError("mail.com 拒绝了本次登录，可能需要人工安全验证")
    if not halogin_location:
        raise MailComAuthError("mail.com 导航登录未按预期重定向（可能触发了风控，请稍后重试或减少登录频率）")
    navigator_root = httpx.URL(_redirect_location(halogin, str(navigator_url)))
    sid = navigator_root.params.get("sid")
    if not sid:
        raise MailComAuthError("mail.com 导航登录未返回会话标识 sid（可能触发了风控，请稍后重试）")
    await http.request(
        str(navigator_root),
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )

    bridge_url = httpx.URL(SETTINGS_OAUTH_BRIDGE_URL, params={"sid": sid})
    settings_token_response = await http.request(
        str(bridge_url),
        method="POST",
        headers={
            "Authorization": SETTINGS_OAUTH_BASIC_AUTH,
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://mailset-root.mail.com",
            "Referer": "https://mailset-root.mail.com/",
        },
        data={
            "grant_type": SETTINGS_OAUTH_GRANT_TYPE,
            "scope": SETTINGS_OAUTH_SCOPE,
        },
    )
    settings_token = settings_token_response.json()
    settings_access_token = settings_token.get("access_token")
    if not settings_access_token:
        raise MailComAuthError("mail.com settings OAuth bridge did not return an access token.")
    return SettingsSession(access_token=settings_access_token, cookies=http.cookies.dump())


async def settings_request(
    http: MailComHttp,
    access_token: str,
    path: str,
    *,
    method: str = "GET",
    accept: str | None = None,
    content_type: str | None = None,
    body: object = None,
    raw_body: str | None = None,
) -> httpx.Response:
    """调用 CATS 设置接口，附加统一请求头。"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Origin": "https://mailset-root.mail.com",
        "Referer": "https://mailset-root.mail.com/",
        "X-UI-App": SETTINGS_UI_APP,
        "X-Request-ID": str(uuid.uuid4()),
    }
    if accept:
        headers["Accept"] = accept
    if content_type:
        headers["Content-Type"] = content_type

    url = urljoin(SETTINGS_CATS_BASE_URL, path)
    if raw_body is not None:
        return await http.request(
            url,
            method=method,
            headers=headers,
            content=raw_body,
            include_cookies=False,
        )
    return await http.request(
        url,
        method=method,
        headers=headers,
        json=body,
        include_cookies=False,
    )
