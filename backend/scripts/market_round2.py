#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/market_round2.py
================================
Rodada 2: (A) testa se a SEVERIDADE DO ÁRBITRO melhora a previsão de CARTÕES
(base vs base+árbitro), e (B) confirma com CV TEMPORAL (3 folds expanding) os
vencedores da rodada 1 (chutes/escanteios c/ Generalized-Poisson; gols c/ HistGBM+NB).
Salva backend/data/reports/market_round2_results.csv.
"""
from __future__ import annotations
import warnings, json
from pathlib import Path
import numpy as np, pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "built" / "referee_features.csv"
OUT = ROOT / "data" / "reports" / "market_round2_results.csv"

def temporal_cv(df, ch, ca, lado, feats, reg, dist, grade, line, n_folds=3):
    """CV temporal expanding: treina no passado, testa no bloco seguinte."""
    df = df.sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, n_folds)
    lls, eces = [], []
    for c in cuts:
        n = int(len(df) * c); m = int(len(df) * min(c + 0.15, 1.0))
        tr, te = df.iloc[:n], df.iloc[n:m]
        if len(te) < 30: continue
        Xtr, Xte = tr[feats], te[feats]
        if lado == "total":
            Ph, _ = M.build_pmf(reg, dist, Xtr, tr[ch].astype(int).values, Xte, grade)
            Pa, _ = M.build_pmf(reg, dist, Xtr, tr[ca].astype(int).values, Xte, grade)
            Pt = np.zeros((len(te), 2*grade+1))
            for i in range(len(te)): Pt[i] = np.convolve(Ph[i], Pa[i])
            y = te[ch].astype(int).values + te[ca].astype(int).values
            lls.append(M.count_logloss(y, Pt)); eces.append(M.ece_ou(y, Pt[:, int(line)+1:].sum(1), line))
        else:
            col = ch if lado == "mandante" else ca
            y = te[col].astype(int).values
            P, _ = M.build_pmf(reg, dist, Xtr, tr[col].astype(int).values, Xte, grade)
            lls.append(M.count_logloss(y, P)); eces.append(M.ece_ou(y, P[:, int(line)+1:].sum(1), line))
    return float(np.mean(lls)), float(np.std(lls)), float(np.mean(eces))

def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy()
    ht = pd.read_parquet(M.HALFT); adv["dkey"] = adv["date"].astype(str).str[:10]
    adv = adv.merge(ht, left_on=["dkey","home_team","away_team"], right_on=["date","home_team","away_team"], how="left", suffixes=("","_ht"))
    ref = pd.read_csv(REF); ref["dkey"] = ref["date"].astype(str).str[:10]
    adv = adv.merge(ref[["dkey","home_team","away_team","ref_strictness","ref_nmatches"]],
                    on=["dkey","home_team","away_team"], how="left")
    REFEATS = ["ref_strictness", "ref_nmatches"]
    rows = []

    # (A) ÁRBITRO em cartões: base vs base+ref (GBR + melhor dist), CV temporal
    print(">> (A) Árbitro em cartões", flush=True)
    cards = [("cartoes","home_cur_sb_cards","away_cur_sb_cards",3.5,15),
             ("cartoes_1t","home_cards_1t","away_cards_1t",1.5,12),
             ("cartoes_2t","home_cards_2t","away_cards_2t",2.5,12)]
    for mkt, ch, ca, line, grade in cards:
        sub = adv.dropna(subset=[ch, ca]).copy()
        cov_ref = sub["ref_strictness"].notna().mean()
        for lado, ln in [("mandante", line/2), ("visitante", line/2), ("total", line)]:
            for fsname, feats in [("base", M.FEATS), ("base+ref", M.FEATS + REFEATS)]:
                for dist in ["poisson", "nb", "gp"]:
                    ll, sd, ece = temporal_cv(sub, ch, ca, lado, feats, "gbr", dist, grade, ln)
                    rows.append({"bloco":"arbitro_cartoes","mercado":mkt,"lado":lado,"feature_set":fsname,
                                 "reg":"gbr","dist":dist,"cov_ref":round(cov_ref,2),
                                 "cv_logloss":ll,"cv_ll_sd":sd,"cv_ece":ece})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        print(f"  {mkt} ok", flush=True)

    # (B) confirmação CV dos vencedores da rodada 1
    print(">> (B) Confirmação CV dos vencedores", flush=True)
    winners = [
        ("gols","home_score","away_score",2.5,12,[("gbr","poisson"),("hgb_sq","nb"),("hgb_pois","nb")]),
        ("finalizacoes","home_cur_sb_shots","away_cur_sb_shots",22.5,55,[("gbr","poisson"),("gbr","nb"),("gbr","gp")]),
        ("escanteios","home_cur_sb_corners","away_cur_sb_corners",9.5,25,[("gbr","poisson"),("gbr","nb"),("gbr","gp")]),
        ("finalizacoes_gol","home_cur_sb_shots_on_target","away_cur_sb_shots_on_target",7.5,30,[("gbr","poisson"),("gbr","nb"),("gbr","gp")]),
    ]
    for mkt, ch, ca, line, grade, combos in winners:
        sub = adv.dropna(subset=[ch, ca]).copy()
        for lado, ln in [("total", line)]:
            for reg, dist in combos:
                ll, sd, ece = temporal_cv(sub, ch, ca, lado, M.FEATS, reg, dist, grade, ln)
                rows.append({"bloco":"confirma_cv","mercado":mkt,"lado":lado,"feature_set":"base",
                             "reg":reg,"dist":dist,"cv_logloss":ll,"cv_ll_sd":sd,"cv_ece":ece})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        print(f"  {mkt} ok", flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
