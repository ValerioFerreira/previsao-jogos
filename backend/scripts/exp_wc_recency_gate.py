#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp_wc_recency_gate.py
================================
GATE HONESTO (não a triagem rápida do exp_wc_recency.py) para a feature candidata
"forma da própria selecao nos jogos ANTERIORES da mesma WC2026" (in_wc_prior_avg),
ativa só a partir do jogo 2 da selecao no torneio -- conforme recomendação do relatorio
`data/reports/wc2026_recency_experiment.md`.

Protocolo (DOCUMENTACAO_CENTRAL.md §6):
  - Mesmo regressor de media (GBR) + mesma distribuicao (NB) da produção (nao proxy).
  - Mesmas features base da produção (META["base_feats"]) + a feature candidata.
  - CV temporal expanding, point-in-time (a feature so usa jogos ANTERIORES da propria
    selecao na WC2026, e so existe pos game_index>=2; fora disso fica NaN -> imputada
    pela mesma pipeline (SimpleImputer median) que ja e usada em produção).
  - Comparado contra a PRODUÇÃO REAL (GBR+NB, mesmo pipeline), avaliado SEGMENTADO no
    grupo onde a feature é ativa (WC2026, jogo>=2 da própria selecao) -- fora desse
    segmento a feature e irrelevante por construção.
  - Metrica: log-loss de contagem (PMF) + ECE da linha O/U por equipe + MAE.
  - Varios cortes temporais sucessivos (uma dobra por data distinta de jogo da WC2026
    com jogo>=2), nao um unico split.

Uso: cd backend && .venv/Scripts/python scripts/exp_wc_recency_gate.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import market_models_experiments as M

OUT = M.ROOT / "data" / "reports" / "wc2026_recency_gate.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

MARKETS = [
    # nome, coluna_home, coluna_away, grade, linha_por_time
    ("escanteios", "home_cur_sb_corners", "away_cur_sb_corners", 25, 4.75),
    ("chutes", "home_cur_sb_shots", "away_cur_sb_shots", 55, 11.25),
]


def build_wc_recency_columns(adv: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time: para cada jogo da WC2026, calcula o game_index da propria
    selecao no torneio e a media dos jogos ANTERIORES da mesma WC2026 (NaN se
    game_index<2 ou fora da WC2026). Nunca olha o proprio jogo ou jogos futuros."""
    adv = adv.sort_values("date").reset_index(drop=True).copy()
    is_wc = (adv["tournament"] == "FIFA World Cup") & (adv["date"].dt.year == 2026)

    hist: dict[str, dict[str, list[float]]] = {}
    for col in ("home_wc_game_index", "away_wc_game_index",
                "home_in_wc_prior_corners", "away_in_wc_prior_corners",
                "home_in_wc_prior_shots", "away_in_wc_prior_shots"):
        adv[col] = np.nan

    for i, row in adv.iterrows():
        if not is_wc.iloc[i]:
            continue
        for side, team, ccol, scol, idxcol, priorcol_c, priorcol_s in [
            ("home", row["home_team"], "home_cur_sb_corners", "home_cur_sb_shots",
             "home_wc_game_index", "home_in_wc_prior_corners", "home_in_wc_prior_shots"),
            ("away", row["away_team"], "away_cur_sb_corners", "away_cur_sb_shots",
             "away_wc_game_index", "away_in_wc_prior_corners", "away_in_wc_prior_shots"),
        ]:
            h = hist.setdefault(team, {"corners": [], "shots": []})
            game_index = len(h["corners"]) + 1
            adv.at[i, idxcol] = game_index
            if game_index >= 2:
                if h["corners"]:
                    adv.at[i, priorcol_c] = float(np.mean(h["corners"]))
                if h["shots"]:
                    adv.at[i, priorcol_s] = float(np.mean(h["shots"]))
            # atualiza o historico DEPOIS de ler (point-in-time correto)
            cv, sv = row[ccol], row[scol]
            if pd.notna(cv):
                h["corners"].append(float(cv))
            if pd.notna(sv):
                h["shots"].append(float(sv))
    return adv


def run_market(adv, market, home_col, away_col, grade, line_side, min_test=2):
    rows = []
    for side, col, idxcol, priorcol in [
        ("mandante", home_col, "home_wc_game_index",
         "home_in_wc_prior_corners" if market == "escanteios" else "home_in_wc_prior_shots"),
        ("visitante", away_col, "away_wc_game_index",
         "away_in_wc_prior_corners" if market == "escanteios" else "away_in_wc_prior_shots"),
    ]:
        eval_pool = adv.dropna(subset=[col]).copy()
        eval_pool = eval_pool[eval_pool[idxcol] >= 2]
        if eval_pool.empty:
            continue
        fold_dates = sorted(eval_pool["date"].unique())
        for d in fold_dates:
            test = eval_pool[eval_pool["date"] == d]
            if len(test) < min_test:
                continue
            train = adv[(adv["date"] < d) & adv[col].notna()]
            if len(train) < 300:
                continue
            Xtr_base, ytr = train[M.FEATS], train[col].astype(int).values
            Xte_base = test[M.FEATS]
            Xtr_aug = train[M.FEATS + [priorcol]]
            Xte_aug = test[M.FEATS + [priorcol]]

            P_base, lam_base = M.build_pmf("gbr", "nb", Xtr_base, ytr, Xte_base, grade)
            P_aug, lam_aug = M.build_pmf("gbr", "nb", Xtr_aug, ytr, Xte_aug, grade)
            y = test[col].astype(int).values

            ll_base = M.count_logloss(y, P_base)
            ll_aug = M.count_logloss(y, P_aug)
            over_base = P_base[:, int(np.floor(line_side)) + 1:].sum(axis=1)
            over_aug = P_aug[:, int(np.floor(line_side)) + 1:].sum(axis=1)
            ece_base = M.ece_ou(y, over_base, line_side)
            ece_aug = M.ece_ou(y, over_aug, line_side)
            mae_base = float(np.mean(np.abs(y - lam_base)))
            mae_aug = float(np.mean(np.abs(y - lam_aug)))

            rows.append({
                "mercado": market, "lado": side, "fold_date": str(pd.Timestamp(d).date()),
                "n_test": len(test), "n_train": len(train),
                "game_index_media": float(test[idxcol].mean()),
                "ll_base": ll_base, "ll_aug": ll_aug, "d_ll": ll_aug - ll_base,
                "ece_base": ece_base, "ece_aug": ece_aug, "d_ece": ece_aug - ece_base,
                "mae_base": mae_base, "mae_aug": mae_aug, "d_mae": mae_aug - mae_base,
            })
    return rows


def summarize(df):
    print(f"\n{'='*78}")
    for (mkt, lado), g in df.groupby(["mercado", "lado"]):
        n_folds = len(g)
        n_test_total = g["n_test"].sum()
        wins_ll = (g["d_ll"] < 0).sum()
        wins_ece = (g["d_ece"] < 0).sum()
        wins_mae = (g["d_mae"] < 0).sum()
        # medias ponderadas por n_test (mais justo que media simples de fold)
        w = g["n_test"].values
        mean_d_ll = float(np.average(g["d_ll"], weights=w))
        mean_d_ece = float(np.average(g["d_ece"], weights=w))
        mean_d_mae = float(np.average(g["d_mae"], weights=w))
        print(f"[{mkt}/{lado}] {n_folds} dobras, N total={n_test_total}")
        print(f"  ΔLogLoss (aug-base) medio ponderado = {mean_d_ll:+.4f}  "
              f"(aug melhora em {wins_ll}/{n_folds} dobras)")
        print(f"  ΔECE     (aug-base) medio ponderado = {mean_d_ece:+.4f}  "
              f"(aug melhora em {wins_ece}/{n_folds} dobras)")
        print(f"  ΔMAE     (aug-base) medio ponderado = {mean_d_mae:+.4f}  "
              f"(aug melhora em {wins_mae}/{n_folds} dobras)")
        veredito = "PROMOVER" if (mean_d_ll < -0.001 and mean_d_ece <= 0.001 and wins_ll >= n_folds * 0.6) else "NAO PROMOVER"
        print(f"  >> Veredito preliminar: {veredito}")


def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy()
    adv = build_wc_recency_columns(adv)

    n_wc = ((adv["tournament"] == "FIFA World Cup") & (adv["date"].dt.year == 2026)).sum()
    print(f"WC2026 com box-score completo no dataset de treino: {n_wc} linhas-time (jogo x lado)")

    all_rows = []
    for market, hcol, acol, grade, line_side in MARKETS:
        rows = run_market(adv, market, hcol, acol, grade, line_side)
        all_rows.extend(rows)
        print(f"[{market}] {len(rows)} dobras avaliadas", flush=True)

    res = pd.DataFrame(all_rows)
    res.to_csv(OUT, index=False)
    print(f"\nSalvo -> {OUT}")
    summarize(res)


if __name__ == "__main__":
    main()
