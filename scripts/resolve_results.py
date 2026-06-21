#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/resolve_results.py
==========================
Resolver: busca o resultado/estatística REAL dos jogos já coletados (registry) que
já foram disputados e extrai os desfechos por mercado, para alimentar o backtest de
value (Passo 4 — value_backtest.py).

Para cada fixture do registry ainda não resolvido cujo horário já passou, consulta
/fixtures?id= e extrai: resultado (H/D/A) e total de gols pelo placar de 90 min
(score.fulltime, alinhado com o que o modelo prevê), BTTS, escanteios e cartões
(amarelos+vermelhos) por lado/total, e chutes. Grava data/odds/results/<id>.json.

A função extract_outcomes funciona sobre a MESMA estrutura de item da api-football,
seja vinda da API (ao vivo) ou de um .json.gz histórico (para validar a extração).

CAVEAT (cartões): contamos cartão = amarelo + vermelho (cada um conta 1), alinhado
com o alvo do modelo. Casas às vezes contam vermelho como 2 — divergência possível
na liquidação do mercado de cartões, registrada.

Uso:
  python scripts/resolve_results.py            # resolve os que já passaram
  python scripts/resolve_results.py --all      # tenta todos do registry
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from scripts.fetch_odds import BASE, load_key  # noqa: E402

ODDS_DIR = ROOT / "data" / "odds"
REGISTRY = ODDS_DIR / "registry.json"
RESULTS_DIR = ODDS_DIR / "results"


def _num(value):
    """Converte '80%' -> 80, None -> None, '15' -> 15."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().rstrip("%")
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return None
    return value


def extract_outcomes(item: dict) -> dict:
    """Desfechos por mercado a partir de um item de fixture da api-football."""
    fx = item.get("fixture", {})
    status = (fx.get("status") or {}).get("short")
    teams = item.get("teams", {})
    home = (teams.get("home") or {}).get("name")
    away = (teams.get("away") or {}).get("name")

    score = item.get("score", {})
    ft = (score.get("fulltime") or {})
    gh, ga = ft.get("home"), ft.get("away")
    if gh is None or ga is None:  # fallback p/ placar geral
        g = item.get("goals", {})
        gh, ga = g.get("home"), g.get("away")

    out = {"status": status, "home": home, "away": away, "resolved": False}
    if gh is None or ga is None:
        return out

    by_team = {}
    for t in item.get("statistics") or []:
        nm = (t.get("team") or {}).get("name")
        by_team[nm] = {s.get("type"): s.get("value") for s in (t.get("statistics") or [])}

    def corners(nm):
        return _num((by_team.get(nm) or {}).get("Corner Kicks"))

    def cards(nm):
        d = by_team.get(nm) or {}
        y = _num(d.get("Yellow Cards")) or 0
        r = _num(d.get("Red Cards")) or 0
        return y + r if (nm in by_team) else None

    def shots(nm):
        return _num((by_team.get(nm) or {}).get("Total Shots"))

    ch, ca = corners(home), corners(away)
    yh, ya = cards(home), cards(away)
    out.update({
        "goals_home": gh, "goals_away": ga, "total_goals": gh + ga,
        "result": "Home" if gh > ga else ("Away" if ga > gh else "Draw"),
        "btts": bool(gh > 0 and ga > 0),
        "corners_home": ch, "corners_away": ca,
        "corners_total": (ch + ca) if (ch is not None and ca is not None) else None,
        "cards_home": yh, "cards_away": ya,
        "cards_total": (yh + ya) if (yh is not None and ya is not None) else None,
        "shots_home": shots(home), "shots_away": shots(away),
        "has_stats": bool(by_team),
        "resolved": status in ("FT", "AET", "PEN"),
    })
    return out


def already_past(fixture_date: str | None) -> bool:
    if not fixture_date:
        return False
    try:
        dt = datetime.fromisoformat(fixture_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    # +2h de folga para o jogo terminar
    return (datetime.now(timezone.utc) - dt).total_seconds() > 2 * 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="tenta resolver todos do registry, nao so os ja passados")
    a = ap.parse_args()
    if not REGISTRY.exists():
        raise SystemExit("Sem registry. Rode antes: python scripts/collect_odds_forward.py")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    key = load_key()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    resolved, skipped, pending = 0, 0, 0
    for fid, meta in registry.items():
        out_path = RESULTS_DIR / f"{fid}.json"
        if out_path.exists():
            skipped += 1
            continue
        if not a.all and not already_past(meta.get("fixture_date")):
            pending += 1
            continue
        r = requests.get(BASE + "/fixtures", headers={"x-apisports-key": key}, params={"id": fid}, timeout=30)
        r.raise_for_status()
        resp = r.json().get("response", [])
        if not resp:
            pending += 1
            continue
        outcome = extract_outcomes(resp[0])
        outcome["fixture_id"] = int(fid)
        if outcome.get("resolved"):
            out_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
            resolved += 1
            print(f"  resolvido {fid}: {meta['home']} {outcome.get('goals_home')}-{outcome.get('goals_away')} "
                  f"{meta['away']} | esc {outcome.get('corners_total')} | cart {outcome.get('cards_total')}")
        else:
            pending += 1

    print(f"\nResolvidos agora: {resolved} | ja resolvidos: {skipped} | pendentes: {pending}")
    print(f"Resultados em {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
