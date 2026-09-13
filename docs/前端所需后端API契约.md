# 前端所需后端 API 契约（前端先行设计产出）

> 本文由前端设计阶段产出，作为前后端接口约定（Single Source of Truth）。
> 基础前缀：`/api/v1`；全部请求/响应为 JSON（除特别说明）。
> 认证：除 `POST /auth/login`、`GET /health`、取件地址 `GET /pickup/{account_key}/{address}` 外，
> 其余接口均需 `Authorization: Bearer <jwt>`；未认证返回 `401`。

## 0. 通用约定

### 0.1 错误响应

所有错误统一结构（FastAPI HTTPException detail 规整为对象）：

```json
{
  "detail": {
    "code": "ALIAS_LIMIT_REACHED",
    "message": "The maximum number of Alias Addresses has been created. This e-mail-address could not be created",
    "extra": { "domains": ["mail.com", "email.com"] }
  }
}
```

错误码枚举（前端按 code 做提示/跳转）：

| code | HTTP | 说明 |
| --- | --- | --- |
| `UNAUTHORIZED` | 401 | 未登录 / token 失效 |
| `ACCOUNT_SESSION_INVALID` | 401 | mail.com 账号会话失效，需重新验证 |
| `ALIAS_LIMIT_REACHED` | 409 | 别名已达上限（10） |
| `ALIAS_EXISTS` | 409 | 别名地址重复（幂等，返回已存在别名） |
| `DOMAIN_UNAVAILABLE` | 422 | 域名不可用，`extra.domains` 返回可用域名 |
| `ALIAS_NOT_DELETABLE` | 422 | 地址不可删除 |
| `UPSTREAM_ERROR` | 502 | 上游 5xx |
| `UPSTREAM_TIMEOUT` | 504 | 上游超时 |
| `CIRCUIT_OPEN` | 503 | 熔断打开，`extra.retry_after` |
| `RATE_LIMITED` | 429 | 限流，`extra.retry_after` |
| `NOT_FOUND` | 404 | 资源不存在 |
| `VALIDATION_ERROR` | 400 | 参数校验失败 |

### 0.2 分页

列表类接口当前均为全量返回（数据量小）。预留 `?limit=&offset=`，响应可含 `total`。

### 0.3 时间格式

统一 ISO8601 UTC 字符串，例：`2026-09-13T10:00:00Z`。

---

## 1. 认证 Auth

### POST `/auth/login`

请求：

```json
{ "username": "admin", "password": "admin123" }
```

响应 `200`：

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": 1, "username": "admin", "role": "admin" }
}
```

### GET `/auth/me`

响应 `200`：

```json
{ "id": 1, "username": "admin", "role": "admin", "created_at": "2026-09-13T00:00:00Z" }
```

### POST `/auth/logout`

响应 `204`（前端仅清理本地 token，幂等）。

---

## 2. 账号 Accounts

### 账号对象 AccountOut

```json
{
  "id": 1,
  "account_key": "acc_ab12cd",
  "email": "user@mail.com",
  "enabled": true,
  "alias_count": 3,
  "alias_limit": 10,
  "session_state": "active",
  "created_at": "2026-09-13T00:00:00Z",
  "updated_at": "2026-09-13T00:00:00Z"
}
```

- `session_state`：`active` | `expired` | `error` | `none`（前端状态色标）
- 响应绝不包含密码或密文。

### GET `/accounts`

响应 `200`：`AccountOut[]`

### POST `/accounts`

请求：

```json
{ "email": "user@mail.com", "password": "secret" }
```

行为：后端用 mail.com Web 接口登录验证 → 加密入库 → 建立会话。

响应 `201`：`AccountOut`

### DELETE `/accounts/{id}`

响应 `204`。

### POST `/accounts/{id}/verify`

行为：校验/重建该账号 mail.com 会话。

响应 `200`：

```json
{ "account_id": 1, "session_state": "active", "ok": true }
```

---

## 3. 别名 Aliases

### 别名对象 AliasOut

```json
{
  "id": 10,
  "account_id": 1,
  "account_email": "user@mail.com",
  "address": "my-alias@mail.com",
  "local_part": "my-alias",
  "domain": "mail.com",
  "display_name": null,
  "is_default_sender": false,
  "deletable": true,
  "state": "ACTIVE",
  "pickup_url": "http://localhost:8000/api/v1/pickup/acc_ab12cd/my-alias@mail.com",
  "created_at": "2026-09-13T00:00:00Z",
  "last_fetched_at": null
}
```

### GET `/accounts/{id}/aliases`

响应 `200`：`AliasOut[]`

### POST `/accounts/{id}/aliases`

请求：

```json
{ "address": "my-alias@mail.com" }
```

行为：计数校验 → 白名单 → 上游创建 → 落库 → 绑定取件地址。

响应 `201`：`AliasOut`

### DELETE `/aliases/{id}`

行为：上游删除 → 删除本地别名与绑定。

响应 `204`。

### POST `/aliases`

> **自动选号创建**：只需别名地址，后端自动挑选仍有别名额度的账号创建。

请求：

```json
{ "address": "my-alias@mail.com", "account_id": null }
```

- `address`：完整地址 `my-alias@mail.com`，或仅前缀 `my-alias`（默认补 `mail.com`）
- `account_id`：可选；指定则只在该账号创建，不填则自动选择

自动选择规则：过滤启用且未满 10 个别名的账号 → 剩余额度最多优先 → 已有别名最少 → id 最小。

响应 `201`：`AliasOut`

行为说明：

- **幂等**：若该别名已存在于任意账号，直接返回已存在的别名（不报错）
- 无可用账号 → `404 NOT_FOUND`；全部账号已满 → `409 ALIAS_LIMIT_REACHED`
- 域名不在白名单 → `422 DOMAIN_UNAVAILABLE`

### POST `/aliases/batch-generate`

> 指定**数量 + 后缀**，随机生成别名并批量创建。**能建多少建多少**，额度用尽的部分记为失败但不中断。

请求：

```json
{
  "count": 10,
  "domain": "mail.com",
  "account_id": null,
  "prefix": "",
  "length": 10
}
```

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `count` | — | 生成数量，1-100 |
| `domain` | `mail.com` | 后缀域名（须在 mail.com 可用域名白名单内） |
| `account_id` | `null` | 指定账号；不填则自动分配 |
| `prefix` | `""` | 可选固定前缀，便于识别 |
| `length` | `10` | 随机部分长度，6-40 |

随机前缀字符集：小写字母、数字，以及 `.` `-` `_` 分隔符（首尾不使用分隔符）。

**性能说明**

- 同一账号的创建操作**串行执行**（避免并发写入触发 mail.com 风控），不同账号可并行
- 上游别名列表与可用域名在单次批量会话内**只拉取一次**并复用
- 创建成功后**直接写入本地缓存**，不再回拉列表校验
- 单个别名纯上游耗时约 1.5s（地址校验 + 创建两步网络往返），这是 mail.com 的固有延迟

响应 `201`：

```json
{
  "requested": 10,
  "created": 8,
  "failed": 2,
  "items": [
    {
      "address": "kx7fq2m9z0@mail.com",
      "ok": true,
      "alias": { /* AliasOut */ },
      "error": null
    },
    {
      "address": "ab3x9k2m1q@mail.com",
      "ok": false,
      "alias": null,
      "error": { "code": "ALIAS_LIMIT_REACHED", "message": "所有账号的别名数量都已达上限" }
    }
  ]
}
```

### GET `/accounts/{id}/domains`

查询参数：`refresh`（默认 `false`）。默认读取**本地缓存**（TTL 7 天）；`refresh=true` 时强制回源 mail.com。

响应 `200`：`{ "account_id": 1, "domains": ["mail.com", "email.com", ...] }`

### PUT `/aliases/{id}/default-sender`

请求：

```json
{ "sender": "email" }
```

`sender` 取值 `email` | `name-email`（`name-email` 需别名已有 display_name，需先调用改名接口）。

响应 `200`：`AliasOut`

### GET `/accounts/{id}/domains`

响应 `200`：

```json
{ "account_id": 1, "domains": ["mail.com", "email.com", "usa.com"] }
```

### PUT `/aliases/{id}/display-name`

请求：

```json
{ "display_name": "My Alias" }
```

响应 `200`：`AliasOut`

---

## 4. 映射 Mappings

### GET `/mappings`

查询参数：`account_id`（可选，过滤）。

响应 `200`：

```json
{
  "total": 2,
  "items": [
    {
      "alias_id": 10,
      "account_id": 1,
      "account_email": "user@mail.com",
      "alias_address": "my-alias@mail.com",
      "pickup_url": "http://localhost:8000/api/v1/pickup/acc_ab12cd/my-alias@mail.com",
      "is_default_sender": false,
      "last_fetched_at": null
    }
  ]
}
```

### GET `/mappings/export?format=text|csv`

响应 `200`：

- `format=text`：`text/plain`，行格式 `alias----pickup_url`
- `format=csv`：`text/csv`，表头 `alias_address,pickup_url,account_email`

---

## 5. 取件 Pickup

### 取件消息对象 MessageOut

```json
{
  "id": "msg-123",
  "from": "a@b.com",
  "to": ["my-alias@mail.com"],
  "subject": "Hello",
  "date": "2026-09-13T10:00:00Z",
  "preview": "…",
  "read": false,
  "has_attachments": false,
  "folder": "INBOX"
}
```

### GET `/pickup/{account_key}/{address}`

> 该地址即“取件地址”，**无需 JWT**（可复制给外部调用）。
> **只返回投递到该别名的邮件**（按邮件 `To` 头过滤），不会暴露主邮箱其它邮件。

查询参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `amount` | 25 | 拉取数量 |
| `mark_read` | false | 是否标记已读 |
| `unread_only` | false | 仅未读 |
| `refresh` | false | 跳过缓存强制刷新 |

响应 `200`：

```json
{
  "pickup_url": "http://localhost:8000/api/v1/pickup/acc_ab12cd/my-alias@mail.com",
  "alias": "my-alias@mail.com",
  "account_key": "acc_ab12cd",
  "messages": [ /* MessageOut[] */ ],
  "total": 1,
  "stale": false,
  "fetched_at": "2026-09-13T10:00:00Z"
}
```

- `stale=true`：上游不可用，返回最近缓存。

### GET `/pickup/{account_key}/{address}/messages/{message_id}/body`

查询参数：`format=html|text`（默认 html）。

响应 `200`：

```json
{ "id": "msg-123", "format": "html", "body": "<html>…</html>" }
```

### POST `/pickup/batch`

请求：

```json
{ "pickup_urls": ["http://host/api/v1/pickup/acc_ab12cd/my-alias@mail.com"], "amount": 25 }
```

响应 `200`：逐地址返回，单项失败不影响其他。

```json
{
  "results": [
    {
      "pickup_url": "http://host/api/v1/pickup/acc_ab12cd/my-alias@mail.com",
      "alias": "my-alias@mail.com",
      "ok": true,
      "messages": [],
      "error": null
    }
  ]
}
```

### POST `/pickup/resolve`

请求：

```json
{ "pickup_url": "http://host/api/v1/pickup/acc_ab12cd/my-alias@mail.com" }
```

响应 `200`：

```json
{
  "account_key": "acc_ab12cd",
  "alias": "my-alias@mail.com",
  "account_id": 1,
  "account_email": "user@mail.com",
  "alias_id": 10
}
```

---

## 6. 仪表盘 Dashboard

### GET `/dashboard/stats`

响应 `200`：

```json
{
  "account_count": 2,
  "alias_count": 5,
  "mapping_count": 5,
  "alias_capacity": { "used": 5, "limit": 20 },
  "recent_fetches": [
    {
      "pickup_url": "http://host/api/v1/pickup/acc_ab12cd/my-alias@mail.com",
      "alias": "my-alias@mail.com",
      "message_count": 3,
      "fetched_at": "2026-09-13T10:00:00Z"
    }
  ]
}
```

---

## 7. 健康检查

### GET `/health`

无需认证。响应 `200`：

```json
{
  "status": "ok",
  "database": "ok",
  "accounts": [{ "account_key": "acc_ab12cd", "session_state": "active" }]
}
```

---

## 8. 前端调用清单（与本文件一一对应）

| 前端位置 | 调用 |
| --- | --- |
| LoginView | `POST /auth/login`、`GET /auth/me` |
| DashboardView | `GET /dashboard/stats` |
| AccountsView | `GET /accounts`、`POST /accounts`、`DELETE /accounts/{id}`、`POST /accounts/{id}/verify` |
| AliasesView | `GET /accounts/{id}/aliases`、`POST /accounts/{id}/aliases`、`DELETE /aliases/{id}`、`PUT /aliases/{id}/default-sender`、`GET /accounts/{id}/domains` |
| MappingsView | `GET /mappings`、`GET /mappings/export`、`GET /accounts` |
| PickupView | `GET /pickup/{account_key}/{address}`、`GET /pickup/.../body`、`POST /pickup/resolve`、`GET /mappings` |
