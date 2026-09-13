"""映射路由：别名 <-> 取件地址 列表与导出。"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Alias, User
from ..schemas import MappingItem, MappingListResponse

router = APIRouter(prefix="/mappings", tags=["映射"])


def _collect(db: Session, account_id: int | None) -> list[MappingItem]:
    query = db.query(Alias).order_by(Alias.id.asc())
    if account_id is not None:
        query = query.filter(Alias.account_id == account_id)
    items: list[MappingItem] = []
    for alias in query.all():
        binding = alias.binding
        if binding is None:
            continue
        last_fetched = binding.last_fetched_at
        if last_fetched is not None and last_fetched.tzinfo is None:
            last_fetched = last_fetched.replace(tzinfo=__import__("datetime").timezone.utc)
        items.append(
            MappingItem(
                alias_id=alias.id,
                account_id=alias.account_id,
                account_email=alias.account.email if alias.account else "",
                alias_address=alias.address,
                pickup_url=binding.pickup_url,
                is_default_sender=alias.is_default_sender,
                last_fetched_at=last_fetched.strftime("%Y-%m-%dT%H:%M:%SZ") if last_fetched else None,
            )
        )
    return items


@router.get("", response_model=MappingListResponse, summary="全部别名-取件地址映射")
def list_mappings(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MappingListResponse:
    items = _collect(db, account_id)
    return MappingListResponse(total=len(items), items=items)


@router.get("/export", summary="导出映射（text/csv）")
def export_mappings(
    format: str = Query(default="text", pattern="^(text|csv)$"),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    items = _collect(db, account_id)
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["alias_address", "pickup_url", "account_email"])
        for item in items:
            writer.writerow([item.alias_address, item.pickup_url, item.account_email])
        return Response(
            content="\ufeff" + buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="mailcom_mappings.csv"'},
        )
    text = "\n".join(f"{item.alias_address}----{item.pickup_url}" for item in items)
    return PlainTextResponse(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mailcom_mappings.txt"'},
    )
