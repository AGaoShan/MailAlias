"""自动选号创建别名的账号选择逻辑测试（不触达真实 mail.com）。"""

from __future__ import annotations

import pytest

from app.config import settings
from app.mailcom.errors import MailComAliasLimitError, MailComDomainUnavailableError, MailComError
from app.mailcom.resilience import WriteRateLimiter
from app.mailcom.resolver import PickupResolver
from app.models import Account, Alias, Base
from app.services.alias_service import AliasService


@pytest.fixture()
def db():
    import tempfile
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    tmp = Path(tempfile.mkdtemp()) / "t.db"
    engine = create_engine(f"sqlite:///{tmp}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _service(db) -> AliasService:
    return AliasService(db, PickupResolver("http://host"), WriteRateLimiter(0))


def _add_account(db, email: str, enabled: bool = True) -> Account:
    account = Account(
        account_key=f"acc_{email.split('@')[0]}",
        email=email,
        password_enc="x",
        enabled=enabled,
        session_state="active",
    )
    db.add(account)
    db.commit()
    return account


def _add_aliases(db, account: Account, count: int) -> None:
    for index in range(count):
        db.add(
            Alias(
                account_id=account.id,
                address=f"a{index}@{account.email}",
                local_part=f"a{index}",
                domain="mail.com",
            )
        )
    db.commit()


def test_no_accounts_raises(db) -> None:
    with pytest.raises(MailComError, match="没有可用的账号"):
        _service(db)._select_account_for_alias(None)


def test_picks_account_with_most_remaining_capacity(db) -> None:
    first = _add_account(db, "first@mail.com")
    second = _add_account(db, "second@mail.com")
    _add_aliases(db, first, 8)  # 剩余 2
    _add_aliases(db, second, 1)  # 剩余 9

    chosen = _service(db)._select_account_for_alias(None)
    assert chosen.id == second.id


def test_skips_disabled_accounts(db) -> None:
    disabled = _add_account(db, "off@mail.com", enabled=False)
    enabled = _add_account(db, "on@mail.com")

    chosen = _service(db)._select_account_for_alias(None)
    assert chosen.id == enabled.id
    assert chosen.id != disabled.id


def test_skips_full_accounts(db) -> None:
    full = _add_account(db, "full@mail.com")
    _add_aliases(db, full, settings.max_aliases_per_account)
    available = _add_account(db, "avail@mail.com")

    chosen = _service(db)._select_account_for_alias(None)
    assert chosen.id == available.id


def test_all_full_raises(db) -> None:
    account = _add_account(db, "full@mail.com")
    _add_aliases(db, account, settings.max_aliases_per_account)

    with pytest.raises(MailComAliasLimitError):
        _service(db)._select_account_for_alias(None)


def test_explicit_account_full_raises(db) -> None:
    account = _add_account(db, "full@mail.com")
    _add_aliases(db, account, settings.max_aliases_per_account)

    with pytest.raises(MailComAliasLimitError):
        _service(db)._select_account_for_alias(account.id)


def test_explicit_missing_account_raises(db) -> None:
    with pytest.raises(MailComError, match="账号不存在"):
        _service(db)._select_account_for_alias(999)


def test_invalid_domain_rejected() -> None:
    with pytest.raises(MailComDomainUnavailableError):
        from app.mailcom import split_alias_address

        split_alias_address("foo@bad-domain.com")
