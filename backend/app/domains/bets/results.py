"""Provedor de RESULTADO OFICIAL da partida (para liquidar apostas). Abstrato/trocável:
adapter API-Football real + injeção de um mock nos testes. Extrai placar e box-score
(escanteios, cartões, finalizações, finalizações a gol) de UMA chamada /fixtures?id."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

_FINISHED = {"FT", "AET", "PEN"}
_LIVE = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}


@dataclass
class MatchResult:
    finished: bool
    kicked_off: bool
    kickoff: datetime | None = None
    home_goals: int | None = None
    away_goals: int | None = None
    total_corners: int | None = None
    total_cards: int | None = None
    total_shots: int | None = None
    total_shots_on_target: int | None = None


class ResultProvider(Protocol):
    def get(self, fixture_id: int) -> MatchResult | None: ...


def _stat_sum(fx: dict, name: str) -> int | None:
    total, found = 0, False
    for block in fx.get("statistics") or []:
        for s in block.get("statistics") or []:
            if s.get("type") == name and s.get("value") is not None:
                try:
                    total += int(s["value"]); found = True
                except (TypeError, ValueError):
                    pass
    return total if found else None


class ApiFootballResultProvider:
    """Adapter real: usa fetch_full_by_id (mesma API/cache do detalhe de partida)."""

    def get(self, fixture_id: int) -> MatchResult | None:
        from app.services.fixture_fetch import fetch_full_by_id
        fx = fetch_full_by_id(fixture_id)
        if not fx:
            return None
        status = ((fx.get("fixture") or {}).get("status") or {}).get("short", "")
        goals = fx.get("goals") or {}
        kickoff = None
        try:
            kickoff = datetime.fromisoformat(((fx.get("fixture") or {}).get("date") or "").replace("Z", "+00:00"))
        except ValueError:
            pass
        finished = status in _FINISHED
        cards = None
        y, r = _stat_sum(fx, "Yellow Cards"), _stat_sum(fx, "Red Cards")
        if y is not None or r is not None:
            cards = (y or 0) + (r or 0)
        return MatchResult(
            finished=finished,
            kicked_off=finished or status in _LIVE,
            kickoff=kickoff,
            home_goals=goals.get("home"), away_goals=goals.get("away"),
            total_corners=_stat_sum(fx, "Corner Kicks"),
            total_cards=cards,
            total_shots=_stat_sum(fx, "Total Shots"),
            total_shots_on_target=_stat_sum(fx, "Shots on Goal"),
        )


def get_result_provider() -> ResultProvider:
    return ApiFootballResultProvider()
