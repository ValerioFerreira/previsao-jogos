#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/value_report.py
=======================
Relatório de VALUE (Passo 4) sobre as odds + previsões já coletadas por
collect_odds_forward.py. Para cada jogo e mercado em que temos a probabilidade do
modelo E a odd da casa, calcula:

  - prob implícita do mercado (com margem) e a prob justa de-vig (sem margem);
  - EV por unidade apostada = p_modelo * odd - 1  (>0 => value, a casa paga acima
    do risco que o modelo estima);
  - lista ordenada das melhores oportunidades (+EV).

IMPORTANTE: isto mede a DIVERGÊNCIA modelo×mercado, não o lucro realizado. O
backtest de P&L precisa dos resultados (jogos ainda não disputados) e entra num
passo seguinte (resolver). O value aqui se apoia na calibração do modelo, não em
histórico de mercado — ver ressalva do projeto.

Uso:
  python scripts/value_report.py                 # todos os jogos coletados
  python scripts/value_report.py --min-ev 5      # só EV >= 5%
  python scripts/value_report.py --top 30
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "data" / "odds" / "snapshots"


def latest_snapshot(path: Path) -> dict | None:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


def devig(probs: list[float]) -> list[float]:
    """Normaliza probs implícitas (1/odd) removendo a margem da casa."""
    s = sum(probs)
    return [p / s for p in probs] if s > 0 else probs


def parse_line(label: str):
    """'Over 8.5' -> ('over', 8.5); 'Under 2.5' -> ('under', 2.5)."""
    parts = label.split()
    if len(parts) == 2:
        side = parts[0].lower()
        try:
            return side, float(parts[1])
        except ValueError:
            return None
    return None


def count_market_bets(snap: dict, odds_key: str, model_block: dict, escopo: str):
    """Casa as linhas O/U de um mercado de contagem (escanteios/cartoes) entre a odd
    da casa e a prob do modelo. model_block tem 'linhas': {'8.5': {over/under}}."""
    bets = []
    odds = snap["odds"].get(odds_key, {})
    linhas = (model_block or {}).get("linhas", {})
    for label, odd in odds.items():
        parsed = parse_line(label)
        if not parsed:
            continue
        side, line = parsed
        key = str(line)
        if key not in linhas or side not in ("over", "under"):
            continue
        p_model = linhas[key][side]["prob"] / 100.0
        bets.append((escopo, f"{side.capitalize()} {line}", p_model, float(odd)))
    return bets


def fixture_bets(snap: dict) -> list[tuple]:
    """Lista (mercado, selecao, p_modelo, odd_casa) com de-vig por grupo onde dá."""
    model = snap.get("model")
    if not model or "_erro" in model:
        return []
    home, away = snap["home"], snap["away"]
    bets = []

    # 1X2 (de-vig 3 vias para a prob justa de mercado; EV usa a odd crua)
    odds_1x2 = snap["odds"].get("resultado", {})
    probs = model["vencedor"]["probabilidades"]
    mapa = {"Home": home, "Draw": "Empate", "Away": away}
    for out, odd in odds_1x2.items():
        team = mapa.get(out)
        if team and team in probs:
            bets.append(("Resultado", out, probs[team] / 100.0, float(odd)))

    # Over/Under 2.5 gols
    ou = snap["odds"].get("gols_over_under", {})
    p_over = model["over_2_5"]["prob_sim"] / 100.0
    if "Over 2.5" in ou:
        bets.append(("Gols", "Over 2.5", p_over, float(ou["Over 2.5"])))
    if "Under 2.5" in ou:
        bets.append(("Gols", "Under 2.5", 1 - p_over, float(ou["Under 2.5"])))

    # BTTS
    btts = snap["odds"].get("btts", {})
    p_yes = model["ambas_marcam"]["prob_sim"] / 100.0
    for label, p in (("Yes", p_yes), ("No", 1 - p_yes)):
        if label in btts:
            bets.append(("Ambas marcam", label, p, float(btts[label])))

    # Escanteios e cartoes (mandante/visitante/total) por linha
    esc = model.get("escanteios", {})
    car = model.get("cartoes", {})
    bets += count_market_bets(snap, "escanteios_mandante", esc.get(home), "Escanteios mand.")
    bets += count_market_bets(snap, "escanteios_visitante", esc.get(away), "Escanteios vis.")
    bets += count_market_bets(snap, "escanteios_total", esc.get("total"), "Escanteios total")
    bets += count_market_bets(snap, "cartoes_mandante", car.get(home), "Cartoes mand.")
    bets += count_market_bets(snap, "cartoes_visitante", car.get(away), "Cartoes vis.")
    bets += count_market_bets(snap, "cartoes_total", car.get("total"), "Cartoes total")
    return bets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-ev", type=float, default=0.0, help="EV minimo em %% (padrao 0)")
    ap.add_argument("--top", type=int, default=25, help="quantas oportunidades listar")
    ap.add_argument("--max-odd", type=float, default=None,
                    help="ignora odds acima deste valor (corta zebras onde o modelo erra)")
    a = ap.parse_args()

    if not SNAP_DIR.exists():
        raise SystemExit("Sem snapshots. Rode antes: python scripts/collect_odds_forward.py")

    rows = []
    n_fixtures = 0
    n_no_model = 0
    for path in sorted(SNAP_DIR.glob("*.jsonl")):
        snap = latest_snapshot(path)
        if not snap:
            continue
        n_fixtures += 1
        bets = fixture_bets(snap)
        if not bets:
            n_no_model += 1
            continue
        jogo = f"{snap['home']} x {snap['away']}"
        for mercado, sel, p_model, odd in bets:
            ev = p_model * odd - 1.0
            rows.append({
                "jogo": jogo,
                "mercado": mercado,
                "selecao": sel,
                "p_model": p_model * 100,
                "odd": odd,
                "p_implicita": 100.0 / odd,
                "ev": ev * 100,
            })

    value = [r for r in rows if r["ev"] >= a.min_ev and (a.max_odd is None or r["odd"] <= a.max_odd)]
    value.sort(key=lambda r: r["ev"], reverse=True)

    print(f"Jogos com snapshot: {n_fixtures} | sem previsao do modelo: {n_no_model}")
    print(f"Apostas avaliadas: {len(rows)} | com EV >= {a.min_ev:.0f}%: {len(value)}\n")
    print(f"{'EV%':>6}  {'odd':>5}  {'pMod':>5}  {'pMkt':>5}  {'mercado':<17} {'selecao':<12} jogo")
    print("-" * 88)
    for r in value[: a.top]:
        print(f"{r['ev']:>+6.1f}  {r['odd']:>5.2f}  {r['p_model']:>5.1f}  {r['p_implicita']:>5.1f}  "
              f"{r['mercado']:<17} {r['selecao']:<12} {r['jogo']}")

    if rows:
        evs = [r["ev"] for r in rows]
        pos = [e for e in evs if e > 0]
        print(f"\nResumo: EV medio {sum(evs)/len(evs):+.1f}% | apostas +EV {len(pos)}/{len(rows)} "
              f"({100*len(pos)/len(rows):.0f}%) | melhor {max(evs):+.1f}% | pior {min(evs):+.1f}%")
    print("\nNota: mede divergencia modelo x mercado (calibracao), NAO lucro realizado. "
          "O P&L precisa dos resultados (resolver, passo seguinte).")


if __name__ == "__main__":
    main()
