"""认证路由：登录、当前用户、登出。"""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserOut
from ..security.jwt import create_access_token
from ..security.passwords import verify_password

router = APIRouter(prefix="/auth", tags=["认证"])


def _user_out(user: User) -> UserOut:
    created = user.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        created_at=created.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if created else None,
    )


@router.post("/login", response_model=LoginResponse, summary="登录")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "用户名或密码错误"},
        )
    token = create_access_token(user.username, role=user.role)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        user=_user_out(user),
    )


@router.get("/me", response_model=UserOut, summary="当前用户")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="登出")
def logout() -> None:
    return None
