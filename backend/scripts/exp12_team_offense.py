#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp12_team_offense.py — Hipótese: força ofensiva do PRÓPRIO time no scorer
==================================================================================
O scorer usa opp_gc (defesa do adversário). Hipótese: a força ofensiva do PRÓPRIO time do
jogador (gols marcados recentes) dá mais chances ao atacante — sinal ortogonal ao opp_gc.
Testa `team_gf` = média móvel de gols marcados pelo time (point-in-time). Gate §6.
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, log_loss
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.build_scorer_model import load_from_cache, team_defense, build_features, FEATS


def main():
    pg, matches = load_from_cache()
    matches, glob_gc = team_defense(matches)
    df, gs, gr, glob_gc = build_features(pg, matches, glob_gc)
    # gols marcados pelo time = gc da linha-parceira (mesmo `key`, outro team_id)
    partner = matches[["key", "team_id", "gc"]].rename(columns={"team_id": "pteam", "gc": "team_gf_raw"})
    m2 = matches.merge(partner, on="key")
    m2 = m2[m2.team_id != m2.pteam].sort_values(["team_id", "date"])
    m2["team_gf"] = m2.groupby("team_id")["team_gf_raw"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    glob = m2["team_gf_raw"].mean(); m2["team_gf"] = m2["team_gf"].fillna(glob)
    off = m2[["date", "team_id", "team_gf"]].drop_duplicates(["date", "team_id"])
    df = df.merge(off, on=["date", "team_id"], how="left"); df["team_gf"] = df["team_gf"].fillna(glob)
    print(f"player-games: {len(df)} | team_gf médio {df.team_gf.mean():.2f}", flush=True)

    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    base = FEATS; ext = FEATS + ["team_gf"]
    cuts = np.linspace(0.5, 0.85, 4); rows = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300: continue
        mb = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(tr[base], tr.scored)
        mf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(tr[ext], tr.scored)
        pb = mb.predict_proba(te[base])[:, 1]; pf = mf.predict_proba(te[ext])[:, 1]
        rows.append(dict(fold=round(c, 2), auc_base=roc_auc_score(te.scored, pb), auc_ext=roc_auc_score(te.scored, pf),
                         ll_base=log_loss(te.scored, pb, labels=[0, 1]), ll_ext=log_loss(te.scored, pf, labels=[0, 1])))
    R = pd.DataFrame(rows); print(R.to_string(index=False))
    dll = (R.ll_ext - R.ll_base).mean(); dauc = (R.auc_ext - R.auc_base).mean()
    v = "APROVADO" if (dll < 0 and int((R.ll_ext < R.ll_base).sum()) >= len(R) - 1) else "REPROVADO"
    print(f">> dAUC {dauc:+.4f} | dLL {dll:+.4f} (melhora {int((R.ll_ext<R.ll_base).sum())}/{len(R)}) | VEREDITO: {v}")


if __name__ == "__main__":
    main()
