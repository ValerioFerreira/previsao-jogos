#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp6_xg_market.py
================================
Hipótese H6: xG como MERCADO PRÓPRIO (não feature -- já testado como feature em
Fase4/xg_feature, delta~0, sem sinal pro RESULTADO). Aqui é diferente: usar
home_cur_sb_xg/away_cur_sb_xg (xG REAL do jogo, já no box-score) como ALVO de uma
cascata O/U, arquitetura idêntica à de escanteios (CornersNB) -- xG total
arredondado pro grid inteiro mais próximo (crua o suficiente pra Poisson/NB,
o mercado de aposta seria em linhas .5 como qualquer O/U de contagem).

Cobertura xG em clubes: ~14% dos jogos (só ligas/temporadas com box-score avançado
da api-football) -- avalia se dá amostra suficiente pra um mercado com confianca.
"""
import sys, json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corners_nb_model import CornersNB
from research_clubs.protocol import temporal_folds, pmf_logloss, pmf_mae, coverage80

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]
OUT_DIR = ROOT / "data" / "reports" / "clubs_new_hyp"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    d = df.dropna(subset=["home_cur_sb_xg", "away_cur_sb_xg"]).copy()
    print(f"jogos com xG do jogo (alvo): {len(d)} / {len(df)} ({len(d)/len(df)*100:.1f}%)", flush=True)
    if len(d) < 2000:
        print("AMOSTRA INSUFICIENTE pra avaliação com 5 folds temporais confiaveis -- abortando com aviso.")
        return

    d["xg_home_round"] = d["home_cur_sb_xg"].round().clip(0, 8).astype(int)
    d["xg_away_round"] = d["away_cur_sb_xg"].round().clip(0, 8).astype(int)
    d = d.reset_index(drop=True)

    rows = []
    for fold, tr_idx, te_idx in temporal_folds(d):
        tr, te = d.loc[tr_idx], d.loc[te_idx]
        if len(te) < 80:
            continue
        Xtr = tr[BASE_FEATS].fillna(tr[BASE_FEATS].median(numeric_only=True))
        Xte = te[BASE_FEATS].fillna(tr[BASE_FEATS].median(numeric_only=True))
        m = CornersNB(feats=BASE_FEATS, max_corners=8)
        m.fit(Xtr, tr["xg_home_round"].to_numpy(), tr["xg_away_round"].to_numpy())
        dist = m.predict_distributions(Xte)
        y_total = (te["xg_home_round"] + te["xg_away_round"]).to_numpy()
        ll = pmf_logloss(y_total, dist["total"])
        mae = pmf_mae(y_total, dist["total"])
        cov = coverage80(y_total, dist["total"])
        print(f"  [{fold}] n={len(te)} logloss={ll:.4f} mae={mae:.3f} cobertura80={cov:.3f}", flush=True)
        rows.append({"fold": fold, "n": len(te), "logloss": ll, "mae": mae, "cobertura80": cov})

    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR / "h6_xg_market.csv", index=False)
    print(f"\n>> media: logloss={R.logloss.mean():.4f} mae={R.mae.mean():.3f} cobertura80={R.cobertura80.mean():.3f}")
    print(">> VEREDITO: viavel como mercado (cobertura80 perto de 0.80 e MAE razoavel) SE amostra >=2000; "
          "senao, aguardar mais coleta com box-score xG antes de servir em producao.")


if __name__ == "__main__":
    main()
