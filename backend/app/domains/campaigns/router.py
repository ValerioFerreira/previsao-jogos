"""Rota pública de campanhas ativas (consumida pelo banner/pacotes da Carteira)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.campaigns import service
from app.domains.users.models import User

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/active")
def active_campaigns(db: Session = Depends(get_db)):
    return {"items": service.list_active_campaigns(db)}


@router.get("/experiments/{experiment_key}/variant")
def experiment_variant(experiment_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A/B testing — variante determinística por usuário (mesmo usuário sempre cai na
    mesma variante). Retorna null se o experimento não existe/está inativo."""
    return {"variant": service.assign_variant(db, experiment_key, user.id)}
