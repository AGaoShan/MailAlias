"""账号路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_pickup_resolver, get_write_limiter
from ..mailcom import MailComError, PickupResolver
from ..mailcom.resilience import WriteRateLimiter
from ..models import User
from ..schemas import (
    AccountCreate,
    AccountExportItem,
    AccountExportOut,
    AccountOut,
    AccountVerifyOut,
    AliasCreate,
    AliasOut,
    DomainsOut,
)
from ..services.account_service import AccountService
from ..services.alias_service import AliasService
from ._errors import to_http_exception

router = APIRouter(prefix="/accounts", tags=["账号"])


@router.get("", response_model=list[AccountOut], summary="账号列表")
def list_accounts(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[AccountOut]:
    return AccountService(db).list()


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED, summary="添加账号")
async def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AccountOut:
    try:
        return await AccountService(db).add(str(payload.email), payload.password)
    except MailComError as exc:
        raise to_http_exception(exc) from exc


@router.get("/export", response_model=AccountExportOut, summary="导出全部账号凭据")
def export_accounts(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AccountExportOut:
    """导出 `邮箱----密码`，格式与批量导入一致，可再次导入。"""
    items = AccountService(db).export_credentials()
    return AccountExportOut(
        total=len(items),
        items=[AccountExportItem(**item) for item in items],
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除账号")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    AccountService(db).delete(account_id)


@router.post("/{account_id}/verify", response_model=AccountVerifyOut, summary="验证账号会话")
async def verify_account(
    account_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AccountVerifyOut:
    try:
        account = await AccountService(db).verify(account_id)
    except MailComError as exc:
        raise to_http_exception(exc) from exc
    return AccountVerifyOut(
        account_id=account.id,
        session_state=account.session_state,
        session_state_text=account.session_state_text,
        ok=True,
    )


def _alias_service(
    db: Session,
    resolver: PickupResolver,
    write_limiter: WriteRateLimiter,
) -> AliasService:
    return AliasService(db, resolver, write_limiter)


@router.get("/{account_id}/aliases", response_model=list[AliasOut], summary="别名列表")
def list_aliases(
    account_id: int,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> list[AliasOut]:
    return _alias_service(db, resolver, write_limiter).list_by_account(account_id)


@router.post(
    "/{account_id}/aliases",
    response_model=AliasOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建别名并绑定取件地址",
)
async def create_alias(
    account_id: int,
    payload: AliasCreate,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> AliasOut:
    try:
        return await _alias_service(db, resolver, write_limiter).create(account_id, payload.address)
    except MailComError as exc:
        raise to_http_exception(exc) from exc


@router.get("/{account_id}/domains", response_model=DomainsOut, summary="可用域名（带本地缓存）")
async def list_domains(
    account_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    write_limiter: WriteRateLimiter = Depends(get_write_limiter),
    _user: User = Depends(get_current_user),
) -> DomainsOut:
    """返回账号可用域名；默认读取本地缓存，refresh=true 时强制回源。"""
    try:
        domains = await _alias_service(db, resolver, write_limiter).domains(account_id, refresh=refresh)
    except MailComError as exc:
        raise to_http_exception(exc) from exc
    return DomainsOut(account_id=account_id, domains=domains)
