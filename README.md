# mail.com 多账号别名管理与取件系统

带前后端的 mail.com 多账号别名管理与取件系统：多账号配置、别名增删、别名—取件地址映射，以及按取件地址拉取邮件。

```
别名邮箱地址 ---- 对应邮箱的取件地址
my-alias@mail.com ---- http://localhost:8000/api/v1/pickup/acc_ab12cd/my-alias@mail.com
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + Axios |
| 后端 | Python 3.11+ / FastAPI / Uvicorn / SQLAlchemy 2.x / SQLite |
| 接入 | 由 `maildotcom-sdk`(TS) 移植的 Python mail.com 接入层（OAuth 桥接 / CATS / 移动 API） |
| 安全 | Fernet 加密凭据、JWT 鉴权、PBKDF2 密码哈希 |
| 部署 | 前后端分离开发；生产由 FastAPI 托管前端构建产物（单进程） |

## 目录结构

```
├── docs/                      # 设计文档与前后端接口契约
│   ├── mail.com-多账号别名与取件-设计方案.md
│   ├── mail.com-alias-management.md
│   └── 前端所需后端API契约.md   # ← 前后端接口唯一约定来源
├── frontend/                  # Vue 3 SPA
├── backend/                   # FastAPI 服务
└── maildotcom-sdk/            # 参考用 TypeScript SDK
```

## 快速开始

### 1. 构建前端

```bash
cd frontend
npm install
npm run build          # 产出 dist/
```

### 2. 启动后端（会自动托管 frontend/dist）

```bash
cd ../backend
uv venv .venv --python 3.12 --clear
uv pip install --python .venv/Scripts/python.exe \
  "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "httpx>=0.28.0" \
  "sqlalchemy>=2.0.36" "pydantic-settings>=2.6.0" "cryptography>=44.0.0" \
  "python-jose[cryptography]>=3.3.0" "python-multipart>=0.0.20" "email-validator>=2.2.0"
cp .env.example .env
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问：

- 界面 http://127.0.0.1:8000/
- 接口文档 http://127.0.0.1:8000/docs
- 默认管理员 `admin` / `admin123`

### 开发模式（前端热更新）

```bash
# 终端 1：后端
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
# 终端 2：前端（Vite 将 /api 代理到 8000）
cd frontend && npm run dev     # http://localhost:5173
```

## 功能页面

| 页面 | 功能 |
| --- | --- |
| 登录 | 用户名/密码登录，保存 JWT，401 自动跳转 |
| 仪表盘 | 账号数、别名数、映射数、别名容量、最近取件 |
| 账号管理 | 增删账号、验证会话、别名用量进度（x/10） |
| 别名管理 | 按账号查看/创建/删除别名、设默认发件人、展示取件地址 |
| 映射列表 | `别名 ---- 取件地址`，支持复制、导出 CSV/文本 |
| 取件查看 | 选择/输入取件地址，拉取邮件列表、查看 HTML/纯文本正文 |

## 接口契约

完整的前后端接口定义见 [`docs/前端所需后端API契约.md`](docs/前端所需后端API契约.md)。

## 测试与检查

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m ruff check app tests
```

## 安全提示

生产环境请务必修改 `.env` 中的 `MAILCOM_SECRET_KEY` 与 `JWT_SECRET`，收紧数据库文件权限，并通过 `CORS_ORIGINS` 限定允许来源。
