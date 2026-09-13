# mail.com 多账号别名管理与取件系统 — 后端

FastAPI + SQLAlchemy(SQLite) 实现，接口契约见 [`../docs/前端所需后端API契约.md`](../docs/前端所需后端API契约.md)。

## 快速开始

```bash
cd backend
# 首次：创建 64 位虚拟环境并安装依赖
uv venv .venv --python 3.12 --clear
uv pip install --python .venv/Scripts/python.exe \
  "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "httpx>=0.28.0" \
  "sqlalchemy>=2.0.36" "pydantic-settings>=2.6.0" "cryptography>=44.0.0" \
  "python-jose[cryptography]>=3.3.0" "python-multipart>=0.0.20" "email-validator>=2.2.0"

# 配置（可复制 .env.example 为 .env）
cp .env.example .env

# 启动
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后：

- 界面： http://127.0.0.1:8000/ （自动托管 `../frontend/dist` 构建产物）
- 接口文档： http://127.0.0.1:8000/docs
- 默认管理员： `admin` / `admin123`（首次启动自动创建）

> 前端需先构建：`cd ../frontend && npm install && npm run build`。

## 配置项（`.env`）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MAILCOM_DB_PATH` | SQLite 路径 | `./data/mailcom.db` |
| `MAILCOM_SECRET_KEY` | mail.com 凭据加密密钥（Fernet） | 开发默认值，**生产必改** |
| `JWT_SECRET` | JWT 签名密钥 | 开发默认值，**生产必改** |
| `JWT_EXPIRE_MINUTES` | JWT 有效期（分钟） | `1440` |
| `PICKUP_API_BASE` | 对外取件基地址 | `http://localhost:8000` |
| `CORS_ORIGINS` | 允许来源，逗号分隔 | `http://localhost:5173,http://localhost:8000` |
| `MAILCOM_TIMEOUT` | 上游请求超时（秒） | `30` |
| `MAX_ALIASES_PER_ACCOUNT` | 每账号别名上限 | `10` |
| `PICKUP_CONCURRENCY_PER_ACCOUNT` | 单账号取件并发 | `2` |
| `PICKUP_GLOBAL_CONCURRENCY` | 全局取件并发 | `8` |
| `RATE_LIMIT_PER_ACCOUNT_QPS` | 单账号限流 | `1` |
| `RATE_LIMIT_GLOBAL_QPS` | 全局限流 | `5` |
| `RETRY_MAX_ATTEMPTS` / `RETRY_BASE_DELAY` | 重试次数 / 退避基数 | `3` / `1.0` |
| `CIRCUIT_FAIL_THRESHOLD` / `CIRCUIT_COOLDOWN` | 熔断阈值 / 冷却秒 | `5` / `60` |
| `PICKUP_CACHE_TTL` | 取件缓存秒数 | `30` |
| `FRONTEND_DIST` | 前端构建产物目录 | `../frontend/dist` |

## 目录结构

```
backend/
├── app/
│   ├── main.py            # 应用入口、CORS、静态托管、健康检查
│   ├── config.py          # 配置（pydantic-settings）
│   ├── database.py        # 引擎与会话
│   ├── deps.py            # 依赖注入（db / 当前用户 / 调度器单例）
│   ├── models/            # SQLAlchemy 模型
│   ├── schemas/           # Pydantic 请求/响应模型
│   ├── services/          # 业务服务（账号/别名/取件）
│   ├── mailcom/           # mail.com 接入层（OAuth / CATS / 移动 API / 取件调度）
│   ├── routers/           # REST 路由
│   └── security/          # Fernet 加密、JWT、密码哈希
├── tests/                 # pytest
└── pyproject.toml
```

## mail.com 接入说明

接入层由 `maildotcom-sdk`（TypeScript）移植为 Python：

- **登录**：`mailcom/web_alias.py` 模拟浏览器 OAuth 桥接，取得 CATS settings token（别名增删、域名、默认发件人）。
- **别名**：`mailcom/aliases.py` 对应 CATS 设置接口（`settings-cats.mail.com`）。
- **取件**：`mailcom/mobile_api.py` 走移动 API（HSP2）读取邮件列表与正文。
- **容错**：`mailcom/resilience.py` 提供令牌桶限流、指数退避重试、熔断。
- **调度**：`mailcom/scheduler.py` 实现双层信号量 + 同账号串行 + single-flight 去重 + TTL 缓存。
- **取件地址**：`mailcom/resolver.py` 生成/反解 `/{PICKUP_API_BASE}/api/v1/pickup/{account_key}/{alias}`。

## 测试与检查

```bash
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m ruff check app tests
```

## 关键行为

- 每账号别名上限 10：**本地预检 → 上游兜底**，返回 `409 ALIAS_LIMIT_REACHED`。
- 取件地址无需 JWT，可复制给外部调用；管理接口均需 `Authorization: Bearer <jwt>`。
- 上游不可用且存在历史记录时，降级返回最近缓存并标注 `stale=true`。
- 错误统一为 `{"detail": {"code", "message", "extra?"}}`。
