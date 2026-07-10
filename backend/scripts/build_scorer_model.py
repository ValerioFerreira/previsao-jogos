#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_scorer_model.py
=============================
Modelo de GOLEADOR (prop "jogador a marcar"): P(jogador marca | joga), a partir do
match_detail_cache (Neon). Sinal validado (docs/BATERIA_HIPOTESES_MOMENTUM): momentum
do jogador prevê marcar ALÉM da taxa-base. Aqui juntamos base + forma + defesa do
adversário + mando + minutos, tudo point-in-time.

Faz: (1) monta player-games + defesa por time; (2) VALIDA sob CV temporal (AUC/LogLoss/
ECE, modelo vs taxa-base); (3) treina final; (4) calibra (isotônico, holdout temporal);
(5) salva artefato model_artifacts/scorer_model.joblib com o estado de serving embutido
(features mais recentes por jogador + defesa por time), para o endpoint prever sem re-varrer.

Uso: python scripts/build_scorer_model.py
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss, roc_auc_score
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "model_artifacts" / "scorer_model.joblib"
WINS = [3, 5, 10]
FEATS = ["base_scored", "form_scored_5", "form_scored_10", "form_rating_5", "form_shots_5",
         "minutes_base", "is_home", "opp_gc"]


def load_from_cache():
    # Lê o bruto do espelho LOCAL (SQLite) quando disponível — zero egress do Neon nos
    # rebuilds diários (que rodam na máquina local). Fallback para o Neon.
    from app.services import raw_cache
    pg, matches = [], []
    for d in raw_cache.iter_all_raw():
        if not d: continue
        fx = d.get("fixture") or {}; date = (fx.get("date") or "")[:10]
        teams = d.get("teams") or {}; hid = (teams.get("home") or {}).get("id"); aid = (teams.get("away") or {}).get("id")
        goals = d.get("goals") or {}; hg, ag = goals.get("home"), goals.get("away")
        key = f"{date}|{hid}|{aid}"
        if not (date and d.get("players")): continue
        if hid and aid and hg is not None and ag is not None:
            matches.append(dict(key=key, date=date, team_id=hid, gc=ag))   # mandante concede ag
            matches.append(dict(key=key, date=date, team_id=aid, gc=hg))   # visitante concede hg
        for pb in d["players"]:
            tid = (pb.get("team") or {}).get("id"); opp = aid if tid == hid else hid
            for p in pb.get("players", []):
                pl = p.get("player") or {}; st = (p.get("statistics") or [{}])[0]; g = st.get("games") or {}
                mins = g.get("minutes")
                if mins is None: continue
                try: rt = float(g.get("rating"))
                except (TypeError, ValueError): rt = np.nan
                pg.append(dict(date=date, key=key, player_id=pl.get("id"), name=pl.get("name"),
                               team_id=tid, opp_id=opp, is_home=int(tid == hid), pos=g.get("position"),
                               minutes=mins or 0, rating=rt,
                               goals=(st.get("goals") or {}).get("total") or 0,
                               shots_total=(st.get("shots") or {}).get("total") or 0))
    pg = pd.DataFrame(pg).dropna(subset=["player_id"]).drop_duplicates(["date", "player_id", "team_id"])
    matches = pd.DataFrame(matches).drop_duplicates(["date", "team_id"])
    return pg.sort_values(["player_id", "date"]).reset_index(drop=True), matches


def team_defense(matches):
    """Gols concedidos por time (média móvel 10, point-in-time)."""
    matches = matches.sort_values(["team_id", "date"]).reset_index(drop=True)
    matches["opp_gc"] = matches.groupby("team_id")["gc"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    glob = matches["gc"].mean()
    matches["opp_gc"] = matches["opp_gc"].fillna(glob)
    return matches, glob


def build_features(pg, matches, glob_gc):
    pg = pg[pg["minutes"] >= 1].copy()
    pg["scored"] = (pg["goals"] > 0).astype(int)
    gs, gr = pg["scored"].mean(), pg["rating"].mean()
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cs = g["scored"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri,
             "base_scored": (cs + 5 * gs) / (npri + 5),
             "minutes_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values}
        for w in WINS:
            d[f"form_scored_{w}"] = g["scored"].shift(1).rolling(w, min_periods=1).mean().values
            d[f"form_rating_{w}"] = g["rating"].shift(1).rolling(w, min_periods=1).mean().fillna(gr).values
            d[f"form_shots_{w}"] = g["shots_total"].shift(1).rolling(w, min_periods=1).mean().values
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns: pg[c] = F[c]
    # defesa do adversário nesse jogo (opp_gc por opp_id+date)
    defmap = matches.set_index(["team_id", "date"])["opp_gc"].to_dict()
    pg["opp_gc"] = [defmap.get((o, dt), glob_gc) for o, dt in zip(pg["opp_id"], pg["date"])]
    pg["form_rating_5"] = pg["form_rating_5"].fillna(gr)
    return pg.dropna(subset=FEATS + ["scored"]).reset_index(drop=True), gs, gr, glob_gc


def temporal_validation(df):
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4); res = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300: continue
        clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
        clf.fit(tr[FEATS], tr["scored"])
        p = clf.predict_proba(te[FEATS])[:, 1]
        pbase = te["base_scored"].clip(1e-4, 1 - 1e-4).values
        # ECE do modelo
        edges = np.linspace(0, 1, 11); ece = 0.0
        for b in range(10):
            mk = (p >= edges[b]) & (p < edges[b + 1])
            if mk.mean() > 0: ece += mk.mean() * abs(te["scored"].values[mk].mean() - p[mk].mean())
        res.append(dict(fold=round(c, 2), n=len(te),
                        auc_base=roc_auc_score(te["scored"], pbase), auc_model=roc_auc_score(te["scored"], p),
                        ll_base=log_loss(te["scored"], pbase, labels=[0, 1]), ll_model=log_loss(te["scored"], p, labels=[0, 1]),
                        ece=ece))
    return pd.DataFrame(res)


def main():
    print("Carregando cache...", flush=True)
    pg, matches = load_from_cache()
    matches, glob_gc = team_defense(matches)
    df, gs, gr, glob_gc = build_features(pg, matches, glob_gc)
    print(f"player-games: {len(df)} | marcou={df.scored.mean():.3f} | jogadores={df.player_id.nunique()}", flush=True)

    print("\n=== VALIDACAO TEMPORAL (goleador: modelo vs taxa-base) ===", flush=True)
    R = temporal_validation(df)
    print(R.to_string(index=False), flush=True)
    print(f"  >> AUC base {R.auc_base.mean():.3f} -> modelo {R.auc_model.mean():.3f} (+{(R.auc_model-R.auc_base).mean():.3f}) "
          f"| LogLoss {R.ll_base.mean():.4f} -> {R.ll_model.mean():.4f} | ECE {R.ece.mean()*100:.2f}%", flush=True)

    # ---- modelo final + calibrador isotônico (holdout temporal 85%) ----
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cut = int(len(d) * 0.85)
    clf_cal = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(d.iloc[:cut][FEATS], d.iloc[:cut]["scored"])
    pv = clf_cal.predict_proba(d.iloc[cut:][FEATS])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(pv, d.iloc[cut:]["scored"].values)
    clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(d[FEATS], d["scored"])

    # ---- estado de serving: features mais recentes por jogador + defesa por time ----
    latest = df.sort_values("date").groupby("player_id").tail(1).copy()
    state_cols = ["player_id", "name", "team_id", "pos", "date", "n_prior"] + [c for c in FEATS if c != "opp_gc" and c != "is_home"]
    player_state = latest[state_cols].rename(columns={"date": "last_date"})
    team_def = matches.sort_values("date").groupby("team_id").tail(1)[["team_id", "opp_gc"]].rename(columns={"opp_gc": "gc"})

    joblib.dump({"model": clf, "calibrator": iso, "feats": FEATS,
                 "glob_gc": float(glob_gc), "glob_scored": float(gs), "glob_rating": float(gr),
                 "player_state": player_state, "team_def": team_def,
                 "built_at": pd.Timestamp.now().isoformat(), "n_train": int(len(d))}, OUT)
    print(f"\nArtefato salvo: {OUT} | jogadores no estado: {len(player_state)} | times: {len(team_def)}", flush=True)


if __name__ == "__main__":
    main()
