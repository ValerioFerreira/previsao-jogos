#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_assist_model.py
=============================
Modelo de ASSISTÊNCIA (prop "jogador dá assistência"): P(jogador assiste | joga).
Espelha build_scorer_model.py ponto a ponto (mesma arquitetura: base point-in-time +
forma + defesa do adversário + mando + minutos), só troca o alvo: `assists` em vez de
`goals`. Dado usado: players[].statistics[].goals.assists, já presente no bruto
cacheado (match_detail_cache / club_match_detail_cache), zero chamada nova à API.

Uso: python scripts/build_assist_model.py [--scope selecao|clube]
"""
import argparse
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss, roc_auc_score
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WINS = [3, 5, 10]
FEATS = ["base_assisted", "form_assisted_5", "form_assisted_10", "form_rating_5", "form_keypasses_5",
         "minutes_base", "is_home", "opp_gc"]


def load_from_cache(scope: str = "selecao"):
    from app.services import raw_cache
    pg, matches = [], []
    for d in raw_cache.iter_all_raw(scope):
        if not d:
            continue
        fx = d.get("fixture") or {}
        date = (fx.get("date") or "")[:10]
        if ((fx.get("status") or {}).get("short")) not in ("FT", "AET", "PEN"):
            continue
        teams = d.get("teams") or {}
        hid = (teams.get("home") or {}).get("id"); aid = (teams.get("away") or {}).get("id")
        goals = d.get("goals") or {}; hg, ag = goals.get("home"), goals.get("away")
        key = f"{date}|{hid}|{aid}"
        if not (date and d.get("players")):
            continue
        if hid and aid and hg is not None and ag is not None:
            matches.append(dict(key=key, date=date, team_id=hid, gc=ag))
            matches.append(dict(key=key, date=date, team_id=aid, gc=hg))
        for pb in d["players"]:
            tid = (pb.get("team") or {}).get("id"); opp = aid if tid == hid else hid
            for p in pb.get("players", []):
                pl = p.get("player") or {}; st = (p.get("statistics") or [{}])[0]; g = st.get("games") or {}
                mins = g.get("minutes")
                if mins is None:
                    continue
                try:
                    rt = float(g.get("rating"))
                except (TypeError, ValueError):
                    rt = np.nan
                gl = st.get("goals") or {}
                pass_st = st.get("passes") or {}
                pg.append(dict(date=date, key=key, player_id=pl.get("id"), name=pl.get("name"),
                               team_id=tid, opp_id=opp, is_home=int(tid == hid), pos=g.get("position"),
                               minutes=mins or 0, rating=rt,
                               assists=gl.get("assists") or 0,
                               key_passes=pass_st.get("key") or 0))
    pg = pd.DataFrame(pg).dropna(subset=["player_id"]).drop_duplicates(["date", "player_id", "team_id"])
    matches = pd.DataFrame(matches).drop_duplicates(["date", "team_id"])
    return pg.sort_values(["player_id", "date"]).reset_index(drop=True), matches


def team_defense(matches):
    matches = matches.sort_values(["team_id", "date"]).reset_index(drop=True)
    matches["opp_gc"] = matches.groupby("team_id")["gc"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    glob = matches["gc"].mean()
    matches["opp_gc"] = matches["opp_gc"].fillna(glob)
    return matches, glob


def build_features(pg, matches, glob_gc):
    pg = pg[pg["minutes"] >= 1].copy()
    pg["assisted"] = (pg["assists"] > 0).astype(int)
    gs, gr = pg["assisted"].mean(), pg["rating"].mean()
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cs = g["assisted"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri,
             "base_assisted": (cs + 5 * gs) / (npri + 5),
             "minutes_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values}
        for w in WINS:
            d[f"form_assisted_{w}"] = g["assisted"].shift(1).rolling(w, min_periods=1).mean().values
            d[f"form_rating_{w}"] = g["rating"].shift(1).rolling(w, min_periods=1).mean().fillna(gr).values
        d["form_keypasses_5"] = g["key_passes"].shift(1).rolling(5, min_periods=1).mean().values
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns:
        pg[c] = F[c]
    defmap = matches.set_index(["team_id", "date"])["opp_gc"].to_dict()
    pg["opp_gc"] = [defmap.get((o, dt), glob_gc) for o, dt in zip(pg["opp_id"], pg["date"])]
    pg["form_rating_5"] = pg["form_rating_5"].fillna(gr)
    return pg.dropna(subset=FEATS + ["assisted"]).reset_index(drop=True), gs, gr, glob_gc


def temporal_validation(df):
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4); res = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300:
            continue
        clf = HistGradientBoostingClassifier(max_iter=200, max_depth=3, learning_rate=0.05, random_state=42)
        clf.fit(tr[FEATS], tr["assisted"])
        p = clf.predict_proba(te[FEATS])[:, 1]
        pbase = te["base_assisted"].clip(1e-4, 1 - 1e-4).values
        edges = np.linspace(0, 1, 11); ece = 0.0
        for b in range(10):
            mk = (p >= edges[b]) & (p < edges[b + 1])
            if mk.mean() > 0:
                ece += mk.mean() * abs(te["assisted"].values[mk].mean() - p[mk].mean())
        res.append(dict(fold=round(c, 2), n=len(te),
                        auc_base=roc_auc_score(te["assisted"], pbase), auc_model=roc_auc_score(te["assisted"], p),
                        ll_base=log_loss(te["assisted"], pbase, labels=[0, 1]), ll_model=log_loss(te["assisted"], p, labels=[0, 1]),
                        ece=ece))
    return pd.DataFrame(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], default="selecao")
    args = ap.parse_args()
    out = ROOT / ("model_artifacts_clubes" if args.scope == "clube" else "model_artifacts") / "assist_model.joblib"

    print(f"Carregando cache (scope={args.scope})...", flush=True)
    pg, matches = load_from_cache(args.scope)
    matches, glob_gc = team_defense(matches)
    df, gs, gr, glob_gc = build_features(pg, matches, glob_gc)
    print(f"player-games: {len(df)} | assistiu={df.assisted.mean():.3f} | jogadores={df.player_id.nunique()}", flush=True)

    print("\n=== VALIDACAO TEMPORAL (assistencia: modelo vs taxa-base) ===", flush=True)
    R = temporal_validation(df)
    print(R.round(4).to_string(index=False), flush=True)
    dauc = (R.auc_model - R.auc_base).mean()
    print(f"  >> AUC base {R.auc_base.mean():.3f} -> modelo {R.auc_model.mean():.3f} ({dauc:+.3f}) "
          f"| LogLoss {R.ll_base.mean():.4f} -> {R.ll_model.mean():.4f} | ECE {R.ece.mean()*100:.2f}%", flush=True)
    ok = (R.auc_model.mean() >= 0.65 and dauc > 0
          and int((R.auc_model > R.auc_base).sum()) >= len(R) - 1 and R.ece.mean() < 0.03)
    print(f"  >> VEREDITO (gate padrao do site): {'PROMOVER' if ok else 'NAO PROMOVER'}", flush=True)
    if not ok:
        print("Nao promovido -- nao salva artefato.", flush=True)
        return

    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cut = int(len(d) * 0.85)
    clf_cal = HistGradientBoostingClassifier(max_iter=200, max_depth=3, learning_rate=0.05, random_state=42).fit(d.iloc[:cut][FEATS], d.iloc[:cut]["assisted"])
    pv = clf_cal.predict_proba(d.iloc[cut:][FEATS])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(pv, d.iloc[cut:]["assisted"].values)
    clf = HistGradientBoostingClassifier(max_iter=200, max_depth=3, learning_rate=0.05, random_state=42).fit(d[FEATS], d["assisted"])

    latest = df.sort_values("date").groupby("player_id").tail(1).copy()
    state_cols = ["player_id", "name", "team_id", "pos", "date", "n_prior"] + [c for c in FEATS if c not in ("opp_gc", "is_home")]
    player_state = latest[state_cols].rename(columns={"date": "last_date"})
    team_def = matches.sort_values("date").groupby("team_id").tail(1)[["team_id", "opp_gc"]].rename(columns={"opp_gc": "gc"})

    joblib.dump({"model": clf, "calibrator": iso, "feats": FEATS,
                 "glob_gc": float(glob_gc), "glob_assisted": float(gs), "glob_rating": float(gr),
                 "player_state": player_state, "team_def": team_def,
                 "built_at": pd.Timestamp.now().isoformat(), "n_train": int(len(d))}, out)
    print(f"\nArtefato salvo: {out} | jogadores no estado: {len(player_state)} | times: {len(team_def)}", flush=True)


if __name__ == "__main__":
    main()
