"""Documentos legais versionados + registro de aceite (data/hora + IP).

Cada tipo de documento tem uma versão vigente (is_current). Quando um documento é
republicado, cria-se uma NOVA versão vigente e a anterior deixa de ser vigente — o
sistema passa a exigir NOVO aceite (pending_for_user detecta quem ainda não aceitou a
versão vigente).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.enums import LegalDocumentType
from app.domains.legal import schemas
from app.domains.legal.models import LegalDocument, UserDocumentAcceptance

# Conteúdo inicial (v1) — TEMPLATE. Deve ser revisado pelo jurídico antes de produção.
_DEFAULTS: dict[LegalDocumentType, tuple[str, str]] = {
    LegalDocumentType.terms: (
        "Termos de Uso",
        "# Termos de Uso\n\nBem-vindo à ApostAI. Ao usar a plataforma você concorda com estes "
        "termos. A plataforma oferece **análises probabilísticas por Inteligência Artificial**. "
        "Os créditos remuneram exclusivamente o uso da IA. Nenhuma previsão garante resultado.\n\n"
        "_(Template inicial — substituir pelo texto jurídico definitivo.)_",
    ),
    LegalDocumentType.privacy: (
        "Política de Privacidade",
        "# Política de Privacidade\n\nDescreve como coletamos, usamos e protegemos seus dados "
        "pessoais (nome, e-mail, CPF, telefone). Você pode solicitar acesso, correção e exclusão.\n\n"
        "_(Template inicial — substituir pelo texto jurídico definitivo.)_",
    ),
    LegalDocumentType.lgpd: (
        "Consentimento LGPD",
        "# Consentimento LGPD\n\nNos termos da Lei nº 13.709/2018 (LGPD), você consente com o "
        "tratamento dos seus dados pessoais para as finalidades descritas na Política de Privacidade.\n\n"
        "_(Template inicial — substituir pelo texto jurídico definitivo.)_",
    ),
    LegalDocumentType.credits_policy: (
        "Política de Créditos",
        "# Política de Créditos\n\nCada crédito custa R$ 1,00 e remunera o uso da Inteligência "
        "Artificial. Créditos podem ser reservados e consumidos ou estornados conforme as regras "
        "de cada análise/promoção.\n\n_(Template inicial — substituir pelo texto jurídico definitivo.)_",
    ),
    LegalDocumentType.promo_regulation: (
        "Regulamento da Promoção 'Só Paga se Acertar'",
        "# Regulamento — 'Só Paga se Acertar'\n\nEm análises de partidas futuras, o crédito é "
        "**reservado**. Após o término oficial da partida, se a aposta escolhida for vencedora o "
        "crédito é consumido; caso contrário, é **estornado** integralmente para a carteira. "
        "A odd combinada é limitada a 2,00. Trata-se de campanha comercial de estorno de créditos, "
        "não de aposta.\n\n_(Template inicial — substituir pelo texto jurídico definitivo.)_",
    ),
}


def seed_default_documents(db: Session) -> None:
    if db.execute(select(LegalDocument.id).limit(1)).first() is not None:
        return
    now = datetime.now(timezone.utc)
    for dtype, (title, body) in _DEFAULTS.items():
        db.add(LegalDocument(type=dtype, version=1, title=title, body_md=body,
                             published_at=now, is_current=True))
    db.commit()


def list_current(db: Session) -> list[LegalDocument]:
    return db.execute(
        select(LegalDocument).where(LegalDocument.is_current.is_(True)).order_by(LegalDocument.type)
    ).scalars().all()


def get_current(db: Session, dtype: str) -> LegalDocument:
    try:
        t = LegalDocumentType(dtype)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tipo de documento inválido.")
    doc = db.execute(
        select(LegalDocument).where(LegalDocument.type == t, LegalDocument.is_current.is_(True))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")
    return doc


def accepted_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.execute(
        select(UserDocumentAcceptance.document_id).where(UserDocumentAcceptance.user_id == user_id)
    ).scalars().all())


def pending_for_user(db: Session, user_id: uuid.UUID) -> list[LegalDocument]:
    """Documentos vigentes que o usuário ainda NÃO aceitou (na versão vigente)."""
    accepted = accepted_ids(db, user_id)
    return [d for d in list_current(db) if d.id not in accepted]


def accept(db: Session, user_id: uuid.UUID, document_ids: list[str], ip: str | None) -> list[str]:
    current = {d.id: d for d in list_current(db)}
    if document_ids:
        targets = []
        for did in document_ids:
            try:
                u = uuid.UUID(did)
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ID de documento inválido.")
            if u not in current:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Documento não é a versão vigente.")
            targets.append(u)
    else:
        targets = list(current.keys())  # aceita todos os vigentes

    already = accepted_ids(db, user_id)
    now = datetime.now(timezone.utc)
    newly = []
    for did in targets:
        if did in already:
            continue  # idempotente
        db.add(UserDocumentAcceptance(user_id=user_id, document_id=did, accepted_at=now, ip=ip))
        newly.append(str(did))
    db.commit()
    return newly


def publish(db: Session, dtype: str, title: str, body_md: str, admin_id: uuid.UUID | None) -> LegalDocument:
    """Publica NOVA versão vigente de um tipo (uso administrativo). Exige novo aceite."""
    try:
        t = LegalDocumentType(dtype)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de documento inválido.")
    prev = db.execute(
        select(LegalDocument).where(LegalDocument.type == t, LegalDocument.is_current.is_(True))
    ).scalar_one_or_none()
    next_version = (prev.version + 1) if prev else 1
    if prev is not None:
        prev.is_current = False
    doc = LegalDocument(type=t, version=next_version, title=title, body_md=body_md,
                        published_at=datetime.now(timezone.utc), is_current=True, created_by=admin_id)
    db.add(doc)
    db.commit()
    return doc
