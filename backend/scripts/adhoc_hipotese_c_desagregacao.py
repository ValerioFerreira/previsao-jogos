#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_hipotese_c_desagregacao.py
==========================================
Hipotese C (v2, honesta) -- desagregacao do desempenho do MODELO (pick 1x2,
preco Avg real, mesma base de bets da Hipotese B) por liga e por ano.

Diferenca central pra v1 (DESCARTADA): nao ha tabela de 89 competicoes com
linhas de N=1 reportando 100% de acerto. Qualquer grupo abaixo do piso minimo
de amostra (MIN_N=100) vai para um bucket "amostra insuficiente", nunca uma
linha individual enganosa. O periodo coberto e o que a base real permite --
temporada 2025/26 (data-test), nao "2010-2026" fabricado.

Uso: python scripts/adhoc_hipotese_c_desagregacao.py
Saida: data/reports/hipotese_c_desagregacao_liga.csv, .../hipotese_c_desagregacao_ano.csv
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT_DIR = ROOT / "data" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REF_BOOK = "Avg"
MIN_N = 100
N_BOOT = 20000
SEED = 20260728


def bootstrap_ci(net: np.ndarray, n_boot: int, rng: np.random.Generator):
    n = len(net)
    idx = rng.integers(0, n, size=(n_boot, n))
    roi_boot = 100.0 * net[idx].sum(axis=1) / n
    lo, hi = np.percentile(roi_boot, [2.5, 97.5])
    return float(lo), float(hi)


def main():
    print("=" * 90)
    print(" HIPOTESE C (v2) -- DESAGREGACAO POR LIGA E ANO (piso de amostra N>=100)")
    print("=" * 90)

    if not PREDICTIONS.exists():
        raise SystemExit(f"{PREDICTIONS} nao existe -- rode backtest_generate_predictions.py primeiro.")

    preds = pd.read_parquet(PREDICTIONS)
    matched = pd.read_parquet(MATCHED)
    odds = pd.read_parquet(ODDS)
    odds = odds[(odds["book"] == REF_BOOK) & (odds["market"] == "1x2")].copy()
    odds["_key5"] = list(zip(odds["source"], odds["div"], odds["date"],
                              odds["home_team_raw"], odds["away_team_raw"]))
    # Preferir fechamento, cai pra abertura se faltar -- BRA (xlsx) so publica "closing".
    odds = odds.sort_values("closing").drop_duplicates(subset=["_key5", "side"], keep="last")
    odds_1x2 = {}
    for k5, side, value in zip(odds["_key5"], odds["side"], odds["value"]):
        odds_1x2.setdefault(k5, {})[side] = value

    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    matched_ok["_key5"] = list(zip(matched_ok["source"], matched_ok["div"], matched_ok["date"],
                                    matched_ok["home_team_raw"], matched_ok["away_team_raw"]))
    fx_to_key5 = dict(zip(matched_ok["fixture_id"], matched_ok["_key5"]))

    preds["prediction"] = preds["prediction_json"].map(json.loads)
    preds["date"] = pd.to_datetime(preds["date"])

    rows = []
    for r in preds.itertuples(index=False):
        key5 = fx_to_key5.get(r.fixture_id)
        orow = odds_1x2.get(key5)
        if orow is None:
            continue
        oh, od, oa = orow.get("H"), orow.get("D"), orow.get("A")
        if oh is None or od is None or oa is None:
            continue
        probs = r.prediction.get("vencedor", {}).get("probabilidades", {})
        p_home, p_draw, p_away = probs.get(r.home_team), probs.get("Empate"), probs.get(r.away_team)
        if None in (p_home, p_draw, p_away):
            continue
        pick = ["H", "D", "A"][int(np.argmax([p_home, p_draw, p_away]))]
        actual = "H" if r.home_score > r.away_score else ("A" if r.away_score > r.home_score else "D")
        odd_taken = {"H": oh, "D": od, "A": oa}[pick]
        win = pick == actual
        rows.append(dict(fixture_id=r.fixture_id, tournament=r.tournament, year=r.date.year,
                          win=win, net_return=(odd_taken - 1.0) if win else -1.0))

    df = pd.DataFrame(rows)
    print(f"\nApostas do modelo (1x2, pick vs Avg real) disponiveis: {len(df)}")
    if df.empty:
        raise SystemExit("Nenhuma aposta disponivel -- nada a desagregar.")

    rng = np.random.default_rng(SEED)

    def build_table(group_col: str, out_name: str):
        rows_out = []
        insuf_net = []
        for key, g in df.groupby(group_col):
            n = len(g)
            net = g["net_return"].to_numpy()
            if n < MIN_N:
                insuf_net.append(net)
                continue
            roi = 100.0 * net.sum() / n
            wr = 100.0 * g["win"].mean()
            lo, hi = bootstrap_ci(net, N_BOOT, rng)
            rows_out.append({group_col: str(key), "n": n, "winrate_pct": round(wr, 2),
                              "roi_pct": round(roi, 2), "roi_ic95_lo": round(lo, 2),
                              "roi_ic95_hi": round(hi, 2), "amostra_suficiente": True})
        if insuf_net:
            net = np.concatenate(insuf_net)
            n = len(net)
            roi = 100.0 * net.sum() / n
            rows_out.append({group_col: f"outras (amostra insuficiente, N<{MIN_N} cada)", "n": n,
                              "winrate_pct": None, "roi_pct": round(roi, 2),
                              "roi_ic95_lo": None, "roi_ic95_hi": None, "amostra_suficiente": False})
        out = pd.DataFrame(rows_out).sort_values("roi_pct", ascending=False)
        out.to_csv(OUT_DIR / out_name, index=False)
        print(f"\n--- Por {group_col} (piso N>={MIN_N}) ---")
        for r in out.itertuples(index=False):
            if r.amostra_suficiente:
                print(f"  {getattr(r, group_col):40s} N={r.n:4d}  winrate={r.winrate_pct:5.1f}%  "
                      f"ROI={r.roi_pct:+7.2f}%  IC95%=[{r.roi_ic95_lo:+6.2f}%,{r.roi_ic95_hi:+6.2f}%]")
            else:
                print(f"  {getattr(r, group_col):40s} N={r.n:4d}  ROI={r.roi_pct:+7.2f}%  (sem IC -- grupos pequenos agregados)")
        print(f"Salvo: {OUT_DIR / out_name}")
        return out

    build_table("tournament", "hipotese_c_desagregacao_liga.csv")
    build_table("year", "hipotese_c_desagregacao_ano.csv")

    print(f"\nNOTA: periodo coberto pela base real (data-test): {df.merge(preds[['fixture_id','date']], on='fixture_id')['date'].min().date()} "
          f"a {df.merge(preds[['fixture_id','date']], on='fixture_id')['date'].max().date()} -- uma temporada, nao "
          f"2010-2026 (isso era a base fabricada da v1).")


if __name__ == "__main__":
    main()
