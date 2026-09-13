# mail.com 多账号别名管理与取件系统（全栈）— 设计方案

## 1. 目标

构建一个带前后端的 mail.com 多账号别名管理与取件系统：

1. **多账号管理**：配置并操作多个 mail.com 账号。
2. **别名管理**：为任意账号创建/删除别名、查询可用域名、设置默认发件人。
3. **别名—取件地址映射**：为每个别名生成并记录一个对应的**取件地址（收信/取件 API 地址）**。
4. **取件**：通过取件地址拉取指定别名收到的邮件。
5. **Web 界面**：账号、别名、映射、取件结果的图形化管理与展示。

核心数据形态：

```
别名邮箱地址 ---- 对应邮箱的取件地址
my-alias@mail.com ---- <pickup api url>
```

## 2. 技术选型

| 层 | 技术 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.11+ / FastAPI / Uvicorn | 异步、自带 OpenAPI |
| HTTP 客户端 | httpx | 调用 mail.com 接口 |
| 存储 | SQLite + SQLAlchemy 2.x | ORM + 迁移（Alembic 可选） |
| 加密 | cryptography（Fernet） | 凭据加密 |
| 前端 | Vue 3 + TypeScript + Vite | SPA |
| UI | Element Plus | 表格/表单/弹窗 |
| 状态/请求 | Pinia + Axios | 状态管理与 API 调用 |
| 部署 | 前后端分离，生产由 FastAPI 托管前端构建产物 | 单进程部署 |

## 3. 总体架构

```
┌───────────────────────────────────────────────────────┐
│                   Vue 3 SPA (Vite)                     │
│  账号管理 | 别名管理 | 映射列表 | 取件查看 | 设置          │
└───────────────────────┬───────────────────────────────┘
                        │ REST /api/v1 (JSON, JWT)
┌───────────────────────▼───────────────────────────────┐
│                    FastAPI 应用                        │
│  routers: accounts / aliases / mappings / pickup / auth│
│  ┌─────────────────────────────────────────────────┐  │
│  │               Service 层 (业务门面)               │  │
│  │  AccountService / AliasService / PickupService   │  │
│  └───┬───────────────┬───────────────────┬─────────┘  │
│      │               │                   │            │
│ ┌────▼──────────┐ ┌──▼────────────┐ ┌────▼──────────┐ │
│ │ MailComWebAlias│ │ PickupResolver │ │ PickupClient │ │
│ │ (CATS 接口)    │ │ 生成/反解地址   │ │ 按地址拉邮件  │ │
│ └────┬──────────┘ └───────────────┘ └────┬──────────┘ │
│      │                                   │            │
│ ┌────▼───────────────────────────────────▼──────────┐ │
│ │          SQLAlchemy + SQLite (accounts/aliases/…)  │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

前端静态资源在生产环境中挂载到 FastAPI，`/` 返回 `index.html`，`/assets/*` 返回打包文件，`/api/*` 走后端。

## 4. 取件地址（Pickup Address）定义

**取件地址**指一个可调用的**收信/取件 API 地址**，访问它即可拉取该别名收到的邮件。

生成规则：

```
pickup_url = f"{PICKUP_API_BASE}/api/v1/pickup/{account_key}/{local_part}@{domain}"
```

- `PICKUP_API_BASE`：本服务对外地址（可配置）。
- `account_key`：账号稳定标识。
- 取件地址与别名一一对应。

`PickupResolver` 职责：
- `build(account_key, alias_address) -> pickup_url`
- `parse(pickup_url) -> (account_key, alias_address)`

## 5. 数据模型（SQLite）

### 5.1 accounts

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| account_key | TEXT UNIQUE | 稳定标识 |
| email | TEXT UNIQUE | 登录邮箱 |
| password_enc | TEXT | 加密后的密码 |
| enabled | BOOLEAN | 是否启用 |
| created_at / updated_at | DATETIME | 时间戳 |

### 5.2 aliases

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| account_id | INTEGER FK | 所属账号 |
| address | TEXT | 别名完整地址 |
| local_part / domain | TEXT | 拆解字段 |
| display_name | TEXT | 显示名 |
| is_default_sender | BOOLEAN | 默认发件人 |
| deletable | BOOLEAN | 可删除性 |
| state | TEXT | 状态 |
| created_at | DATETIME | 时间 |
| UNIQUE(account_id, address) | | |

### 5.3 pickup_bindings

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| alias_id | INTEGER FK UNIQUE | 关联别名 |
| pickup_url | TEXT UNIQUE | 取件地址 |
| created_at | DATETIME | 创建时间 |
| last_fetched_at | DATETIME | 最近取件时间 |

### 5.4 sessions

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| account_id | INTEGER FK UNIQUE | 账号 |
| access_token | TEXT | token |
| token_type | TEXT | bearer |
| expires_at | DATETIME | 过期时间 |
| cookies | TEXT | Cookie JSON |
| updated_at | DATETIME | 更新时间 |

### 5.5 users（登录前端用）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| username | TEXT UNIQUE | 用户名 |
| password_hash | TEXT | 哈希密码 |
| role | TEXT | admin |
| created_at | DATETIME | 时间 |

### 5.6 fetch_log（可选）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| pickup_url | TEXT | 取件地址 |
| message_count | INTEGER | 数量 |
| fetched_at | DATETIME | 时间 |

## 6. 后端设计

### 6.1 项目结构

```
backend/
├── app/
│   ├── main.py                # FastAPI 实例、CORS、静态托管
│   ├── config.py              # Settings（pydantic-settings）
│   ├── database.py            # 引擎/Session
│   ├── deps.py                # 依赖注入（db、current_user）
│   ├── models/                # SQLAlchemy 模型
│   │   ├── account.py
│   │   ├── alias.py
│   │   ├── pickup.py
│   │   ├── session.py
│   │   └── user.py
│   ├── schemas/               # Pydantic 请求/响应模型
│   │   ├── account.py
│   │   ├── alias.py
│   │   ├── pickup.py
│   │   └── auth.py
│   ├── services/
│   │   ├── account_service.py
│   │   ├── alias_service.py
│   │   └── pickup_service.py
│   ├── mailcom/               # mail.com 接入层
│   │   ├── domains.py         # 域名白名单
│   │   ├── web_alias.py       # CATS Web 接口
│   │   ├── mobile_api.py      # 移动 API
│   │   └── resolver.py        # PickupResolver
│   ├── routers/
│   │   ├── auth.py
│   │   ├── accounts.py
│   │   ├── aliases.py
│   │   ├── mappings.py
│   │   └── pickup.py
│   └── security/
│       ├── crypto.py          # Fernet 加解密
│       └── jwt.py             # JWT 生成/校验
├── tests/
├── pyproject.toml
└── README.md
```

### 6.2 核心服务接口

```python
class AccountService:
    async def add(self, email: str, password: str) -> AccountOut: ...
    async def list(self) -> list[AccountOut]: ...
    async def delete(self, account_id: int) -> None: ...
    async def verify_login(self, account_id: int) -> bool: ...

class AliasService:
    async def create(self, account_id: int, address: str) -> AliasOut: ...
    async def delete(self, account_id: int, address: str) -> None: ...
    async def list(self, account_id: int) -> list[AliasOut]: ...
    async def domains(self, account_id: int | None = None) -> list[str]: ...
    async def set_default(self, alias_id: int, sender: str) -> None: ...

class PickupService:
    async def bind(self, alias_id: int) -> PickupBindingOut: ...
    async def fetch(self, pickup_url: str, amount: int = 25) -> list[MessageOut]: ...
    def export_mappings(self) -> list[str]: ...  # "alias----pickup"
```

### 6.3 REST API（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/login` | 登录，返回 JWT |
| GET | `/auth/me` | 当前用户 |
| GET | `/accounts` | 账号列表 |
| POST | `/accounts` | 添加账号（验证登录后入库） |
| DELETE | `/accounts/{id}` | 删除账号 |
| POST | `/accounts/{id}/verify` | 校验账号会话 |
| GET | `/accounts/{id}/aliases` | 别名列表 |
| POST | `/accounts/{id}/aliases` | 创建别名 + 绑定取件地址 |
| DELETE | `/aliases/{id}` | 删除别名及映射 |
| PUT | `/aliases/{id}/default-sender` | 设置默认发件人 |
| GET | `/accounts/{id}/domains` | 该账号可用域名 |
| GET | `/mappings` | 全部“别名----取件地址”映射 |
| GET | `/mappings/export?format=text\|csv` | 导出映射 |
| GET | `/pickup/{account_key}/{address}` | 取件地址（拉邮件） |
| POST | `/pickup/resolve` | 由取件地址反查别名信息 |

### 6.4 请求/响应示例

创建别名：

```json
POST /api/v1/accounts/1/aliases
{ "address": "my-alias@mail.com" }

201 Created
{
  "id": 10,
  "account_id": 1,
  "address": "my-alias@mail.com",
  "local_part": "my-alias",
  "domain": "mail.com",
  "is_default_sender": false,
  "deletable": true,
  "pickup_url": "https://host/api/v1/pickup/acc_ab12/my-alias@mail.com"
}
```

取件：

```json
GET /api/v1/pickup/acc_ab12/my-alias@mail.com?amount=25&mark_read=false

200 OK
{
  "pickup_url": "https://host/api/v1/pickup/acc_ab12/my-alias@mail.com",
  "alias": "my-alias@mail.com",
  "messages": [
    { "id": "…", "from": "a@b.com", "subject": "Hello", "date": "2026-09-13T10:00:00Z", "preview": "…" }
  ]
}
```

## 7. 前端设计

### 7.1 项目结构

```
frontend/
├── index.html
├── vite.config.ts        # dev 代理 /api -> 后端
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/index.ts
│   ├── stores/
│   │   ├── auth.ts
│   │   ├── account.ts
│   │   └── alias.ts
│   ├── api/
│   │   ├── client.ts     # axios 实例 + 拦截器
│   │   ├── accounts.ts
│   │   ├── aliases.ts
│   │   └── pickup.ts
│   ├── views/
│   │   ├── LoginView.vue
│   │   ├── DashboardView.vue
│   │   ├── AccountsView.vue
│   │   ├── AliasesView.vue
│   │   ├── MappingsView.vue
│   │   └── PickupView.vue
│   └── components/
│       ├── AccountForm.vue
│       ├── AliasCreateDialog.vue
│       └── MessageList.vue
└── package.json
```

### 7.2 页面功能

| 页面 | 功能 |
| --- | --- |
| 登录页 | 用户名/密码登录，保存 JWT |
| 仪表盘 | 账号数、别名数、最近取件概览 |
| 账号管理 | 增删账号、验证登录状态 |
| 别名管理 | 按账号查看/创建/删除别名、设默认发件人、展示取件地址 |
| 映射列表 | 表格展示“别名邮箱地址 ---- 取件地址”，支持复制/导出 |
| 取件查看 | 输入或选择取件地址，拉取并展示邮件列表 |

### 7.3 交互要点

- Axios 拦截器统一附加 `Authorization: Bearer <jwt>`，401 跳登录。
- 创建别名成功后自动刷新映射列表并高亮新行。
- 映射表提供“复制取件地址”“一键导出 CSV”。
- 取件结果支持按时间倒序、点击查看正文。

## 8. 安全与凭据

- mail.com 账号密码用 Fernet 加密存储，密钥来自 `MAILCOM_SECRET_KEY`。
- 前端用户密码用 bcrypt/argon2 哈希。
- JWT 有过期时间，支持刷新。
- 数据库文件与密钥权限收紧；日志脱敏。
- CORS 仅允许配置的前端来源。

## 9. 配置项

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MAILCOM_DB_PATH` | SQLite 路径 | `./data/mailcom.db` |
| `MAILCOM_SECRET_KEY` | 加密密钥 | 必填 |
| `JWT_SECRET` | JWT 签名密钥 | 必填 |
| `JWT_EXPIRE_MINUTES` | JWT 有效期 | `1440` |
| `PICKUP_API_BASE` | 对外取件基地址 | `http://localhost:8000` |
| `CORS_ORIGINS` | 允许来源 | `http://localhost:5173` |
| `MAILCOM_TIMEOUT` | 请求超时 | `30` |
| `MAX_ALIASES_PER_ACCOUNT` | 每账号别名上限 | `10` |
| `PICKUP_CONCURRENCY_PER_ACCOUNT` | 单账号并发取件数 | `2` |
| `PICKUP_GLOBAL_CONCURRENCY` | 全局并发取件上限 | `8` |
| `RATE_LIMIT_PER_ACCOUNT_QPS` | 单账号请求速率（次/秒） | `1` |
| `RATE_LIMIT_GLOBAL_QPS` | 全局请求速率（次/秒） | `5` |
| `RETRY_MAX_ATTEMPTS` | 最大重试次数 | `3` |
| `RETRY_BASE_DELAY` | 重试基础退避（秒） | `1.0` |
| `CIRCUIT_FAIL_THRESHOLD` | 熔断失败阈值 | `5` |
| `CIRCUIT_COOLDOWN` | 熔断冷却（秒） | `60` |
| `PICKUP_CACHE_TTL` | 取件结果缓存（秒） | `30` |

## 9.1 并发取件设计

取件涉及外部 mail.com 接口，必须限制并发以避免触发风控与流量过载。

**双层信号量 + 单账号串行队列**：

```
全局 Semaphore(PICKUP_GLOBAL_CONCURRENCY)      # 保护整体流量
  └─ 每账号 Semaphore(PICKUP_CONCURRENCY_PER_ACCOUNT)  # 保护单账号
       └─ 每账号 asyncio.Lock / 串行队列              # 同账号取件串行化
```

- **同账号串行**：同一 mail.com 账号的取件请求串行执行（`asyncio.Lock` 或 `asyncio.Queue`），因为同一会话的邮件列表接口对并发敏感，且共享 token/cookie。
- **跨账号并行**：不同账号之间用 `asyncio.gather` 并行，但受全局信号量约束。
- **锁超时**：获取锁设置超时（如 `MAILCOM_TIMEOUT`），超时返回 `429/503` 而非无限等待。
- **请求去重（Single-flight）**：同一 `pickup_url` 的并发请求合并为一次上游调用，其余等待其结果（用 `dict[str, asyncio.Future]` 实现）。

```python
class PickupScheduler:
    def __init__(self, global_limit: int, per_account_limit: int):
        self._global = asyncio.Semaphore(global_limit)
        self._per_account: dict[int, asyncio.Semaphore] = {}
        self._account_locks: dict[int, asyncio.Lock] = {}
        self._inflight: dict[str, asyncio.Future] = {}

    async def run(self, account_id: int, key: str, coro_factory):
        if key in self._inflight:          # single-flight 去重
            return await asyncio.shield(self._inflight[key])
        fut = asyncio.get_event_loop().create_future()
        self._inflight[key] = fut
        try:
            async with self._global, self._per_account(account_id):
                async with self._account_locks.setdefault(account_id, asyncio.Lock()):
                    result = await coro_factory()
            fut.set_result(result)
            return result
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)
```

## 9.2 流量控制（限流）

**令牌桶限流**，分为账号级与全局级：

- 每账号 `RATE_LIMIT_PER_ACCOUNT_QPS`（默认 1 次/秒），避免单账号高频命中。
- 全局 `RATE_LIMIT_GLOBAL_QPS`（默认 5 次/秒），保护出口 IP。
- 对**写操作**（创建/删除别名）额外降速，写操作之间强制间隔（默认 2s），降低风控概率。
- 前端请求进入后端后，若有缓存命中且未过期直接返回，不消耗上游额度。

```python
class TokenBucket:
    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = rate
        self.capacity = capacity or rate
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                await asyncio.sleep((tokens - self._tokens) / self.rate)
```

**合并请求**：批量取件接口 `POST /pickup/batch` 接收多地址，后端按账号分组、统一限流调度，减少往返。

## 9.3 缓存策略

- 取件结果按 `pickup_url + amount` 缓存 `PICKUP_CACHE_TTL` 秒（默认 30）。
- 缓存键含 `account_id`，不同账号隔离。
- 写操作（创建/删除别名、改默认发件人）后使相关别名缓存失效。
- 可选持久化最近一次取件结果到 `fetch_log`，用于仪表盘展示。

## 9.4 容错机制

**分层容错**：

| 机制 | 说明 |
| --- | --- |
| 重试 | 对网络错误、超时、5xx 使用指数退避重试（最多 `RETRY_MAX_ATTEMPTS`，带抖动 jitter），4xx（除 429）不重试 |
| 熔断 | 单账号连续失败达 `CIRCUIT_FAIL_THRESHOLD` 后打开熔断，冷却 `CIRCUIT_COOLDOWN` 秒内直接快速失败，避免雪崩 |
| 降级 | 上游不可用时，返回 `fetch_log` 中最近一次缓存结果并标注 `stale=true` |
| 隔离 | 多账号批处理逐账号返回结果，单账号失败不影响其他账号 |
| 会话自愈 | token 失效（401/403）自动重新登录一次，仍失败则标记账号 `session_error` |
| 幂等 | 创建别名前查重、删除别名按地址幂等；重复请求返回已存在/已删除的结果 |
| 超时 | 所有上游请求设置连接/读取超时，禁止无限等待 |

```python
class CircuitBreaker:
    def __init__(self, fail_threshold: int, cooldown: float):
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.cooldown:
            self._opened_at = None
            self._failures = 0
            return True
        return False

    def on_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_threshold:
            self._opened_at = time.monotonic()
```

**错误分类与 HTTP 映射**：

| 上游情况 | 本地 HTTP | 说明 |
| --- | --- | --- |
| 别名已达 10 个 | 409 | 返回明确提示 |
| 地址重复 | 409 | 幂等返回已有别名 |
| 域名不可用 | 422 | 列出可用域名 |
| 不可删除地址 | 422 | 拒绝并说明 |
| 上游 5xx / 超时 | 502 / 504 | 触发重试与熔断 |
| 熔断打开 / 限流拒 | 503 / 429 | 返回 `Retry-After` |
| 账号会话失效 | 401 | 前端提示重新验证账号 |

## 9.5 别名上限（每账号最多 10 个）

mail.com 硬性限制每账号最多 **10 个别名**（`MAX_ALIASES_PER_ACCOUNT`），需多层防护：

1. **常量定义**：`MAX_ALIASES_PER_ACCOUNT = 10`，并提供官方错误文案常量：
   `The maximum number of Alias Addresses has been created. This e-mail-address could not be created`。
2. **创建前本地预检**：统计 `aliases` 表中该账号记录数（以本地为准）`>= 10` 立即拒绝，不发起上游请求。
3. **事务内校验**：创建别名与计数检查放在同一数据库事务，并对账号行加锁（`SELECT ... FOR UPDATE` 语义 / SQLite 写事务），防止并发创建突破上限。
4. **上游兜底**：即使预检通过，若上游返回上限错误，捕获并转为 409，同时同步本地计数。
5. **展示**：前端在账号卡片显示 `已用别名 8/10`，达上限时禁用“创建”按钮。

```python
async def create_alias(self, account_id: int, address: str) -> AliasOut:
    async with self._write_lock(account_id):          # 每账号写锁，串行化创建/删除
        async with self.db.begin():                    # 事务内校验
            count = await self._count_aliases(account_id)
            if count >= MAX_ALIASES_PER_ACCOUNT:
                raise AliasLimitError(MAX_ALIASES_MESSAGE)
            # 白名单/重复/availableDomains 校验后调用上游创建
            ...
```

> 注意：别名删除后计数随之释放；删除与创建共用同一把账号写锁，保证计数一致。

## 9.6 可观测性

- **指标**：上游请求数、成功率、P95 延迟、限流等待时长、熔断状态、每账号别名使用率（x/10）。
- **日志**：结构化日志记录 `account_key`、`pickup_url`、重试次数、错误分类，密码与 token 脱敏。
- **健康检查**：`/api/v1/health` 返回数据库连通性与各账号会话状态概览。

## 10. 关键流程

### 10.1 添加账号

```
前端表单 → POST /accounts → 后端用 WebAlias 登录验证 → 加密存库 → 返回账号
```

### 10.2 创建别名并生成取件地址

```
前端选账号填地址 → POST /accounts/{id}/aliases
后端（单账号写锁 + 事务）：
     别名计数校验（>= 10 拒绝，见 §9.5）
     → 白名单校验 → 重复检查 → availableDomains 复核
     → CATS 创建 + 轮询确认 → aliases 落库
     → PickupResolver.build() → pickup_bindings 落库
→ 返回别名 + 取件地址，前端展示 “别名----取件地址”
```

### 10.3 取件

```
前端选/填取件地址 → GET /pickup/{account_key}/{address}
后端：
     parse 取件地址 → 查缓存（命中且未过期直接返回）
     → PickupScheduler 调度（全局/账号双层并发 + 同账号串行 + single-flight 去重）
     → 令牌桶限流 → 熔断检查
     → 定位账号会话（必要时登录）→ 移动 API 拉邮件
     → 更新 last_fetched_at、写 fetch_log、写缓存
→ 返回列表（降级时带 stale=true）
```

## 11. 实施计划（里程碑）

| 阶段 | 内容 | 产出 |
| --- | --- | --- |
| M1 | 后端骨架：FastAPI、配置、SQLite、模型与迁移 | `backend/app` |
| M2 | 登录与会话：mail.com OAuth 桥接 + token 缓存 | `mailcom/web_alias.py` |
| M3 | 别名服务与 API：创建/删除/列表/域名/默认发件人 | routers + services |
| M4 | 取件：Resolver、绑定落库、取件 API | `pickup.py` |
| M5 | 认证与安全：JWT、凭据加密 | `security/` |
| M6 | 并发与流量：双层信号量、single-flight、令牌桶限流、缓存 | `pickup/scheduler.py` |
| M7 | 容错：重试、熔断、降级、别名上限三层防护 | `pickup/resilience.py` |
| M8 | 前端骨架：Vite、路由、Pinia、Axios | `frontend/` |
| M9 | 前端页面：账号/别名/映射/取件（含 8/10 用量展示） | views |
| M10 | 联调与静态托管、CORS | main.py |
| M11 | 测试：并发、限流、容错、上限边界 | tests |

## 12. 错误处理

- **别名上限**：每账号最多 10 个，三层防护（本地预检 → 事务内校验 → 上游兜底），见 §9.5。
- 其余语义：重复、域名不可用、不可删除地址明确报错（HTTP 映射见 §9.4）。
- 创建/删除后轮询确认（1s/2s/3s 退避）。
- token 失效自动重登一次；网络超时按指数退避重试，单账号连续失败触发熔断。
- 多账号批处理逐账号返回结果，单账号失败不中断。
- 上游不可用时降级返回最近缓存并标注 `stale=true`。

## 13. 依赖

后端：`fastapi`、`uvicorn[standard]`、`httpx`、`sqlalchemy`、`pydantic-settings`、`cryptography`、`passlib[bcrypt]`、`python-jose[cryptography]`、`alembic`。

前端：`vue`、`vue-router`、`pinia`、`axios`、`element-plus`、`typescript`、`vite`。

## 参考资料

- `docs/mail.com-alias-management.md`：mail.com 别名管理机制
- `maildotcom-sdk/src/web-aliases.ts`、`src/web-alias-domains.ts`、`src/client.ts`
