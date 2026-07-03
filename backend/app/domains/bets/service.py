"""Regras da 'Aposta Escolhida'.

A partir de uma análise de PARTIDA FUTURA (crédito reservado), o usuário combina mercados
da própria análise. A odd combinada NUNCA pode passar de 2,00 (settings.max_combined_odd).
Se o usuário não escolher, o sistema AUTO-SELECIONA uma aposta com odd próxima de 2,00.
Após confirmada, a aposta é IMUTÁVEL (sem edição/exclusão) e entra na máquina de estados.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.analysis.models import Analysis
from app.domains.bets import markets, schemas
from app.domains.bets.models import Bet, BetSelection
from app.domains.enums import AnalysisType, BetStatus
from app.domains.users.models import User

CAP = float(settings.max_combined_odd)


def _load_reserved_analysis(db: Session, user: User, analysis_id: str) -> Analysis:
    try:
        aid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Análise não encontrada.")
    a = db.get(Analysis, aid)
    if a is None or a.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Análise não encontrada.")
    if a.type != AnalysisType.future_match:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Apostas só em análises de partida futura.")
    return a


def _candidates(a: Analysis) -> dict:
    return markets.extract_candidates(a.snapshot, a.home_team, a.away_team)


def get_markets(db: Session, user: User, analysis_id: str) -> schemas.MarketsResponse:
    a = _load_reserved_analysis(db, user, analysis_id)
    cands = _candidates(a)
    opts = [schemas.MarketOption(**c) for c in sorted(cands.values(), key=lambda c: c["market_key"])]
    return schemas.MarketsResponse(analysis_id=str(a.id), home_team=a.home_team,
                                   away_team=a.away_team, max_combined_odd=CAP, options=opts)


def _selection_outs(sels: list[dict]) -> list[schemas.SelectionOut]:
    return [schemas.SelectionOut(market_key=s["market_key"], label=s["label"],
                                 selection=s["selection"], odd=s["odd"]) for s in sels]


def preview(db: Session, user: User, analysis_id: str, market_keys: list[str]) -> schemas.PreviewResponse:
    a = _load_reserved_analysis(db, user, analysis_id)
    cands = _candidates(a)
    auto = not market_keys
    sels = markets.auto_select(cands, CAP) if auto else markets.resolve_selections(cands, market_keys)
    codd = markets.combined_odd(sels)
    exceeds = codd > CAP + 1e-9
    return schemas.PreviewResponse(
        selections=_selection_outs(sels), combined_odd=codd, valid=(not exceeds and len(sels) > 0),
        exceeds_cap=exceeds, auto=auto, max_combined_odd=CAP,
    )


def create_bet(db: Session, user: User, analysis_id: str, market_keys: list[str]) -> schemas.BetResponse:
    a = _load_reserved_analysis(db, user, analysis_id)
    # uma aposta por análise
    existing = db.execute(select(Bet).where(Bet.analysis_id == a.id)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esta análise já possui uma aposta.")

    cands = _candidates(a)
    auto = not market_keys
    sels = markets.auto_select(cands, CAP) if auto else markets.resolve_selections(cands, market_keys)
    if not sels:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nenhum mercado disponível para apostar.")
    codd = markets.combined_odd(sels)
    if codd > CAP + 1e-9:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"A odd combinada ({codd:.2f}) ultrapassa o limite de {CAP:.2f}. Remova alguma seleção.",
        )

    bet = Bet(
        user_id=user.id, analysis_id=a.id, fixture_id=a.fixture_id,
        combined_odd=Decimal(str(codd)), status=BetStatus.awaiting_start,
        reserved_tx_id=a.credit_tx_id,   # a reserva feita ao gerar a análise
    )
    db.add(bet)
    db.flush()
    for s in sels:
        db.add(BetSelection(
            bet_id=bet.id, market_key=s["market_key"], market_label=s["label"],
            selection=s["selection"], odd=Decimal(str(s["odd"])), snapshot_ref=s,
        ))
    db.commit()

    return schemas.BetResponse(
        id=str(bet.id), analysis_id=str(a.id), status=bet.status.value, combined_odd=bet.combined_odd,
        auto_selected=auto, fixture_id=bet.fixture_id, match_datetime=bet.match_datetime,
        created_at=bet.created_at, selections=_selection_outs(sels),
    )


def _to_response(db: Session, bet: Bet) -> schemas.BetResponse:
    sels = db.execute(select(BetSelection).where(BetSelection.bet_id == bet.id)).scalars().all()
    return schemas.BetResponse(
        id=str(bet.id), analysis_id=str(bet.analysis_id), status=bet.status.value,
        combined_odd=bet.combined_odd, auto_selected=False, fixture_id=bet.fixture_id,
        match_datetime=bet.match_datetime, created_at=bet.created_at,
        selections=[schemas.SelectionOut(market_key=s.market_key, label=s.market_label or s.market_key,
                                         selection=s.selection, odd=float(s.odd)) for s in sels],
    )


def list_bets(db: Session, user: User, limit: int, offset: int) -> schemas.BetsPage:
    total = db.execute(select(func.count(Bet.id)).where(Bet.user_id == user.id)).scalar_one()
    rows = db.execute(select(Bet).where(Bet.user_id == user.id)
                      .order_by(Bet.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return schemas.BetsPage(items=[_to_response(db, b) for b in rows], total=total, limit=limit, offset=offset)


def get_bet(db: Session, user: User, bet_id: str) -> schemas.BetResponse:
    try:
        bid = uuid.UUID(bet_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aposta não encontrada.")
    b = db.get(Bet, bid)
    if b is None or b.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aposta não encontrada.")
    return _to_response(db, b)
