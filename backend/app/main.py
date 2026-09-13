"""FastAPI 应用入口：路由挂载、CORS、静态托管、启动初始化、健康检查。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import settings
from .database import SessionLocal, init_db
from .models import Account, User
from .routers import (
    accounts_router,
    aliases_router,
    auth_router,
    dashboard_router,
    mappings_router,
    pickup_router,
)
from .security.passwords import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("mailcom")

API_PREFIX = "/api/v1"


def _ensure_default_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username=settings.default_admin_username,
                    password_hash=hash_password(settings.default_admin_password),
                    role="admin",
                )
            )
            db.commit()
            logger.info("已创建默认管理员账号：%s", settings.default_admin_username)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _ensure_default_admin()
    logger.info("数据库初始化完成：%s", settings.db_path)
    yield


app = FastAPI(
    title="MailAlias · 邮箱别名管理与取件",
    description="多账号 · 别名 · 取件地址统一管理",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- API 路由 ----------
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(accounts_router, prefix=API_PREFIX)
app.include_router(aliases_router, prefix=API_PREFIX)
app.include_router(mappings_router, prefix=API_PREFIX)
app.include_router(pickup_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", tags=["健康检查"], summary="健康检查")
def health() -> dict:
    database = "ok"
    accounts: list[dict] = []
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            accounts = [
                {"account_key": account.account_key, "session_state": account.session_state}
                for account in db.query(Account).all()
            ]
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("健康检查数据库异常：%s", exc)
        database = "error"
    return {"status": "ok" if database == "ok" else "degraded", "database": database, "accounts": accounts}


# ---------- 统一错误格式 ----------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """把参数校验错误规整为统一结构。"""
    errors = exc.errors()
    first = errors[0] if errors else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part not in ("body", "query", "path"))
    message = str(first.get("msg", "参数校验失败"))
    if location:
        message = f"{location}: {message}"
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "VALIDATION_ERROR", "message": message}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}},
    )


# ---------- 静态托管前端构建产物 ----------
_dist: Path = settings.frontend_dist_path
if _dist.is_dir():
    assets_dir = _dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(str(_dist / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": {"code": "NOT_FOUND", "message": "接口不存在"}})
        candidate = _dist / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_dist / "index.html"))
else:
    logger.warning("未找到前端构建产物目录：%s（可运行 frontend 的 npm run build 生成）", _dist)
