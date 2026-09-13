"""依赖注入：数据库会话、当前登录用户、应用级单例服务。"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .mailcom.resilience import CircuitBreakerRegistry, WriteRateLimiter
from .mailcom.resolver import PickupResolver
from .mailcom.scheduler import PickupCache, PickupScheduler
from .models import User
from .security.jwt import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

_pickup_resolver = PickupResolver(settings.pickup_api_base)
_pickup_scheduler = PickupScheduler(
    global_limit=settings.pickup_global_concurrency,
    per_account_limit=settings.pickup_concurrency_per_account,
    global_qps=settings.rate_limit_global_qps,
    account_qps=settings.rate_limit_per_account_qps,
)
_pickup_cache = PickupCache(ttl=settings.pickup_cache_ttl)
_circuit_registry = CircuitBreakerRegistry(
    fail_threshold=settings.circuit_fail_threshold,
    cooldown=settings.circuit_cooldown,
)
_write_limiter = WriteRateLimiter(min_interval=settings.write_min_interval)


def get_pickup_resolver() -> PickupResolver:
    return _pickup_resolver


def get_pickup_scheduler() -> PickupScheduler:
    return _pickup_scheduler


def get_pickup_cache() -> PickupCache:
    return _pickup_cache


def get_circuit_registry() -> CircuitBreakerRegistry:
    return _circuit_registry


def get_write_limiter() -> WriteRateLimiter:
    return _write_limiter


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "未登录或凭据缺失"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": f"登录状态无效：{exc}"},
        ) from exc

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "用户不存在"},
        )
    return user


DbSession = Iterator[Session]
