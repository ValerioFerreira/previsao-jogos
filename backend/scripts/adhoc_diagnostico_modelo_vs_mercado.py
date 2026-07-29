#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_diagnostico_modelo_vs_mercado.py
================================================
Diagnostico honesto: o modelo esta "errado" ou o ROI negativo e o esperado?

ROI e uma metrica de altissima variancia -- com N~700 o erro padrao e da ordem
de +-6pp, entao "-12.95%" pode ser ruido em cima de um modelo perfeitamente
sao. As perguntas certas sao:

  1. Qual o VIG (overround) real das odds? -> define o ROI esperado de QUALQUER
     apostador sem edge. Esse e o benchmark honesto, nao zero.
  2. O modelo bate o MERCADO em log-loss/Brier/ECE (metrica propria de
     probabilidade, nao de dinheiro)? Mercado de-vigado e o benchmark mais
     duro que existe.
  3. Qual o piso de ruido do ROI (SE) nessa amostra? Os resultados observados
     estao dentro ou fora do que o acaso explica?

Uso: python scripts/adhoc_diagnostico_modelo_vs_mercado.py
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
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from devig_methods import shin_devig, proportional_devig  # noqa: E402

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT = ROOT / "data" / "reports" / "diagnostico_modelo_vs_mercado.csv"

REF_BOOK = "Avg"
EPS = 1e-12


def log_loss_multi(probs: np.ndarray, actual_idx: np.ndarray) -> float:
    p = np.clip(probs[np.arange(len(actual_idx)), actual_idx], EPS, 1.0)
    return float(-np.mean(np.log(p)))


def brier_multi(probs: np.ndarray, actual_idx: np.ndarray) -> float:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(actual_idx)), actual_idx] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def ece(probs_flat: np.ndarray, outcomes_flat: np.ndarray, n_bins=10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.digitize(probs_flat, bins) - 1
    idx = np.clip(idx, 0, n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        total += (m.sum() / len(probs_flat)) * abs(probs_flat[m].mean() - outcomes_flat[m].mean())
    return float(total)


def main():
    print("=" * 92)
    print(" DIAGNOSTICO -- O MODELO ESTA ERRADO, OU O ROI NEGATIVO E O ESPERADO?")
    print("=" * 92)

    preds = pd.read_parquet(PREDICTIONS)
    matched = pd.read_parquet(MATCHED)
    odds = pd.read_parquet(ODDS)
    odds = odds[(odds["book"] == REF_BOOK) & (odds["market"] == "1x2")].copy()
    odds["_key5"] = list(zip(odds["source"], odds["div"], odds["date"],
                              odds["home_team_raw"], odds["away_team_raw"]))
    odds = odds.sort_values("closing").drop_duplicates(subset=["_key5", "side"], keep="last")
    omap = {}
    for k5, side, value in zip(odds["_key5"], odds["side"], odds["value"]):
        omap.setdefault(k5, {})[side] = value

    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    matched_ok["_key5"] = list(zip(matched_ok["source"], matched_ok["div"], matched_ok["date"],
                                    matched_ok["home_team_raw"], matched_ok["away_team_raw"]))
    fx_to_key5 = dict(zip(matched_ok["fixture_id"], matched_ok["_key5"]))

    preds["prediction"] = preds["prediction_json"].map(json.loads)

    rows = []
    for r in preds.itertuples(index=False):
        o = omap.get(fx_to_key5.get(r.fixture_id))
        if not o or any(o.get(s) is None for s in ("H", "D", "A")):
            continue
        probs = r.prediction.get("vencedor", {}).get("probabilidades", {})
        ph, pd_, pa = probs.get(r.home_team), probs.get("Empate"), probs.get(r.away_team)
        if None in (ph, pd_, pa):
            continue
        model_p = np.array([ph, pd_, pa], dtype=float) / 100.0
        model_p = model_p / model_p.sum()
        oh, od, oa = float(o["H"]), float(o["D"]), float(o["A"])
        implied = np.array([1 / oh, 1 / od, 1 / oa])
        overround = implied.sum()
        try:
            mkt_p = np.array(shin_devig([oh, od, oa]), dtype=float)
        except Exception:
            mkt_p = np.array(proportional_devig([oh, od, oa]), dtype=float)
        actual = 0 if r.home_score > r.away_score else (2 if r.away_score > r.home_score else 1)
        rows.append(dict(tournament=r.tournament, overround=overround,
                          mp0=model_p[0], mp1=model_p[1], mp2=model_p[2],
                          kp0=mkt_p[0], kp1=mkt_p[1], kp2=mkt_p[2],
                          oh=oh, od=od, oa=oa, actual=actual))

    df = pd.DataFrame(rows)
    print(f"\nPartidas com previsao + odd 1x2 completa: {len(df)}")

    out_rows = []
    for label, sub in [("TODOS", df)] + [(t, g) for t, g in df.groupby("tournament")]:
        mp = sub[["mp0", "mp1", "mp2"]].to_numpy()
        kp = sub[["kp0", "kp1", "kp2"]].to_numpy()
        act = sub["actual"].to_numpy()
        n = len(sub)

        ll_m, ll_k = log_loss_multi(mp, act), log_loss_multi(kp, act)
        br_m, br_k = brier_multi(mp, act), brier_multi(kp, act)
        onehot = np.zeros_like(mp); onehot[np.arange(n), act] = 1.0
        ece_m = ece(mp.ravel(), onehot.ravel())
        ece_k = ece(kp.ravel(), onehot.ravel())
        vig = float(sub["overround"].mean())
        vig_pct = (vig - 1.0) * 100

        # ROI esperado de um apostador SEM edge, dado o vig (aposta 1u sempre):
        roi_sem_edge = -(1.0 - 1.0 / vig) * 100

        # piso de ruido: SE do ROI do pick do modelo (argmax)
        pick = mp.argmax(axis=1)
        odds_arr = sub[["oh", "od", "oa"]].to_numpy()
        odd_taken = odds_arr[np.arange(n), pick]
        won = pick == act
        net = np.where(won, odd_taken - 1.0, -1.0)
        roi_obs = 100.0 * net.mean()
        se_roi = 100.0 * net.std(ddof=1) / np.sqrt(n)

        # acuracia argmax modelo vs argmax mercado
        acc_m = float((mp.argmax(axis=1) == act).mean() * 100)
        acc_k = float((kp.argmax(axis=1) == act).mean() * 100)

        print(f"\n--- {label} (N={n}) ---")
        print(f"  Vig medio (overround): {vig:.4f}  ->  {vig_pct:+.2f}%   "
              f"| ROI esperado SEM edge algum: {roi_sem_edge:+.2f}%")
        print(f"  log-loss  modelo={ll_m:.4f}  mercado(de-vig)={ll_k:.4f}  "
              f"diff={ll_m - ll_k:+.4f}  ({'MODELO MELHOR' if ll_m < ll_k else 'MERCADO MELHOR'})")
        print(f"  Brier     modelo={br_m:.4f}  mercado={br_k:.4f}  diff={br_m - br_k:+.4f}")
        print(f"  ECE       modelo={ece_m:.4f}  mercado={ece_k:.4f}")
        print(f"  Acuracia  modelo={acc_m:.1f}%  mercado={acc_k:.1f}%")
        print(f"  ROI observado (pick modelo) = {roi_obs:+.2f}%  | erro padrao = +-{se_roi:.2f}pp "
              f"| IC95% ~ [{roi_obs - 1.96*se_roi:+.2f}%, {roi_obs + 1.96*se_roi:+.2f}%]")
        print(f"  >> Distancia do ROI observado ao ROI-sem-edge: "
              f"{(roi_obs - roi_sem_edge)/se_roi:+.2f} desvios padrao")

        out_rows.append(dict(recorte=label, n=n, vig_pct=round(vig_pct, 3),
                              roi_esperado_sem_edge=round(roi_sem_edge, 3),
                              roi_observado=round(roi_obs, 3), se_roi=round(se_roi, 3),
                              logloss_modelo=round(ll_m, 4), logloss_mercado=round(ll_k, 4),
                              brier_modelo=round(br_m, 4), brier_mercado=round(br_k, 4),
                              ece_modelo=round(ece_m, 4), ece_mercado=round(ece_k, 4),
                              acc_modelo=round(acc_m, 2), acc_mercado=round(acc_k, 2)))

    pd.DataFrame(out_rows).to_csv(OUT, index=False)
    print(f"\nSalvo: {OUT}")

    # --- quanto N seria preciso pra detectar um edge de 2%? ---
    net_all = None
    mp = df[["mp0", "mp1", "mp2"]].to_numpy(); act = df["actual"].to_numpy()
    pick = mp.argmax(axis=1); oarr = df[["oh", "od", "oa"]].to_numpy()
    odd_taken = oarr[np.arange(len(df)), pick]
    net_all = np.where(pick == act, odd_taken - 1.0, -1.0)
    sd = net_all.std(ddof=1)
    for edge in (0.02, 0.05):
        n_req = (2.8 * sd / edge) ** 2  # ~80% poder, alpha=0.05 bilateral
        print(f"\nPara detectar edge de {edge*100:.0f}% com 80% de poder: N ~ {n_req:,.0f} apostas "
              f"(temos {len(df)})")


if __name__ == "__main__":
    main()
