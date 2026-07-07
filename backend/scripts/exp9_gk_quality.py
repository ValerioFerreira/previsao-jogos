#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp9_gk_quality.py — Hipótese emergente: qualidade do GOLEIRO adversário
================================================================================
O modelo de goleador (produção) usa opp_gc (gols concedidos do time). Hipótese: a forma
recente do GOLEIRO adversário (rating) carrega sinal ADICIONAL para P(atacante marca) —
um bom goleiro reduz a conversão além da defesa geral do time.
Teste: adiciona opp_gk_rating (rating recente do goleiro do adversário, point-in-time) ao
conjunto de features do scorer e mede o ganho incremental de AUC/LogLoss sob CV temporal.
Gate §6. Se passar, vale rebuildar o scorer com essa feature.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, log_loss
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.build_scorer_model import load_from_cache, team_defense, build_features, FEATS


def gk_ratings():
    """Rating recente do goleiro por (time, data), point-in-time."""
    from app.db.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        rows = c.execute(text("SELECT raw FROM match_detail_cache")).fetchall()
    gk = []
    for (raw,) in rows:
        try: d = json.loads(raw)
        except Exception: continue
        date = ((d.get("fixture") or {}).get("date") or "")[:10]
        if not (date and d.get("players")): continue
        for pb in d.get("players", []):
            tid = (pb.get("team") or {}).get("id")
            for p in pb.get("players", []):
                g = (p.get("statistics") or [{}])[0].get("games") or {}
                if g.get("position") == "G" and (g.get("minutes") or 0) >= 1:
                    try: rt = float(g.get("rating"))
                    except (TypeError, ValueError): rt = np.nan
                    gk.append(dict(date=date, team_id=tid, gk_rating=rt)); break
    g = pd.DataFrame(gk).dropna(subset=["gk_rating"]).drop_duplicates(["date", "team_id"]).sort_values(["team_id", "date"])
    glob = g["gk_rating"].mean()
    g["gk_form"] = g.groupby("team_id")["gk_rating"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    g["gk_form"] = g["gk_form"].fillna(glob)
    return g[["date", "team_id", "gk_form"]], glob


def main():
    pg, matches = load_from_cache()
    matches, glob_gc = team_defense(matches)
    df, gs, gr, glob_gc = build_features(pg, matches, glob_gc)
    gk, glob_gk = gk_ratings()
    o = gk.rename(columns={"team_id": "opp_id", "gk_form": "opp_gk_form"})
    df = df.merge(o, on=["date", "opp_id"], how="left")
    df["opp_gk_form"] = df["opp_gk_form"].fillna(glob_gk)
    print(f"player-games: {len(df)} | com opp_gk_form: {int(df.opp_gk_form.notna().sum())}", flush=True)

    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    base = FEATS; ext = FEATS + ["opp_gk_form"]
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
    R = pd.DataFrame(rows)
    print("\n=== Scorer: base vs base+opp_gk_form ===")
    print(R.to_string(index=False))
    dll = (R.ll_ext - R.ll_base).mean(); dauc = (R.auc_ext - R.auc_base).mean()
    v = "APROVADO" if (dll < 0 and int((R.ll_ext < R.ll_base).sum()) >= len(R) - 1) else "REPROVADO"
    print(f"\n>> dAUC {dauc:+.4f} | dLL {dll:+.4f} (melhora {int((R.ll_ext<R.ll_base).sum())}/{len(R)}) | VEREDITO: {v}")


if __name__ == "__main__":
    main()
