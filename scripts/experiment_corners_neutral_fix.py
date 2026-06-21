#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_corners_neutral_fix.py
=========================================
Item 2 / Fase B — testa se features de INTERACAO DE MANDO reduzem o residuo de
escanteios em campo neutro (verificado real, ~2.4 sigma). As interacoes sao
deterministicas a partir de colunas existentes (sem mexer no build_final_dataset).

Compara, em split temporal, a CornersNB atual (full_feats) vs aumentada
(full_feats + interacoes), medindo: residuo em neutro (mandante/visitante) e
log-loss/ECE no total. Gate: so promove se reduzir o residuo SEM piorar calibracao.
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("api").resolve()))
sys.path.insert(0, "scripts")
from corners_nb_model import CornersNB
import compare_corners as cc

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FULL = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))["full_feats"]
INTER = ["rha_x_elo_winprob", "rha_x_corner_diff", "rha_x_shot_diff", "rha_x_elo_diff"]


def add_interactions(df):
    """Interacoes de mando (real_home_advantage = 1-neutral) com os drivers de
    assimetria de escanteios. Deterministicas a partir de colunas existentes."""
    df = df.copy()
    rha = (1 - df["neutral"].fillna(0)).astype(float)
    df["rha_x_elo_winprob"] = rha * df["elo_home_winprob"].fillna(0.5)
    df["rha_x_corner_diff"] = rha * (df.get("home_sb_corners_l5", 0).fillna(0) - df.get("away_sb_corners_l5", 0).fillna(0))
    df["rha_x_shot_diff"] = rha * (df.get("home_sb_shots_l5", 0).fillna(0) - df.get("away_sb_shots_l5", 0).fillna(0))
    df["rha_x_elo_diff"] = rha * df["elo_diff"].fillna(0)
    return df


def ece_over(prob, actual, line):
    return cc.expected_calibration_error((actual > line).astype(int), prob[:, int(line) + 1:].sum(axis=1))


def eval_model(feats, tr, te, M=25):
    m = CornersNB(max_corners=M, feats=feats)
    m.fit(tr[feats], tr["home_cur_sb_corners"].astype(int).values, tr["away_cur_sb_corners"].astype(int).values)
    d = m.predict_distributions(te[feats])
    yh, ya = te["home_cur_sb_corners"].astype(int).values, te["away_cur_sb_corners"].astype(int).values
    yt = yh + ya
    neu = te["neutral"].fillna(0).astype(int).values == 1
    res_h = yh - (d["home"] @ np.arange(M + 1))
    res_a = ya - (d["away"] @ np.arange(M + 1))
    ll_t = -np.mean(np.log(d["total"][np.arange(len(te)), np.clip(yt, 0, 2 * M)] + 1e-15))
    return {
        "res_h_neutro": float(res_h[neu].mean()), "res_a_neutro": float(res_a[neu].mean()),
        "ll_total": float(ll_t), "ece_total": float(ece_over(d["total"], yt, 8.5)),
        "ll_home": float(-np.mean(np.log(d["home"][np.arange(len(te)), np.clip(yh, 0, M)] + 1e-15))),
        "ece_home": float(ece_over(d["home"], yh, 4.5)),
    }


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_corners", "away_cur_sb_corners"]).sort_values("date").reset_index(drop=True)
    adv = add_interactions(adv)
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr, te = adv[adv["date"] <= cut].reset_index(drop=True), adv[adv["date"] > cut].reset_index(drop=True)
    print(f"treino {len(tr)} | teste {len(te)} | neutros no teste: {int((te['neutral']==1).sum())}")

    base = eval_model(FULL, tr, te)
    aug = eval_model(FULL + INTER, tr, te)

    print(f"\n{'metrica':16s} {'baseline':>12s} {'+interacoes':>12s}")
    for k in ["res_h_neutro", "res_a_neutro", "ll_home", "ece_home", "ll_total", "ece_total"]:
        b, a = base[k], aug[k]
        fmt = (lambda x: f"{x:.4f}") if "ll" in k else (lambda x: f"{x:+.3f}" if "res" in k else f"{x:.2%}")
        print(f"{k:16s} {fmt(b):>12s} {fmt(a):>12s}")

    # veredito
    res_better = (abs(aug["res_h_neutro"]) < abs(base["res_h_neutro"])) and (abs(aug["res_a_neutro"]) < abs(base["res_a_neutro"]))
    cal_ok = aug["ece_total"] <= base["ece_total"] + 0.002 and aug["ll_total"] <= base["ll_total"] + 0.002
    print(f"\nResiduo neutro reduzido: {res_better} | calibracao mantida/melhor: {cal_ok}")
    print("VEREDITO:", "PROMOVER (interacoes ajudam)" if (res_better and cal_ok) else "NAO promover (sem ganho liquido)")


if __name__ == "__main__":
    main()
