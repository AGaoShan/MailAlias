"""取件路由。取件地址本身无需 JWT，便于对外复制使用。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    get_circuit_registry,
    get_current_user,
    get_pickup_cache,
    get_pickup_resolver,
    get_pickup_scheduler,
)
from ..mailcom import MailComError, PickupResolver
from ..mailcom.resilience import CircuitBreakerRegistry
from ..mailcom.scheduler import PickupCache, PickupScheduler
from ..models import User
from ..schemas import (
    BatchPickupRequest,
    PickupBodyOut,
    PickupResolveOut,
    PickupResolveRequest,
    PickupResponse,
    PickupResult,
)
from ..services.pickup_service import PickupService, _message_out
from ._errors import to_http_exception

router = APIRouter(tags=["取件"])


def build_service(
    db: Session,
    resolver: PickupResolver,
    scheduler: PickupScheduler,
    cache: PickupCache,
    circuits: CircuitBreakerRegistry,
) -> PickupService:
    return PickupService(db, resolver, scheduler, cache, circuits)


@router.get("/pickup/{account_key}/{address}", response_model=PickupResponse, summary="取件地址拉取邮件")
async def pickup(
    account_key: str,
    address: str,
    amount: int = Query(default=25, ge=1, le=100),
    mark_read: bool = Query(default=False),
    unread_only: bool = Query(default=False),
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    scheduler: PickupScheduler = Depends(get_pickup_scheduler),
    cache: PickupCache = Depends(get_pickup_cache),
    circuits: CircuitBreakerRegistry = Depends(get_circuit_registry),
) -> PickupResponse:
    pickup_url = resolver.build(account_key, address)
    service = build_service(db, resolver, scheduler, cache, circuits)
    try:
        messages, stale, fetched_at = await service.fetch(
            pickup_url,
            amount=amount,
            mark_read=mark_read,
            unread_only=unread_only,
            refresh=refresh,
        )
    except MailComError as exc:
        raise to_http_exception(exc) from exc
    return PickupResponse(
        pickup_url=pickup_url,
        alias=address,
        account_key=account_key,
        messages=[_message_out(message) for message in messages],
        total=len(messages),
        stale=stale,
        fetched_at=fetched_at,
    )


@router.get(
    "/pickup/{account_key}/{address}/messages/{message_id}/body",
    response_model=PickupBodyOut,
    summary="取件地址拉取邮件正文",
)
async def pickup_body(
    account_key: str,
    address: str,
    message_id: str,
    format: str = Query(default="html", pattern="^(html|text)$"),
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    scheduler: PickupScheduler = Depends(get_pickup_scheduler),
    cache: PickupCache = Depends(get_pickup_cache),
    circuits: CircuitBreakerRegistry = Depends(get_circuit_registry),
) -> PickupBodyOut:
    pickup_url = resolver.build(account_key, address)
    service = build_service(db, resolver, scheduler, cache, circuits)
    try:
        body = await service.get_body(pickup_url, message_id, format)
    except MailComError as exc:
        raise to_http_exception(exc) from exc
    return PickupBodyOut(id=message_id, format=format, body=body)


@router.post("/pickup/batch", response_model=list[PickupResult], summary="批量取件")
async def pickup_batch(
    payload: BatchPickupRequest,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    scheduler: PickupScheduler = Depends(get_pickup_scheduler),
    cache: PickupCache = Depends(get_pickup_cache),
    circuits: CircuitBreakerRegistry = Depends(get_circuit_registry),
    _user: User = Depends(get_current_user),
) -> list[PickupResult]:
    service = build_service(db, resolver, scheduler, cache, circuits)
    return await service.batch(payload.pickup_urls, amount=payload.amount)


@router.post("/pickup/resolve", response_model=PickupResolveOut, summary="由取件地址反查别名")
def pickup_resolve(
    payload: PickupResolveRequest,
    db: Session = Depends(get_db),
    resolver: PickupResolver = Depends(get_pickup_resolver),
    _user: User = Depends(get_current_user),
) -> PickupResolveOut:
    service = build_service(db, resolver, get_pickup_scheduler(), get_pickup_cache(), get_circuit_registry())
    try:
        account, alias = service.resolve(payload.pickup_url)
    except (MailComError, ValueError) as exc:
        message = exc.message if isinstance(exc, MailComError) else str(exc)
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message}) from exc
    return PickupResolveOut(
        account_key=account.account_key,
        alias=alias.address,
        account_id=account.id,
        account_email=account.email,
        alias_id=alias.id,
    )
