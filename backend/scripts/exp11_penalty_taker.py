#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp11_penalty_taker.py — Hipótese: cobrador de pênalti no modelo de goleador
====================================================================================
Um cobrador designado tem mais oportunidades de marcar (pênaltis convertem ~75%). O scorer
não sabe quem cobra. Testa adicionar `pk_rate` = taxa histórica de cobrança de pênalti do
jogador (point-in-time, dos eventos do cache) às features do scorer. Gate §6.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, log_loss
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.build_scorer_model import load_from_cache, team_defense, build_features, FEATS


def pk_events():
    """(date, player_id) de quem COBROU pênalti (convertido ou perdido)."""
    from app.db.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        rows = c.execute(text("SELECT raw FROM match_detail_cache")).fetchall()
    pk = []
    for (raw,) in rows:
        try: d = json.loads(raw)
        except Exception: continue
        date = ((d.get("fixture") or {}).get("date") or "")[:10]
        for e in (d.get("events") or []):
            det = (e.get("detail") or ""); typ = (e.get("type") or "")
            if "Penalty" in det and typ in ("Goal",) or typ == "Missed Penalty":
                pid = (e.get("player") or {}).get("id")
                if date and pid: pk.append((date, pid))
    return pd.DataFrame(pk, columns=["date", "player_id"]).drop_duplicates()


def main():
    pg, matches = load_from_cache()
    matches, glob_gc = team_defense(matches)
    df, gs, gr, glob_gc = build_features(pg, matches, glob_gc)
    pk = pk_events()
    took = pk.assign(took=1)
    df = df.merge(took, on=["date", "player_id"], how="left")
    df["took"] = df["took"].fillna(0)
    df = df.sort_values(["player_id", "date"]).reset_index(drop=True)
    # taxa de cobrança point-in-time (cumulativa, shift)
    df["pk_rate"] = df.groupby("player_id")["took"].transform(lambda s: s.shift(1).expanding().mean()).fillna(0.0)
    print(f"player-games: {len(df)} | cobranças de pênalti registradas: {int(pk.shape[0])} | "
          f"jogadores que já cobraram: {pk.player_id.nunique()}", flush=True)

    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    base = FEATS; ext = FEATS + ["pk_rate"]
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
