"""别名路由（跨账号操作）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_pickup_resolver, get_write_limiter
from ..mailcom import MailComError, PickupResolver
from ..mailcom.resilience import WriteRateLimiter
from ..models import User
from ..schemas import (
    AliasAutoCreate,
    AliasBatchGenerate,
    AliasBatchItem,
    AliasBatchResult,
    AliasOut,
    DefaultSenderUpdate,
    DisplayNameUpdate,
)
from ..services.alias_service import AliasService
from ._errors import to_http_exception

router = APIRouter(prefix="/aliases", tags=["别名"])


@router.post(
    "",
    response_model=AliasOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建别名（自动选号）",
)
async def create_alias_auto(
    payload: AliasAutoCreate,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> AliasOut:
    """只传别名（可含 @域名），自动挑选仍有别名额度的账号创建。

    - `address`：`my-alias@mail.com`（或仅 `my-alias`，默认 mail.com 后缀）
    - `account_id`：可选，指定账号；不填则自动选择
    """
    try:
        return await AliasService(db, resolver, write_limiter).create_auto(payload.address, payload.account_id)
    except MailComError as exc:
        raise to_http_exception(exc) from exc


@router.post(
    "/batch-generate",
    response_model=AliasBatchResult,
    status_code=status.HTTP_201_CREATED,
    summary="随机生成并批量创建别名",
)
async def batch_generate_aliases(
    payload: AliasBatchGenerate,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> AliasBatchResult:
    """指定数量与后缀，随机生成别名并批量创建（能建多少建多少）。"""
    service = AliasService(db, resolver, write_limiter)
    try:
        raw = await service.batch_generate(
            payload.count,
            domain=payload.domain,
            account_id=payload.account_id,
            prefix=payload.prefix,
            length=payload.length,
        )
    except MailComError as exc:
        raise to_http_exception(exc) from exc

    items: list[AliasBatchItem] = []
    for address, alias, error in raw:
        if alias is not None:
            items.append(AliasBatchItem(address=address, ok=True, alias=alias))
        else:
            code = error.code if error else "UNKNOWN"
            message = error.message if error else "创建失败"
            items.append(AliasBatchItem(address=address, ok=False, error={"code": code, "message": message}))
    created = sum(1 for item in items if item.ok)
    return AliasBatchResult(
        requested=payload.count,
        created=created,
        failed=len(items) - created,
        items=items,
    )


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
