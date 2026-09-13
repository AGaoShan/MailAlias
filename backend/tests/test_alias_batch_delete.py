"""别名批量删除的容错逻辑测试（不触达真实 mail.com）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.mailcom.resilience import WriteRateLimiter
from app.mailcom.resolver import PickupResolver
from app.models import Account, Alias, Base
from app.services.alias_service import AliasService


@pytest.fixture()
def db():
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    engine = create_engine(f"sqlite:///{tmp}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _service(db) -> AliasService:
    return AliasService(db, PickupResolver("http://host"), WriteRateLimiter(0))


def _seed(db) -> tuple[Account, list[Alias]]:
    account = Account(account_key="acc_x", email="a@mail.com", password_enc="x", enabled=True)
    db.add(account)
    db.commit()
    aliases = []
    for index in range(3):
        alias = Alias(
            account_id=account.id,
            address=f"a{index}@mail.com",
            local_part=f"a{index}",
            domain="mail.com",
            deletable=index != 2,  # 最后一个不可删除
        )
        db.add(alias)
        aliases.append(alias)
    db.commit()
    return account, aliases


def test_missing_ids_are_reported_not_dropped(db) -> None:
    _seed(db)
    results = __import__("asyncio").run(_service(db).delete_many([999, 998]))
    assert len(results) == 2
    assert all(error is not None for _id, _addr, error in results)
    assert {error.code for _id, _addr, error in results} == {"NOT_FOUND"}


def test_non_deletable_alias_reported(db) -> None:
    _account, aliases = _seed(db)
    non_deletable = aliases[2]
    results = __import__("asyncio").run(_service(db).delete_many([non_deletable.id]))
    assert len(results) == 1
    _id, _addr, error = results[0]
    assert error is not None
    assert error.code == "ALIAS_NOT_DELETABLE"


def test_results_preserve_input_order(db) -> None:
    _seed(db)
    ids = [999, 998, 997]
    results = __import__("asyncio").run(_service(db).delete_many(ids))
    assert [item[0] for item in results] == ids


def test_duplicate_ids_are_deduplicated(db) -> None:
    _seed(db)
    results = __import__("asyncio").run(_service(db).delete_many([999, 999]))
    assert len(results) == 1


def test_empty_input_returns_empty(db) -> None:
    _seed(db)
    assert __import__("asyncio").run(_service(db).delete_many([])) == []
