"""Rotas de Análise: gerar (consome/reserva crédito), listar histórico e ver snapshot."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domains.analysis import schemas, service
from app.domains.auth.deps import get_current_user, get_db
from app.domains.users.models import User

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=schemas.AnalysisResponse, status_code=201)
def create_analysis(data: schemas.AnalysisRequest, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return service.create_analysis(db, user, data)


@router.get("", response_model=schemas.AnalysisPage)
def list_analyses(user: User = Depends(get_current_user), db: Session = Depends(get_db),
                  limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return service.list_analyses(db, user, limit, offset)


@router.get("/{analysis_id}", response_model=schemas.AnalysisResponse)
def get_analysis(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = service.get_analysis(db, user, analysis_id)
    from decimal import Decimal
    from app.domains.wallet.service import get_or_create_wallet
    wallet = get_or_create_wallet(db, user.id)
    db.commit()
    return schemas.AnalysisResponse(
        id=str(a.id), type=a.type.value, status=a.status.value, home_team=a.home_team,
        away_team=a.away_team, tournament=a.tournament, fixture_id=a.fixture_id,
        algo_version=a.algo_version, data_version=a.data_version, model_hash=a.model_hash,
        created_at=a.created_at, credits_consumed=0, credits_reserved=0,
        available_balance=wallet.available_balance, snapshot=a.snapshot,
    )
