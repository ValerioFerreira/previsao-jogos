#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_player_fouls.py — VALIDACAO do prop "Jogador a cometer falta"
=========================================================================
Faltas COMETIDAS sao acao propria do jogador (nao dependem do arbitro como o cartao),
entao podem ser mais previsiveis que cartao. Valida sob CV temporal a linha >=2 faltas,
modelo vs taxa-base. Promove so se ficar no padrao do site (goleador/finalizacoes ~0.74).

Uso: python scripts/test_player_fouls.py
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
WINS = [3, 5, 10]
FEATS = ["base_fouls", "form_fouls_5", "form_fouls_10", "minutes_base", "is_home", "pos_def", "pos_mid"]


def load():
    from app.db.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        rows = c.execute(text("SELECT raw FROM match_detail_cache")).fetchall()
    pg = []
    for (raw,) in rows:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        fx = d.get("fixture") or {}
        if ((fx.get("status") or {}).get("short")) not in ("FT", "AET", "PEN"):
            continue
        date = (fx.get("date") or "")[:10]
        teams = d.get("teams") or {}
        hid = (teams.get("home") or {}).get("id")
        if not (date and d.get("players")):
            continue
        for pb in d["players"]:
            tid = (pb.get("team") or {}).get("id")
            for p in pb.get("players", []):
                pl = p.get("player") or {}; st = (p.get("statistics") or [{}])[0]; g = st.get("games") or {}
                mins = g.get("minutes")
                if mins is None:
                    continue
                fouls = (st.get("fouls") or {}).get("committed")
                pg.append(dict(date=date, player_id=pl.get("id"), team_id=tid, is_home=int(tid == hid),
                               pos=g.get("position") or "", minutes=mins or 0,
                               fouls=fouls if fouls is not None else 0,
                               fouls_na=(fouls is None)))
    pg = pd.DataFrame(pg).dropna(subset=["player_id"]).drop_duplicates(["date", "player_id", "team_id"])
    return pg.sort_values(["player_id", "date"]).reset_index(drop=True)


def build(pg):
    # cobertura de faltas (a API preenche committed so em parte dos jogos)
    cov = 1 - pg["fouls_na"].mean()
    pg = pg[(pg["minutes"] >= 1) & (~pg["fouls_na"])].copy()
    pg["ge2"] = (pg["fouls"] >= 2).astype(int)
    gf = pg["fouls"].mean(); gr = pg["ge2"].mean()
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cs = g["fouls"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri,
             "base_fouls": (cs + 5 * gf) / (npri + 5),
             "minutes_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values}
        for w in WINS:
            d[f"form_fouls_{w}"] = g["fouls"].shift(1).rolling(w, min_periods=1).mean().values
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns:
        pg[c] = F[c]
    pg["pos_def"] = (pg["pos"] == "D").astype(int)
    pg["pos_mid"] = (pg["pos"] == "M").astype(int)
    return pg.dropna(subset=FEATS + ["ge2"]).reset_index(drop=True), cov, gf


def validate(df):
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    res = []
    for c in np.linspace(0.5, 0.85, 4):
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300:
            continue
        clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(tr[FEATS], tr["ge2"])
        p = clf.predict_proba(te[FEATS])[:, 1]
        pb = (te["base_fouls"] / (te["base_fouls"] + 2.0)).clip(1e-4, 1 - 1e-4).values
        edges = np.linspace(0, 1, 11); ece = 0.0
        for b in range(10):
            mk = (p >= edges[b]) & (p < edges[b + 1])
            if mk.mean() > 0:
                ece += mk.mean() * abs(te["ge2"].values[mk].mean() - p[mk].mean())
        res.append(dict(fold=round(c, 2), n=len(te), auc_base=roc_auc_score(te["ge2"], pb),
                        auc_model=roc_auc_score(te["ge2"], p), ll=log_loss(te["ge2"], p, labels=[0, 1]), ece=ece))
    return pd.DataFrame(res)


def main():
    print("Carregando cache...", flush=True)
    pg = load()
    df, cov, gf = build(pg)
    print(f"cobertura de faltas (committed) no cache: {100*cov:.1f}%", flush=True)
    print(f"player-games com falta: {len(df)} | media faltas={gf:.2f} | >=2={df.ge2.mean():.3f} | jogadores={df.player_id.nunique()}", flush=True)
    print("\n=== VALIDACAO TEMPORAL (>=2 faltas: modelo vs taxa-base) ===", flush=True)
    R = validate(df)
    print(R.round(4).to_string(index=False), flush=True)
    dauc = (R.auc_model - R.auc_base).mean()
    print(f"\n  >> AUC base {R.auc_base.mean():.3f} -> modelo {R.auc_model.mean():.3f} ({dauc:+.3f}) | ECE {R.ece.mean()*100:.2f}%", flush=True)
    ok = R.auc_model.mean() >= 0.72 and dauc > 0 and int((R.auc_model > R.auc_base).sum()) == len(R) and R.ece.mean() < 0.02
    print(f"  >> VEREDITO (padrao do site): {'PROMOVER' if ok else 'NAO PROMOVER'}", flush=True)


if __name__ == "__main__":
    main()
