"""Suporte ao Painel Administrativo (próxima etapa) — já modelado desde já:
auditoria de ações administrativas, configurações da plataforma e banners/avisos."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin


class AdminAuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Toda ação administrativa registrada (before/after) para auditoria completa."""
    __tablename__ = "app_admin_audit_log"

    admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PlatformSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurações gerais editáveis pelo admin (gateway ativo, flags, delays, etc.)."""
    __tablename__ = "app_platform_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Banner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Banners e avisos exibidos na plataforma (gerenciados pelo admin)."""
    __tablename__ = "app_banners"

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    type: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
