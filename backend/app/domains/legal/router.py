"""Rotas de documentos legais: leitura pública, aceite e pendências do usuário."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.domains.auth.deps import client_ip, get_current_user, get_db
from app.domains.legal import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/documents", response_model=list[schemas.LegalDocumentSummary])
def documents(db: Session = Depends(get_db)):
    service.seed_default_documents(db)
    return [schemas.LegalDocumentSummary(
        id=str(d.id), type=d.type.value, version=d.version, title=d.title, published_at=d.published_at,
    ) for d in service.list_current(db)]


@router.get("/documents/{doc_type}", response_model=schemas.LegalDocumentPublic)
def document(doc_type: str, db: Session = Depends(get_db)):
    service.seed_default_documents(db)
    d = service.get_current(db, doc_type)
    return schemas.LegalDocumentPublic(
        id=str(d.id), type=d.type.value, version=d.version, title=d.title,
        body_md=d.body_md, published_at=d.published_at,
    )


@router.get("/pending", response_model=list[schemas.LegalDocumentSummary])
def pending(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.seed_default_documents(db)
    return [schemas.LegalDocumentSummary(
        id=str(d.id), type=d.type.value, version=d.version, title=d.title,
        published_at=d.published_at, accepted=False,
    ) for d in service.pending_for_user(db, user.id)]


@router.post("/accept", response_model=schemas.AcceptResponse)
def accept(data: schemas.AcceptRequest, request: Request,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    newly = service.accept(db, user.id, data.document_ids, client_ip(request))
    return schemas.AcceptResponse(accepted=newly)
