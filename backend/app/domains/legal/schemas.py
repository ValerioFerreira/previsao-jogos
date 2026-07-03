"""Schemas de documentos legais e aceite (LGPD, Termos, etc.)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LegalDocumentPublic(BaseModel):
    id: str
    type: str
    version: int
    title: str
    body_md: str
    published_at: datetime | None


class LegalDocumentSummary(BaseModel):
    id: str
    type: str
    version: int
    title: str
    published_at: datetime | None
    accepted: bool = False


class AcceptRequest(BaseModel):
    # aceita documentos específicos; se vazio, aceita TODOS os vigentes
    document_ids: list[str] = Field(default_factory=list)


class AcceptResponse(BaseModel):
    accepted: list[str]
    message: str = "Aceite registrado."


class PublishDocumentRequest(BaseModel):
    type: str
    title: str
    body_md: str
