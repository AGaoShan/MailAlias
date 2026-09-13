from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_enc: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    session_state: Mapped[str] = mapped_column(String(32), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    aliases: Mapped[list[Alias]] = relationship(back_populates="account", cascade="all, delete-orphan", lazy="selectin")
    session: Mapped[SessionToken | None] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (UniqueConstraint("account_id", "address", name="uq_alias_account_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    address: Mapped[str] = mapped_column(String(255), index=True)
    local_part: Mapped[str] = mapped_column(String(128))
    domain: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_default_sender: Mapped[bool] = mapped_column(Boolean, default=False)
    deletable: Mapped[bool] = mapped_column(Boolean, default=True)
    state: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped[Account] = relationship(back_populates="aliases")
    binding: Mapped[PickupBinding | None] = relationship(
        back_populates="alias", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class PickupBinding(Base):
    __tablename__ = "pickup_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias_id: Mapped[int] = mapped_column(ForeignKey("aliases.id", ondelete="CASCADE"), unique=True)
    pickup_url: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    alias: Mapped[Alias] = relationship(back_populates="binding")


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)

    # 别名（CATS settings）会话
    settings_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings_cookies: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 取件（HSP2 移动 API）会话
    mobile_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    mobile_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 兼容旧字段（保留但不再作为主存储）
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_type: Mapped[str] = mapped_column(String(32), default="bearer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cookies: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    account: Mapped[Account] = relationship(back_populates="session")


class FetchLog(Base):
    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pickup_url: Mapped[str] = mapped_column(Text, index=True)
    alias_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
