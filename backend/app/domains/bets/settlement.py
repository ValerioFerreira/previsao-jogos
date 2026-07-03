"""Liquidação automática da 'Aposta Escolhida' (promo 'Só Paga se Acertar').

Fluxo por aposta em aberto:
  1. Consulta o resultado oficial (provider). Se ainda não começou/terminou, aguarda.
  2. Ao detectar FIM da partida, aguarda um DELAY DE SEGURANÇA (evita alteração do placar).
  3. Passado o delay, reconsulta e LIQUIDA:
       - aposta VENCEDORA  -> consome o crédito reservado;
       - aposta NÃO vencedora (ou indeterminável) -> ESTORNA o crédito reservado.
Idempotente (idempotency_key no ledger + guarda por status). Auditável (BetSettlement).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.analysis.models import Analysis
from app.domains.bets.models import Bet, BetSelection, BetSettlement
from app.domains.bets.results import MatchResult, ResultProvider
from app.domains.enums import AnalysisStatus, BetStatus, CreditTxType, SettlementOutcome
from app.domains.wallet.service import get_or_create_wallet, post_transaction

_OPEN = (BetStatus.awaiting_start, BetStatus.in_progress, BetStatus.awaiting_settlement)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_leg(group: str, selection: str, r: MatchResult) -> bool | None:
    """True=venceu, False=perdeu, None=indeterminável (dados ausentes)."""
    if group == "resultado":
        if r.home_goals is None or r.away_goals is None:
            return None
        if selection == "home":
            return r.home_goals > r.away_goals
        if selection == "away":
            return r.home_goals < r.away_goals
        return r.home_goals == r.away_goals
    if group == "btts":
        if r.home_goals is None or r.away_goals is None:
            return None
        both = r.home_goals > 0 and r.away_goals > 0
        return both if selection == "sim" else (not both)
    if group == "gols_ou2.5":
        if r.home_goals is None or r.away_goals is None:
            return None
        total = r.home_goals + r.away_goals
        return total > 2.5 if selection == "over" else total < 2.5
    if "_total:" in group:
        mkt, _, line_s = group.partition("_total:")
        try:
            line = float(line_s)
        except ValueError:
            return None
        value = {
            "escanteios": r.total_corners, "cartoes": r.total_cards,
            "chutes": r.total_shots, "chutes_a_gol": r.total_shots_on_target,
        }.get(mkt)
        if value is None:
            return None
        return value > line if selection == "over" else value < line
    return None


def _group_of(sel: BetSelection) -> str:
    ref = sel.snapshot_ref or {}
    return ref.get("group") or ""


def settle_bet(db: Session, bet: Bet, result: MatchResult) -> SettlementOutcome:
    """Avalia (combinada: TODAS as pernas precisam vencer) e aplica consumo/estorno."""
    if bet.status not in _OPEN:
        return None  # já liquidada — idempotente

    sels = db.execute(select(BetSelection).where(BetSelection.bet_id == bet.id)).scalars().all()
    legs = [evaluate_leg(_group_of(s), s.selection, result) for s in sels]
    if any(x is None for x in legs):
        outcome = SettlementOutcome.void          # indeterminável -> estorna
    elif all(legs):
        outcome = SettlementOutcome.won            # todas venceram -> consome
    else:
        outcome = SettlementOutcome.lost           # alguma perdeu -> estorna

    wallet = get_or_create_wallet(db, bet.user_id)
    if outcome == SettlementOutcome.won:
        tx = post_transaction(
            db, wallet=wallet, tx_type=CreditTxType.consumption, amount=Decimal("0"),
            reserved_delta=Decimal("-1"), idempotency_key=f"bet-settle:{bet.id}",
            reference_type="bet", reference_id=bet.id, description="Aposta vencedora — crédito consumido",
        )
        bet.status = BetStatus.credit_consumed
        analysis = db.get(Analysis, bet.analysis_id)
        if analysis is not None:
            analysis.status = AnalysisStatus.consumed
    else:
        tx = post_transaction(
            db, wallet=wallet, tx_type=CreditTxType.reservation_release, amount=Decimal("1"),
            reserved_delta=Decimal("-1"), idempotency_key=f"bet-settle:{bet.id}",
            reference_type="bet", reference_id=bet.id,
            description="Aposta não vencedora — crédito estornado" if outcome == SettlementOutcome.lost
            else "Aposta anulada — crédito estornado",
        )
        bet.status = BetStatus.credit_refunded

    bet.resolution_tx_id = tx.id
    _record_settlement(db, bet, outcome, result)
    return outcome


def _get_or_create_settlement(db: Session, bet: Bet) -> BetSettlement:
    st = db.execute(select(BetSettlement).where(BetSettlement.bet_id == bet.id)).scalar_one_or_none()
    if st is None:
        st = BetSettlement(bet_id=bet.id, attempts=0)
        db.add(st)
        db.flush()
    return st


def _record_settlement(db: Session, bet: Bet, outcome: SettlementOutcome, result: MatchResult) -> None:
    st = _get_or_create_settlement(db, bet)
    st.settled_at = _now()
    st.outcome = outcome
    st.attempts += 1
    st.api_result = {
        "home_goals": result.home_goals, "away_goals": result.away_goals,
        "total_corners": result.total_corners, "total_cards": result.total_cards,
        "total_shots": result.total_shots, "total_shots_on_target": result.total_shots_on_target,
    }


def run_due_settlements(db: Session, provider: ResultProvider, now: datetime | None = None) -> dict:
    now = now or _now()
    delay = timedelta(minutes=settings.settlement_safety_delay_min)
    bets = db.execute(select(Bet).where(Bet.status.in_(_OPEN))).scalars().all()
    counts = {"checked": 0, "in_progress": 0, "waiting_delay": 0, "won": 0, "lost": 0, "void": 0, "pending": 0}

    for bet in bets:
        counts["checked"] += 1
        if not bet.fixture_id:
            continue
        try:
            res = provider.get(bet.fixture_id)
        except Exception:
            res = None
        if res is None:
            counts["pending"] += 1
            db.commit()
            continue

        if not res.finished:
            if res.kicked_off and bet.status == BetStatus.awaiting_start:
                bet.status = BetStatus.in_progress
                counts["in_progress"] += 1
            else:
                counts["pending"] += 1
            db.commit()
            continue

        # partida terminou -> aplica o delay de segurança antes de liquidar
        st = _get_or_create_settlement(db, bet)
        if st.safety_delay_until is None:
            st.safety_delay_until = now + delay
            bet.status = BetStatus.awaiting_settlement
            counts["waiting_delay"] += 1
            db.commit()
            continue
        sdu = st.safety_delay_until
        if sdu.tzinfo is None:
            sdu = sdu.replace(tzinfo=timezone.utc)
        if now < sdu:
            counts["waiting_delay"] += 1
            db.commit()
            continue

        outcome = settle_bet(db, bet, res)
        if outcome is not None:
            counts[outcome.value] += 1
        db.commit()

    return counts
