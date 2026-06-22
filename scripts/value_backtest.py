#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/value_backtest.py
=========================
Backtest de VALUE realizado (o veredito do Passo 4). Junta, por jogo já resolvido:
  - o último snapshot pré-jogo (odds da casa + previsão do modelo) — collect_odds_forward;
  - o desfecho real por mercado — resolve_results;
e LIQUIDA cada aposta (ganhou/perdeu), calculando o P&L a 1 unidade na odd da casa.

Mede o que importa: as apostas que o MODELO marcou como +EV deram lucro? E a
calibração (prob do modelo vs frequência real de acerto) se sustenta fora da amostra?

A pergunta-chave do projeto ("o sistema tem valor de aposta real?") só começa a ser
respondida aqui, e só com volume suficiente de jogos resolvidos. Com poucos jogos, o
resultado é ruído — o relatório mostra o N para calibrar a leitura.

Uso:
  python scripts/value_backtest.py
  python scripts/value_backtest.py --max-odd 3.0     # foca mercados liquidos
  python scripts/value_backtest.py --min-ev 3        # so apostas com EV>=3% do modelo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from scripts.value_report import fixture_bets, latest_snapshot  # noqa: E402

ODDS_DIR = ROOT / "data" / "odds"
SNAP_DIR = ODDS_DIR / "snapshots"
RESULTS_DIR = ODDS_DIR / "results"

_COUNT_FIELD = {
    "Escanteios mand.": "corners_home",
    "Escanteios vis.": "corners_away",
    "Escanteios total": "corners_total",
    "Cartoes mand.": "cards_home",
    "Cartoes vis.": "cards_away",
    "Cartoes total": "cards_total",
}


def settle(mercado: str, selecao: str, outcome: dict):
    """True=ganhou, False=perdeu, None=nao liquidavel (dado faltando)."""
    if mercado == "Resultado":
        res = outcome.get("result")
        return None if res is None else (res == selecao)
    if mercado == "Gols":
        tg = outcome.get("total_goals")
        if tg is None:
            return None
        side, line = selecao.split()
        return tg > float(line) if side == "Over" else tg < float(line)
    if mercado == "Ambas marcam":
        b = outcome.get("btts")
        if b is None:
            return None
        return bool(b) if selecao == "Yes" else (not b)
    field = _COUNT_FIELD.get(mercado)
    if field is None:
        return None
    actual = outcome.get(field)
    if actual is None:
        return None
    side, line = selecao.split()
    return actual > float(line) if side == "Over" else actual < float(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-ev", type=float, default=0.0, help="so apostas com EV do modelo >= isto (%%)")
    ap.add_argument("--max-odd", type=float, default=None, help="ignora odds acima disto (corta zebras)")
    a = ap.parse_args()

    if not RESULTS_DIR.exists() or not any(RESULTS_DIR.glob("*.json")):
        raise SystemExit("Sem jogos resolvidos ainda. Rode: python scripts/resolve_results.py "
                         "(os jogos da Copa comecam a resolver conforme sao disputados).")

    settled = []  # (mercado, ev, odd, win)
    n_games = 0
    for res_path in sorted(RESULTS_DIR.glob("*.json")):
        outcome = json.loads(res_path.read_text(encoding="utf-8"))
        snap_path = SNAP_DIR / f"{res_path.stem}.jsonl"
        if not snap_path.exists():
            continue
        snap = latest_snapshot(snap_path)
        if not snap:
            continue
        n_games += 1
        for mercado, sel, p_model, odd in fixture_bets(snap):
            if a.max_odd is not None and odd > a.max_odd:
                continue
            ev = p_model * odd - 1.0
            if ev * 100 < a.min_ev:
                continue
            win = settle(mercado, sel, outcome)
            if win is None:
                continue
            settled.append({"mercado": mercado, "ev": ev * 100, "p_model": p_model * 100,
                            "odd": odd, "win": win, "pnl": (odd - 1.0) if win else -1.0})

    if not settled:
        print(f"Jogos resolvidos com snapshot: {n_games}, mas nenhuma aposta liquidavel "
              f"sob os filtros (min-ev={a.min_ev}, max-odd={a.max_odd}).")
        return

    def expected_calibration_error(y_true, y_prob, n_bins=10):
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
            prop_in_bin = np.mean(in_bin)
            if prop_in_bin > 0:
                accuracy_in_bin = np.mean(y_true[in_bin])
                avg_confidence_in_bin = np.mean(y_prob[in_bin])
                ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)
        return ece

    def tail_expected_calibration_error(y_true, y_prob, n_bins=10):
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            if bin_upper > 0.2 and bin_lower < 0.8:
                continue
            in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
            prop_in_bin = np.mean(in_bin)
            if prop_in_bin > 0:
                accuracy_in_bin = np.mean(y_true[in_bin])
                avg_confidence_in_bin = np.mean(y_prob[in_bin])
                ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)
        tail_mask = (y_prob < 0.2) | (y_prob >= 0.8)
        prop_total = np.mean(tail_mask)
        if prop_total > 0:
            ece = ece / prop_total
        return ece

    def roi(rows):
        pnl = sum(r["pnl"] for r in rows)
        return pnl, 100 * pnl / len(rows), sum(r["win"] for r in rows), len(rows)

    print(f"Jogos resolvidos: {n_games} | apostas liquidadas: {len(settled)}\n")
    pnl, r, w, n = roi(settled)
    
    y_true_all = np.array([float(s["win"]) for s in settled])
    y_prob_all = np.array([s["p_model"] / 100.0 for s in settled])
    ece_all = expected_calibration_error(y_true_all, y_prob_all)
    tail_ece_all = tail_expected_calibration_error(y_true_all, y_prob_all)
    
    print(f"GERAL: {n} apostas | acerto {w}/{n} ({100*w/n:.0f}%) | P&L {pnl:+.2f}u | ROI {r:+.1f}% | ECE {ece_all:.2%} | Tail ECE {tail_ece_all:.2%}")

    ev_pos = [s for s in settled if s["ev"] > 0]
    if ev_pos:
        pnl, r, w, n = roi(ev_pos)
        y_true_ev = np.array([float(s["win"]) for s in ev_pos])
        y_prob_ev = np.array([s["p_model"] / 100.0 for s in ev_pos])
        ece_ev = expected_calibration_error(y_true_ev, y_prob_ev)
        tail_ece_ev = tail_expected_calibration_error(y_true_ev, y_prob_ev)
        print(f"+EV (modelo): {n} apostas | acerto {w}/{n} ({100*w/n:.0f}%) | P&L {pnl:+.2f}u | ROI {r:+.1f}% | ECE {ece_ev:.2%} | Tail ECE {tail_ece_ev:.2%}")

    # por mercado
    print("\nPor mercado:")
    mercados = sorted({s["mercado"] for s in settled})
    for m in mercados:
        rows = [s for s in settled if s["mercado"] == m]
        pnl, r, w, n = roi(rows)
        y_true_m = np.array([float(s["win"]) for s in rows])
        y_prob_m = np.array([s["p_model"] / 100.0 for s in rows])
        ece_m = expected_calibration_error(y_true_m, y_prob_m)
        tail_ece_m = tail_expected_calibration_error(y_true_m, y_prob_m)
        print(f"  {m:<17} {n:>3} apostas | acerto {100*w/n:>3.0f}% | ROI {r:+6.1f}% | ECE {ece_m:.2%} | Tail ECE {tail_ece_m:.2%}")

    # calibracao por faixa de prob do modelo
    print("\nCalibracao (prob do modelo x acerto real):")
    bins = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
    for lo, hi in bins:
        rows = [s for s in settled if lo <= s["p_model"] < hi]
        if not rows:
            continue
        avg_p = sum(s["p_model"] for s in rows) / len(rows)
        real = 100 * sum(s["win"] for s in rows) / len(rows)
        print(f"  [{lo:>3}-{hi-1:>3}%] n={len(rows):>3} | modelo {avg_p:>4.1f}% vs real {real:>4.1f}%")

    print("\nNota: com N baixo isto e RUIDO. So ganha forca com dezenas/centenas de "
          "apostas liquidadas. Cartoes: casas podem contar vermelho como 2 (possivel "
          "divergencia na liquidacao).")


if __name__ == "__main__":
    main()
