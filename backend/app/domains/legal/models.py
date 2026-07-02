"""Documentos legais versionados (Termos, Privacidade, LGPD, Política de Créditos,
Regulamento da Promoção) e o registro de aceite por usuário (com data/hora e IP)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import LegalDocumentType


class LegalDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_legal_documents"
    __table_args__ = (UniqueConstraint("type", "version", name="uq_legal_doc_type_version"),)

    type: Mapped[LegalDocumentType] = mapped_column(enum_type(LegalDocumentType), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )


class UserDocumentAcceptance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_user_document_acceptances"
    __table_args__ = (UniqueConstraint("user_id", "document_id", name="uq_user_doc_acceptance"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_legal_documents.id", ondelete="RESTRICT"), index=True
    )
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
