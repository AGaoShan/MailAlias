# mail.com 别名（Alias）管理机制

本文基于 `maildotcom-sdk`（`tanu360/maildotcom-sdk`）的实现，梳理 mail.com 邮箱别名的管理原理、接口与操作流程。

## 1. 概览

mail.com 的别名管理分成**两套相互独立的接口体系**，职责不同：

| 能力 | 接口体系 | SDK 入口 | 说明 |
| --- | --- | --- | --- |
| 列出别名、修改显示名 | 移动 API（HSP2 / MobSI） | `client.account.aliases()`<br>`client.account.updateAliasDisplayName()` | 只读列表 + 改显示名 |
| 创建别名、删除别名、查询可用域名、设置默认发件人 | Web 设置接口（CATS） | `MailComWebAliasAddon` | 通过 web 设置 OAuth 桥接授权 |

简单说：**列表和改名走移动 API，增删和默认发件人设置走 Web 设置接口**。二者都需要登录拿 token。

## 2. 别名的基本约束

- **数量上限**：`MAILCOM_ALIAS_LIMIT = 10`。达到上限时 mail.com 返回文本 `The maximum number of Alias Addresses has been created. This e-mail-address could not be created`，SDK 在创建前也会本地预检。
- **地址格式**：`localPart@domain`，localPart 长度 3–62，字符集 `[a-z0-9._-]`，大小写归一为小写；不写 `@domain` 时默认 `mail.com`。
- **域名白名单**：`MAILCOM_ALIAS_DOMAINS`（`src/web-alias-domains.ts`），约 190 个 mail.com 系域名（`mail.com`、`email.com`、`usa.com`、`engineer.com`、`musician.org`…）。创建前先做静态白名单校验，再通过 `availableDomains()` 与服务器实际开放域名求交集。
- **可删除性**：别名对象带 `deletable` 字段，主地址/不可删地址 `deletable === false`，删除前 SDK 会拒绝。
- **状态/类型过滤**：列表查询只取 `state=ACTIVE` 且 `type in (MANAGED, DOMAIN_HOSTING)`（Web）或 `type in (SENDER, MAIL_COLLECT)`（移动 API）。

## 3. 数据模型

Web 设置接口返回的别名对象（`SettingsAlias`）关键字段：

```ts
interface SettingsAlias {
  type?: string;                    // 别名类型
  entryDate?: string;               // 创建时间
  address: string;                  // 完整别名地址
  displayName?: string;             // 发件人显示名
  deletable?: boolean;              // 是否允许删除
  pgpEnabled?: boolean;
  defaultSenderAddress?: boolean;   // 是否为默认发件人
  defaultReceiverAddress?: boolean; // 是否为默认收件人
  state?: string;                   // ACTIVE 等
  _links?: { self?: { href?: string } }; // 自链接，从中解析资源标识
}
```

列表响应包装为 `{ mailaddresslist: SettingsAlias[] }`。

## 4. Web 设置接口（CATS）详解

### 4.1 登录链路（OAuth 桥接）

`MailComWebAliasAddon.login()` 走一条浏览器模拟链路，最终拿到 settings access token：

1. **授权码**：请求 `https://oauth2.mail.com/authorize`
   - `client_id = mailcom_mailcheck_chrome`
   - `redirect_uri = https://lpebgcnlaohcgdfhbffjajlnpifdkllg.chromiumapp.org/`
   - `scope = mailbox_user_status_access mailbox_user_full_access login`
   - 携带随机 `state` 与 `login_hint`（用户邮箱）。
2. **登录页**：跟随重定向到 mlogin 页面，解析 `<input>` 表单字段，填入 `username` / `password`，POST 到 `https://login.mail.com/login`。
   - 需要 `authcode-context` 构造 `successURL` / `loginFailedURL` / `loginErrorURL`。
3. **换 token**：POST `https://oauth2.mail.com/token`（`grant_type=authorization_code`），使用内置 Basic Auth，校验返回 `state` 一致。
4. **建立 mail 会话**：POST `https://login.mail.com/oauth2login`（`service=mailint`，携带 access token 与 `partnerdata`），跟随到 navigator，改路径为 `/halogin&tz=5.5`，从重定向里取出 `sid`（会话 id）。
5. **换取设置 token**：POST `https://oauthbridge.navigator-lxa.mail.com/navigator/oauth2/token`
   - `Authorization: Basic bWFpbGNvbV9tYWlsc2V0X3Jvb3RfbGl2ZToqKioqKioq`
   - `grant_type = urn:mam:oauth:grant-type:spa`
   - `scope = mail_mailbox_w webmailer_setting_r webmailer_setting_w mail_confix_w`
   - 得到的 `access_token` 即 CATS 接口的 Bearer token。

整个链路使用 `fetch` + `redirect: "manual"`，并自带 `CookieJar` 累积 `set-cookie`。

### 4.2 请求公共头

所有 CATS 请求（`settingsRequest`）统一附加：

```
Authorization: Bearer <settingsAccessToken>
Origin:  https://mailset-root.mail.com
Referer: https://mailset-root.mail.com/
X-UI-App: mailcom.mailset-compose/1.0.5-build.322
X-Request-ID: <random UUID>
```

Base URL：`https://settings-cats.mail.com`。所有 URL 带 `absoluteURI=false`。

### 4.3 操作一览

| 操作 | 方法/路径 | Accept / Content-Type |
| --- | --- | --- |
| 列出别名 | `GET /mailaccount/primary/emailAddresses?absoluteURI=false&q.state.in=ACTIVE&q.type.in=MANAGED%2CDOMAIN_HOSTING` | `application/vnd.ui.trinity.mailaddress.list-v5+json` |
| 查询可用域名 | `GET /domains?absoluteURI=false&q.state.eq=ACTIVE&q.legacySupport.eq=true` | `application/json` |
| 校验地址可用性 | `POST /mailaccount/emailAddressValidations?absoluteURI=false`，body 为 `["address"]` | `...email-address-validation-response+json` / `...email-address-validation-request+json` |
| 创建别名 | `POST /mailaccount/primary/emailAddresses?absoluteURI=false` | `application/vnd.ui.trinity.minimalmailaddress-v3+json` |
| 删除别名 | `POST /mailaccount/primary/emailAddressesRemovals/{address}/removals?absoluteURI=false` | `text/plain;charset=UTF-8` |
| 设置默认发件人 | `PUT /emailAddresses/{identifier}?absoluteURI=false` | `application/vnd.ui.trinity.minimalmailaddress-v3+json` |

## 5. 核心操作流程

### 5.1 创建别名 `createAlias(address)`

```
1. 解析地址、校验域名在白名单内
2. listAliases()：数量 >= 10 拒绝；地址已存在拒绝
3. availableDomains()：域名不在服务器当前开放集合则拒绝
4. validateAddressAvailable()：POST 校验，返回非空对象表示不可用
5. POST 创建，body 字段：
   { address, deletable: true, pgpEnabled: false,
     defaultSenderAddress: false, defaultReceiverAddress: false, state: "ACTIVE" }
6. waitForAlias(address, true)：轮询最多 4 次（1s/2s/3s 退避）确认已出现在列表中
```

### 5.2 删除别名 `deleteAlias(address)`

```
1. findAlias() 确认存在
2. deletable === false 时拒绝
3. POST removals 接口
4. waitForAlias(address, false)：轮询确认已从列表消失
```

### 5.3 设置默认发件人 `setDefaultAlias(address, { sender })`

- `sender` 取值 `"email"`（纯邮箱）或 `"name-email"`（`显示名 <邮箱>`）。
- 选 `name-email` 要求别名已有 `displayName`。
- 通过 `_links.self.href` 解析资源标识（`emailaddresses/` 之后的部分），PUT 更新 `defaultSenderAddress: true`；选纯邮箱时同时把 `displayName` 置空。
- 更新后重新读取确认 `defaultSenderAddress === true`，否则报错。
- `defaultSenderOptions(address)` 返回可选项及当前选中态。

### 5.4 列出/改名（移动 API）

- `client.account.aliases()`：`GET /MailAccount/accountId/emailaddresses?absoluteURI=false&q.type.in=SENDER,MAIL_COLLECT&q.state.in=ACTIVE`。
- `client.account.updateAliasDisplayName(address, displayName)`：先取别名对象，再 `PUT /massrv/MailAccount/accountId/EmailAddress/{address}`，body 回填 `displayName` 与 `type/entryDate/address/defaultSenderAddress/defaultReceiverAddress/pgpEnabled/deletable` 等原字段。**改名后若要选 `name-email` 默认发件人，应先用此方法设置 displayName。**

## 6. 使用示例

```ts
import { MAILCOM_ALIAS_DOMAINS, MailComWebAliasAddon } from "maildotcom-sdk/web-aliases";

const webAliases = new MailComWebAliasAddon({
  email: process.env.MAILCOM_EMAIL!,
  password: process.env.MAILCOM_PASSWORD!,
});

await webAliases.login();
console.log(MAILCOM_ALIAS_DOMAINS);              // 静态域名白名单
const domains = await webAliases.availableDomains(); // 服务器当前可用子集

await webAliases.createAlias("my-alias@mail.com");
await webAliases.setDefaultAlias("my-alias@mail.com", { sender: "email" });
await webAliases.deleteAlias("my-alias@mail.com");
```

## 7. 注意事项

- 域名白名单是**静态**的，`createAlias()` 在登录前即拒绝名单外域名；真实可用性以 `availableDomains()` 为准。
- 创建/删除是**最终一致**的：接口返回后别名不会立即出现/消失，必须轮询确认（SDK 用 `waitForAlias`）。
- 内置 OAuth Basic Auth 常量来自官方 Chrome 扩展，属于公开客户端凭据；实际生产应评估其稳定性。
- 主地址、不可删地址受 `deletable` 保护；默认发件人别名按 mail.com 服务端行为处理。
- 别名的**列表与改名**请走移动 API，**增删与默认发件人**请走 Web 设置接口，不要混用。

## 参考资料

- 源码：`maildotcom-sdk/src/web-aliases.ts`、`src/web-alias-domains.ts`、`src/client.ts`
- 技能参考：`maildotcom-sdk/skills/maildotcom-sdk/references/api-cheatsheet.md`、`usage-patterns.md`
- 示例：`maildotcom-sdk/examples/01-account-and-aliases.ts`、`examples/13-web-alias-addon.ts`
