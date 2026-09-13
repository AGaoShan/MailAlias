"""别名路由（跨账号操作）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_pickup_resolver, get_write_limiter
from ..mailcom import MailComError, PickupResolver
from ..mailcom.resilience import WriteRateLimiter
from ..models import User
from ..schemas import AliasOut, DefaultSenderUpdate, DisplayNameUpdate
from ..services.alias_service import AliasService
from ._errors import to_http_exception

router = APIRouter(prefix="/aliases", tags=["别名"])


@router.delete("/{alias_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除别名及映射")
async def delete_alias(
    alias_id: int,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        await AliasService(db, resolver, write_limiter).delete(alias_id)
    except MailComError as exc:
        raise to_http_exception(exc) from exc


@router.put("/{alias_id}/default-sender", response_model=AliasOut, summary="设置默认发件人")
async def set_default_sender(
    alias_id: int,
    payload: DefaultSenderUpdate,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> AliasOut:
    try:
        return await AliasService(db, resolver, write_limiter).set_default_sender(alias_id, payload.sender)
    except MailComError as exc:
        raise to_http_exception(exc) from exc


@router.put("/{alias_id}/display-name", response_model=AliasOut, summary="设置别名显示名")
async def set_display_name(
    alias_id: int,
    payload: DisplayNameUpdate,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> AliasOut:
    try:
        return await AliasService(db, resolver, write_limiter).set_display_name(alias_id, payload.display_name)
    except MailComError as exc:
        raise to_http_exception(exc) from exc
