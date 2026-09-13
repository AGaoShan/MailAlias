"""仪表盘统计路由。"""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Account, Alias, FetchLog, User
from ..schemas import AliasCapacity, DashboardStats, RecentFetch

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=DashboardStats, summary="仪表盘统计")
def stats(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> DashboardStats:
    account_count = db.query(Account).count()
    alias_count = db.query(Alias).count()
    recent_logs = db.query(FetchLog).order_by(FetchLog.fetched_at.desc()).limit(10).all()
    recent: list[RecentFetch] = []
    for log in recent_logs:
        fetched = log.fetched_at
        if fetched is not None and fetched.tzinfo is None:

            fetched = fetched.replace(tzinfo=UTC)
        recent.append(
            RecentFetch(
                pickup_url=log.pickup_url,
                alias=log.alias_address or "",
                message_count=log.message_count,
                fetched_at=fetched.strftime("%Y-%m-%dT%H:%M:%SZ") if fetched else "",
            )
        )

    return DashboardStats(
        account_count=account_count,
        alias_count=alias_count,
        mapping_count=alias_count,
        alias_capacity=AliasCapacity(
            used=alias_count,
            limit=account_count * settings.max_aliases_per_account,
        ),
        recent_fetches=recent,
    )
