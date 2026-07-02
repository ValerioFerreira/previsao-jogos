"""Geração de análise com SNAPSHOT IMUTÁVEL + versionamento e integração com créditos.

- Análise INDEPENDENTE: consome 1 crédito imediatamente; sem promoção/aposta.
- Análise de PARTIDA FUTURA: reserva 1 crédito; habilita a "Aposta Escolhida" (Fase 6).

O snapshot é a resposta completa da previsão (a mesma que a UI mostra), congelada — nunca
muda, mesmo que o algoritmo evolua depois.
"""
from __future__ import annotations

import functools
import hashlib
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.analysis import schemas
from app.domains.analysis.models import Analysis
from app.domains.enums import AnalysisStatus, AnalysisType, CreditTxType
from app.domains.users.models import User
from app.domains.wallet.service import get_or_create_wallet, post_transaction

ANALYSIS_ALGO_VERSION = "1.0.0"   # pipeline DC-NB + cascata NB/GP + calibração O/U


@functools.lru_cache(maxsize=1)
def _model_fingerprint() -> tuple[str, str]:
    """(data_version, model_hash) a partir dos artefatos de modelo — determinístico,
    muda quando os modelos mudam. Congela a versão dos dados/modelo na análise."""
    root = Path(__file__).resolve().parents[3]
    art = root / "model_artifacts"
    if not art.exists():
        art = root / "api" / "model_artifacts"
    parts = []
    if art.exists():
        for p in sorted(art.glob("*.joblib")):
            try:
                parts.append(f"{p.name}:{p.stat().st_size}")
            except OSError:
                parts.append(p.name)
    blob = "|".join(parts)
    h = hashlib.sha256(blob.encode()).hexdigest()[:16] if blob else None
    data_version = f"artifacts:{len(parts)}" if parts else None
    return data_version, h


def _generate_snapshot(req: schemas.AnalysisRequest) -> dict:
    """Chama o mesmo pipeline do endpoint /predict (previsão + odds)."""
    from app.schemas import PredictRequest
    from app.services.predictor_service import get_predictor, predict_match

    predictor = get_predictor()
    home = predictor.norm_team(req.home_team)
    away = predictor.norm_team(req.away_team)
    if home == away:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Escolha duas seleções diferentes.")
    if home not in predictor.teams() or away not in predictor.teams():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Seleção não encontrada.")
    if req.tournament not in predictor.meta["tournament_weights"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Competição inválida.")
    payload = PredictRequest(home_team=home, away_team=away, neutral=req.neutral, tournament=req.tournament)
    return predict_match(payload), home, away


def create_analysis(db: Session, user: User, req: schemas.AnalysisRequest) -> schemas.AnalysisResponse:
    if req.type == "future_match" and not req.fixture_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="fixture_id é obrigatório para análise de partida futura.")

    wallet = get_or_create_wallet(db, user.id)
    if Decimal(wallet.available_balance) < 1:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Créditos insuficientes. Compre créditos para gerar a análise.")

    snapshot, home, away = _generate_snapshot(req)
    data_version, model_hash = _model_fingerprint()
    atype = AnalysisType(req.type)

    analysis = Analysis(
        user_id=user.id, type=atype,
        status=AnalysisStatus.consumed if atype == AnalysisType.independent else AnalysisStatus.reserved,
        home_team=home, away_team=away, tournament=req.tournament, fixture_id=req.fixture_id,
        algo_version=ANALYSIS_ALGO_VERSION, data_version=data_version, model_hash=model_hash,
        snapshot=snapshot,
    )
    db.add(analysis)
    db.flush()

    if atype == AnalysisType.independent:
        tx = post_transaction(
            db, wallet=wallet, tx_type=CreditTxType.consumption, amount=Decimal("-1"),
            idempotency_key=f"analysis-consume:{analysis.id}", reference_type="analysis",
            reference_id=analysis.id, description=f"Análise {home} x {away}",
        )
        consumed, reserved = 1, 0
    else:  # future_match — reserva
        tx = post_transaction(
            db, wallet=wallet, tx_type=CreditTxType.reservation, amount=Decimal("-1"),
            reserved_delta=Decimal("1"), idempotency_key=f"analysis-reserve:{analysis.id}",
            reference_type="analysis", reference_id=analysis.id,
            description=f"Reserva — análise {home} x {away}",
        )
        consumed, reserved = 0, 1

    analysis.credit_tx_id = tx.id
    db.commit()

    return schemas.AnalysisResponse(
        id=str(analysis.id), type=atype.value, status=analysis.status.value,
        home_team=home, away_team=away, tournament=req.tournament, fixture_id=req.fixture_id,
        algo_version=ANALYSIS_ALGO_VERSION, data_version=data_version, model_hash=model_hash,
        created_at=analysis.created_at, credits_consumed=consumed, credits_reserved=reserved,
        available_balance=wallet.available_balance, snapshot=snapshot,
    )


def list_analyses(db: Session, user: User, limit: int, offset: int) -> schemas.AnalysisPage:
    total = db.execute(
        select(func.count(Analysis.id)).where(Analysis.user_id == user.id)
    ).scalar_one()
    rows = db.execute(
        select(Analysis).where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    items = [schemas.AnalysisSummary(
        id=str(a.id), type=a.type.value, status=a.status.value, home_team=a.home_team,
        away_team=a.away_team, tournament=a.tournament, fixture_id=a.fixture_id,
        algo_version=a.algo_version, created_at=a.created_at,
    ) for a in rows]
    return schemas.AnalysisPage(items=items, total=total, limit=limit, offset=offset)


def get_analysis(db: Session, user: User, analysis_id: str) -> Analysis:
    try:
        aid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Análise não encontrada.")
    a = db.get(Analysis, aid)
    if a is None or a.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Análise não encontrada.")
    return a
