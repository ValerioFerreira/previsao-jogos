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
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.analysis import schemas
from app.domains.analysis.models import Analysis, FreeDailyUse
from app.domains.admin.models import MatchDeepAnalysis
from app.domains.analytics import service as analytics_service
from app.domains.enums import AnalysisStatus, AnalysisType, CreditTxType
from app.domains.users.models import User
from app.domains.wallet.service import get_or_create_wallet, post_transaction

ANALYSIS_ALGO_VERSION = "1.0.0"   # pipeline DC-NB + cascata NB/GP + calibração O/U
FREE_TOURNAMENT = "Copa do Mundo"  # único identificador disponível hoje (sem campo de ano)


def _try_claim_daily_free(db: Session, user_id: uuid.UUID) -> bool:
    """Tenta reservar a análise grátis do dia — mesma idempotência do ledger (unique
    constraint em vez de checar-e-inserir, para não ter corrida em concorrência)."""
    today = datetime.now(timezone.utc).date()
    savepoint = db.begin_nested()
    try:
        db.add(FreeDailyUse(user_id=user_id, used_on=today))
        db.flush()
        savepoint.commit()
        return True
    except IntegrityError:
        savepoint.rollback()
        return False


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
    from app.services.predictor_service import _predictor_for, predict_match

    scope = req.scope if req.scope == "clube" else "selecao"
    predictor = _predictor_for(scope)
    home = predictor.norm_team(req.home_team)
    away = predictor.norm_team(req.away_team)
    if home == away:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Escolha duas equipes diferentes.")
    if home not in predictor.teams() or away not in predictor.teams():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Time não encontrado.")
    if req.tournament not in predictor.meta["tournament_weights"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Competição inválida.")
    payload = PredictRequest(home_team=home, away_team=away, neutral=req.neutral,
                             tournament=req.tournament, scope=scope)
    return predict_match(payload, scope=scope), home, away


_FINISHED_OR_LIVE = {"FT", "AET", "PEN", "1H", "2H", "HT", "ET", "BT", "P", "LIVE"}


def _reject_if_fixture_started(fixture_id: int) -> None:
    """Impede gerar análise de partida futura para um confronto que já começou/terminou
    (aba aberta há horas, seleção presa no localStorage etc.) — best-effort: se a API
    falhar, deixa passar (não bloqueia o fluxo por indisponibilidade externa)."""
    try:
        from app.services.fixture_fetch import fetch_full_by_id
        fx = fetch_full_by_id(fixture_id)
    except Exception:
        return
    if not fx:
        return
    status_short = ((fx.get("fixture") or {}).get("status") or {}).get("short", "")
    if status_short in _FINISHED_OR_LIVE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Esta partida já aconteceu. Para informações sobre a mesma, vá à página de Estatísticas.",
        )


def create_analysis(db: Session, user: User, req: schemas.AnalysisRequest) -> schemas.AnalysisResponse:
    if req.type == "future_match" and not req.fixture_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="fixture_id é obrigatório para análise de partida futura.")
    if req.type == "future_match" and req.fixture_id:
        _reject_if_fixture_started(req.fixture_id)

    wallet = get_or_create_wallet(db, user.id)

    # Copa do Mundo é grátis ilimitada; senão, tenta consumir a cota diária grátis (1x/dia
    # por usuário) ANTES de checar saldo — só se a análise realmente for gerada com sucesso
    # (snapshot abaixo) é que o crédito/gratuidade é efetivado, evitando gastar a cota do
    # dia numa requisição que ia falhar de qualquer forma.
    is_wc_free = req.tournament == FREE_TOURNAMENT
    used_daily_free = False
    if is_wc_free or user.is_demo:
        # Conta demo compartilhada (créditos ilimitados p/ parceiros divulgarem a
        # plataforma) — tratada como gratuita: nunca debita nem toca no ledger da carteira.
        is_free = True
    else:
        used_daily_free = _try_claim_daily_free(db, user.id)
        is_free = used_daily_free
        if not is_free and Decimal(wallet.available_balance) < 1:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                                detail="Créditos insuficientes. Compre créditos para gerar a análise.")

    analytics_service.track(db, "analysis_started", user_id=user.id, type=req.type, tournament=req.tournament)
    snapshot, home, away = _generate_snapshot(req)
    data_version, model_hash = _model_fingerprint()
    atype = AnalysisType(req.type)

    analysis = Analysis(
        user_id=user.id, type=atype,
        status=AnalysisStatus.consumed if atype == AnalysisType.independent else AnalysisStatus.reserved,
        home_team=home, away_team=away, tournament=req.tournament, fixture_id=req.fixture_id,
        algo_version=ANALYSIS_ALGO_VERSION, data_version=data_version, model_hash=model_hash,
        snapshot=snapshot, is_free=is_free,
    )
    db.add(analysis)
    db.flush()

    if used_daily_free:
        today = datetime.now(timezone.utc).date()
        claim = db.execute(select(FreeDailyUse).where(
            FreeDailyUse.user_id == user.id, FreeDailyUse.used_on == today,
        )).scalar_one_or_none()
        if claim is not None:
            claim.analysis_id = analysis.id

    tx = None
    if is_free:
        consumed, reserved = 0, 0
    elif atype == AnalysisType.independent:
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

    if tx is not None:
        analysis.credit_tx_id = tx.id
    analytics_service.track(db, "analysis_finished", user_id=user.id, analysis_id=str(analysis.id))
    db.commit()

    res_snapshot = dict(snapshot)
    if req.fixture_id:
        da = db.execute(select(MatchDeepAnalysis).where(MatchDeepAnalysis.fixture_id == req.fixture_id)).scalar_one_or_none()
        if da:
            res_snapshot["deep_analysis"] = {"analyst_name": da.analyst_name, "markdown_content": da.markdown_content}

    return schemas.AnalysisResponse(
        id=str(analysis.id), type=atype.value, status=analysis.status.value,
        home_team=home, away_team=away, tournament=req.tournament, fixture_id=req.fixture_id,
        algo_version=ANALYSIS_ALGO_VERSION, data_version=data_version, model_hash=model_hash,
        created_at=analysis.created_at, credits_consumed=consumed, credits_reserved=reserved,
        is_free=is_free, available_balance=wallet.available_balance, snapshot=res_snapshot,
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
