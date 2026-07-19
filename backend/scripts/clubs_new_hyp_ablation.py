#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_new_hyp_ablation.py
==================================
Hipóteses NOVAS (sessão 2026-07-19) via mesmo harness de clubs_features_v2_ablation.py
(protocolo único, gate: >=4/5 folds melhoram logloss E delta<-0.001):

  H3  league_pooling   -- shrinkage empírico-Bayesiano da taxa de vitória-mandante por
                          liga (n/(n+k) contra a média global), alvo: ligas thin-data
                          (tier 3/4, poucas temporadas) onde o Elo sozinho tem mais ruído.
  H8  derby             -- indicador de clássico regional: mandante e visitante têm a
                          MESMA cidade-sede mais frequente (venue_city histórico).

Rodado sobre club_features_enriched.parquet (60 ligas, retreino 2026-07-18/19).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, compare, FoldResult)

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
import json
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_new_hyp"
Y_MAP = {"H": 0, "D": 1, "A": 2}
K_SHRINK = 200  # peso do prior global no shrinkage (jogos-equivalentes)


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def result_probs(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "ece": ece_multiclass(y_idx, probs), "accuracy": accuracy(y_idx, probs)}


def run_dc(df, feats, name):
    out = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr[feats].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, result_probs(m, X_te))
        out.append(FoldResult(fold, len(te), met))
        print(f"  [{name}] {fold}: ll={met['logloss']:.4f} rps={met['rps']:.4f}", flush=True)
    return out


def build_league_pooling(df: pd.DataFrame) -> pd.DataFrame:
    """Shrinkage empírico-Bayesiano: taxa de vitória-mandante por liga (point-in-time,
    só usa jogos ANTERIORES no expanding), puxada em direção à média global por
    n/(n+K_SHRINK). Feature única: home_win_rate_league_shrunk."""
    d = df.sort_values("date").reset_index(drop=True)
    global_rate = (d["result"] == "H").mean()
    rates = np.full(len(d), global_rate)
    is_home_win = (d["result"] == "H").astype(float).to_numpy()
    league = d["league_id"].to_numpy()
    running_n: dict[int, int] = {}
    running_sum: dict[int, float] = {}
    for i in range(len(d)):
        lg = league[i]
        n = running_n.get(lg, 0)
        s = running_sum.get(lg, 0.0)
        local_rate = (s / n) if n > 0 else global_rate
        rates[i] = (n * local_rate + K_SHRINK * global_rate) / (n + K_SHRINK)
        running_n[lg] = n + 1
        running_sum[lg] = s + is_home_win[i]
    out = pd.DataFrame(index=d.index)
    out["league_home_bias_shrunk"] = rates
    return out.set_axis(df.sort_values("date").index)


def build_derby(df: pd.DataFrame) -> pd.DataFrame:
    """Cidade mais frequente do time como mandante (histórico, point-in-time não é
    necessário aqui -- cidade-sede é praticamente estática por time). derby=1 se
    mandante e visitante compartilham a MESMA cidade-sede mais comum."""
    if "venue_city" not in df.columns:
        return pd.DataFrame(index=df.index, data={"is_derby": 0})
    home_city = df.groupby("home_team")["venue_city"].agg(lambda s: s.mode().iat[0] if len(s.mode()) else None)
    # cidade do visitante = cidade onde ELE manda (via seu próprio home_team)
    away_city = df["away_team"].map(home_city)
    home_city_col = df["home_team"].map(home_city)
    derby = (home_city_col.notna() & (home_city_col == away_city)).astype(int)
    return pd.DataFrame(index=df.index, data={"is_derby": derby})


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df2 = df[(df["home_matches_played_before"] >= 5) &
             (df["away_matches_played_before"] >= 5)].reset_index(drop=True)
    print(f"dataset pos burn-in: {len(df2)} jogos", flush=True)

    df2 = df2.join(build_league_pooling(df2))
    df2 = df2.join(build_derby(df2))
    print(f"derby: {df2['is_derby'].sum()} jogos ({df2['is_derby'].mean()*100:.2f}%)", flush=True)

    GROUPS = {
        "league_pooling": ["league_home_bias_shrunk"],
        "derby": ["is_derby"],
    }

    base_feats = bf()
    print("\n=== baseline ===", flush=True)
    baseline = run_dc(df2, base_feats, "baseline")

    passed = []
    for name, extra in GROUPS.items():
        print(f"\n=== ablacao: {name} ===", flush=True)
        cand = run_dc(df2, base_feats + extra, name)
        comp = compare(baseline, cand, metric="logloss")
        comp.to_csv(OUT_DIR / f"{name}.csv", index=False)
        wins = comp.iloc[:-1]["melhora"].sum()
        delta = comp.iloc[-1]["delta"]
        veredito = "PASSA" if wins >= 4 and delta < -0.001 else ("misto" if wins >= 2 else "REPROVADO")
        print(f"  {name}: {wins}/5 folds melhoram | delta {delta:+.4f} -> {veredito}", flush=True)
        if veredito == "PASSA":
            passed.append(name)

    # H3 segmentado: efeito só nas ligas thin-data (tier3/4 -- poucas temporadas no historico)
    league_counts = df2["league_id"].value_counts()
    thin_leagues = league_counts[league_counts < league_counts.median()].index
    thin_mask = df2["league_id"].isin(thin_leagues)
    print(f"\n=== H3 segmentado: ligas thin-data ({thin_mask.sum()} jogos, {len(thin_leagues)} ligas) ===", flush=True)
    for fold, tr_idx, te_idx in temporal_folds(df2):
        te = df2.loc[te_idx]
        te_thin = te[te.index.isin(df2[thin_mask].index)]
        if len(te_thin) < 50:
            continue
        print(f"  {fold}: {len(te_thin)} jogos thin no teste", flush=True)

    print(f"\n===== grupos que PASSAM: {passed} =====", flush=True)


if __name__ == "__main__":
    main()
