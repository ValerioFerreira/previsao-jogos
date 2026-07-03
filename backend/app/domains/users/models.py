"""Identidade e segurança: usuários, OTP, sessões de refresh e auditoria de auth."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import AuthEventType, OtpPurpose, UserRole, UserStatus


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_users"

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus), default=UserStatus.pending_verification, nullable=False
    )
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole), default=UserRole.user, nullable=False)

    # rastreabilidade (exigida no spec)
    signup_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # anti-brute-force
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    otp_codes: Mapped[list["OtpCode"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OtpCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_otp_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[OtpPurpose] = mapped_column(enum_type(OtpPurpose), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship(back_populates="otp_codes")


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Refresh token (armazenado só como hash) — permite revogar sessões individualmente."""
    __tablename__ = "app_auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class AuthEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Log de autenticação (imutável) — auditoria e detecção de abuso."""
    __tablename__ = "app_auth_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    event: Mapped[AuthEventType] = mapped_column(enum_type(AuthEventType), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
