"""Rotas da 'Aposta Escolhida': mercados disponíveis, prévia em tempo real, criação
(imutável) e histórico. Se o corpo vier sem seleções, o sistema auto-seleciona (odd ~2,00)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.bets import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/bets", tags=["bets"])


@router.get("/markets/{analysis_id}", response_model=schemas.MarketsResponse)
def markets_for_analysis(analysis_id: str, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    return service.get_markets(db, user, analysis_id)


@router.post("/preview/{analysis_id}", response_model=schemas.PreviewResponse)
def preview(analysis_id: str, data: schemas.PreviewRequest,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cálculo em tempo real da odd combinada (sem persistir). Seleções vazias = auto-seleção."""
    return service.preview(db, user, analysis_id, data.market_keys)


@router.post("/{analysis_id}", response_model=schemas.BetResponse, status_code=201)
def create_bet(analysis_id: str, data: schemas.CreateBetRequest,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Confirma a aposta (IMUTÁVEL). Sem seleções -> o sistema escolhe uma odd ~2,00."""
    return service.create_bet(db, user, analysis_id, data.market_keys)


@router.get("", response_model=schemas.BetsPage)
def list_bets(user: User = Depends(get_current_user), db: Session = Depends(get_db),
              limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return service.list_bets(db, user, limit, offset)


@router.get("/{bet_id}", response_model=schemas.BetResponse)
def get_bet(bet_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.get_bet(db, user, bet_id)
