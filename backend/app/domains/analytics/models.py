"""Eventos de funil/conversão — instrumentação leve (insert simples), separada do
AdminAuditLog (que é só para ações administrativas)."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_events"

    event_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
