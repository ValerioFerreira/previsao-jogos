#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/run_experiment_history.py  --arm {full|b2016}  --csv <path>
==================================================================
Treina o Dixon-Coles (resultado/gols/BTTS/over) e a CornersNB (escanteios) sobre
o dataset de um braço, num split temporal 80/20, e avalia no test-fold. Dumpa as
métricas em scratch/experimento_historico/metrics_<arm>.json.

Os dois braços compartilham as MESMAS partidas (2016+), então o corte de data e o
test-fold são idênticos — a única diferença é o aquecimento de Elo/forma/h2h.
"""
import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, accuracy_score, mean_absolute_error, mean_squared_error

sys.path.insert(0, str(Path("api").resolve()))
sys.path.insert(0, "scripts")
from dixon_coles_model import DixonColesNBRegressor
from corners_nb_model import CornersNB
from diagnose_models import multiclass_ece, multiclass_brier_score, expected_calibration_error

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]
FULL_FEATS = META["full_feats"]


def temporal_split(df, frac=0.8):
    df = df.sort_values("date").reset_index(drop=True)
    cut = df.iloc[int(len(df) * frac)]["date"]
    return df[df["date"] <= cut].reset_index(drop=True), df[df["date"] > cut].reset_index(drop=True), cut


def eval_dixon_coles(df):
    tr, te, cut = temporal_split(df)
    dc = DixonColesNBRegressor(max_goals=12)
    dc.fit(tr[BASE_FEATS], tr["home_score"].values, tr["away_score"].values)
    pm = dc.predict_proba_markets(te[BASE_FEATS])

    # Resultado (classes [A,D,H])
    classes = ["A", "D", "H"]
    P = pm["result"]
    y = te["result"].values
    res = {
        "n_test": int(len(te)), "cutoff": str(cut.date()),
        "result_logloss": float(log_loss(y, P, labels=classes)),
        "result_acc": float(accuracy_score(y, [classes[i] for i in P.argmax(1)])),
        "result_ece": float(multiclass_ece(y, P, classes)),
        "result_brier": float(multiclass_brier_score(np.array([classes.index(v) for v in y]), P)),
    }
    # Gols total (da matriz conjunta)
    M = dc.max_goals
    joint = pm["joint"]
    td = np.zeros((len(te), 2 * M + 1))
    for x in range(M + 1):
        for yy in range(M + 1):
            td[:, x + yy] += joint[:, x, yy]
    td /= td.sum(axis=1, keepdims=True)
    actual_total = np.clip(te["total_goals"].values, 0, 2 * M).astype(int)
    e_total = td @ np.arange(2 * M + 1)
    res["gols_logloss"] = float(-np.mean(np.log(td[np.arange(len(te)), actual_total] + 1e-15)))
    res["gols_mae"] = float(mean_absolute_error(te["total_goals"].values, e_total))
    res["gols_rmse"] = float(np.sqrt(mean_squared_error(te["total_goals"].values, e_total)))
    # BTTS / Over2.5
    for name, key, col in [("btts", "btts", "btts"), ("over25", "over_2_5", "over_2_5")]:
        p = pm[key]
        yt = te[col].values.astype(int)
        res[f"{name}_logloss"] = float(log_loss(yt, p, labels=[0, 1]))
        res[f"{name}_ece"] = float(expected_calibration_error(yt, p))
        res[f"{name}_brier"] = float(np.mean((yt - p) ** 2))
    return res


def _count_ll(pmf, actual, maxc):
    a = np.clip(actual, 0, maxc).astype(int)
    return float(-np.mean(np.log(pmf[np.arange(len(actual)), a] + 1e-15)))


def eval_corners(df):
    adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]).copy()
    tr, te, cut = temporal_split(adv)
    m = CornersNB(max_corners=25, feats=FULL_FEATS).fit(
        tr[FULL_FEATS], tr["home_cur_sb_corners"].astype(int).values,
        tr["away_cur_sb_corners"].astype(int).values)
    d = m.predict_distributions(te[FULL_FEATS])
    yh = te["home_cur_sb_corners"].astype(int).values
    ya = te["away_cur_sb_corners"].astype(int).values
    yt = yh + ya
    out = {"n_test_corners": int(len(te)), "r_H": float(m.r_H_), "r_A": float(m.r_A_)}
    for nm, pmf, act, line, maxc in [("home", d["home"], yh, 4.5, 25),
                                     ("away", d["away"], ya, 3.5, 25),
                                     ("total", d["total"], yt, 8.5, 50)]:
        out[f"corners_{nm}_logloss"] = _count_ll(pmf, act, maxc)
        out[f"corners_{nm}_ece"] = float(expected_calibration_error(
            (act > line).astype(int), pmf[:, int(line) + 1:].sum(axis=1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--csv", required=True)
    a = ap.parse_args()
    print(f"[{a.arm}] carregando {a.csv}")
    df = pd.read_csv(a.csv, parse_dates=["date"], low_memory=False)
    print(f"[{a.arm}] {len(df)} linhas | rodando DC...")
    metrics = eval_dixon_coles(df)
    print(f"[{a.arm}] DC OK | rodando Corners...")
    metrics.update(eval_corners(df))
    out = Path(f"scratch/experimento_historico/metrics_{a.arm}.json")
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"[{a.arm}] metricas salvas em {out}")


if __name__ == "__main__":
    main()
