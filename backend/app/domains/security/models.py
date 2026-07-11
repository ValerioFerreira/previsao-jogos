"""Registro de incidentes de anti-compartilhamento: tentativas de captura de tela,
cópia ou impressão detectadas nas análises geradas (cada análise é individual e
exclusiva da sessão do usuário). Usado para revisão manual pelo admin — sem
punição automática por ora (ver ADMIN painel de incidentes)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin


class ScreenshotIncident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_screenshot_incidents"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    incident_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    page: Mapped[str | None] = mapped_column(String(200), nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
