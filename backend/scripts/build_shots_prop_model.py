#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_shots_prop_model.py
=================================
Prop "JOGADOR A FINALIZAR" — P(jogador dá >= N finalizações | joga), N em {1,2,3}
(linhas 0,5 / 1,5 / 2,5). Espelha o modelo de goleador (build_scorer_model.py). Sinal
validado na bateria EXP8 (finalizações do jogador >=2: AUC 0,74->0,76). Aqui:
  (1) monta player-games + defesa-de-finalizações por time (chutes concedidos);
  (2) VALIDA sob CV temporal a linha principal (>=2), modelo vs taxa-base (AUC/LL/ECE);
  (3) se passar o padrão do site (~goleador), treina 3 classificadores calibrados (>=1/2/3)
      e salva model_artifacts/shots_prop_model.joblib com o estado de serving embutido.

Uso: python scripts/build_shots_prop_model.py
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
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
OUT = ROOT / "model_artifacts" / "shots_prop_model.joblib"
WINS = [3, 5, 10]
LINES = [1, 2, 3]  # >= N finalizações (linhas 0.5, 1.5, 2.5)
FEATS = ["base_shots", "form_shots_5", "form_shots_10", "form_rating_5",
         "minutes_base", "is_home", "opp_shots_allowed"]


def load_from_cache():
    # Bruto do espelho LOCAL (SQLite) quando disponível — zero egress do Neon no rebuild.
    from app.services import raw_cache
    pg, team_shots = [], []
    for d in raw_cache.iter_all_raw():
        if not d:
            continue
        fx = d.get("fixture") or {}
        date = (fx.get("date") or "")[:10]
        if ((fx.get("status") or {}).get("short")) not in ("FT", "AET", "PEN"):
            continue
        teams = d.get("teams") or {}
        hid = (teams.get("home") or {}).get("id"); aid = (teams.get("away") or {}).get("id")
        key = f"{date}|{hid}|{aid}"
        if not (date and d.get("players")):
            continue
        # finalizações por time (soma dos jogadores) -> o adversário "concede" isso
        shots_by_team = {}
        for pb in d["players"]:
            tid = (pb.get("team") or {}).get("id")
            tot = 0
            for p in pb.get("players", []):
                st = (p.get("statistics") or [{}])[0]
                tot += (st.get("shots") or {}).get("total") or 0
            shots_by_team[tid] = tot
        if hid in shots_by_team and aid in shots_by_team:
            team_shots.append(dict(date=date, team_id=hid, shots_allowed=shots_by_team[aid]))
            team_shots.append(dict(date=date, team_id=aid, shots_allowed=shots_by_team[hid]))
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
                pg.append(dict(date=date, key=key, player_id=pl.get("id"), name=pl.get("name"),
                               team_id=tid, opp_id=opp, is_home=int(tid == hid), pos=g.get("position"),
                               minutes=mins or 0, rating=rt,
                               shots=(st.get("shots") or {}).get("total") or 0))
    pg = pd.DataFrame(pg).dropna(subset=["player_id"]).drop_duplicates(["date", "player_id", "team_id"])
    team_shots = pd.DataFrame(team_shots).drop_duplicates(["date", "team_id"])
    return pg.sort_values(["player_id", "date"]).reset_index(drop=True), team_shots


def team_defense(ts):
    ts = ts.sort_values(["team_id", "date"]).reset_index(drop=True)
    ts["opp_shots_allowed"] = ts.groupby("team_id")["shots_allowed"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    glob = ts["shots_allowed"].mean()
    ts["opp_shots_allowed"] = ts["opp_shots_allowed"].fillna(glob)
    return ts, glob


def build_features(pg, ts, glob_sa):
    pg = pg[pg["minutes"] >= 1].copy()
    gsh = pg["shots"].mean(); gr = pg["rating"].mean()
    for L in LINES:
        pg[f"ge{L}"] = (pg["shots"] >= L).astype(int)
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cs = g["shots"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri,
             "base_shots": (cs + 5 * gsh) / (npri + 5),
             "minutes_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values,
             "form_rating_5": g["rating"].shift(1).rolling(5, min_periods=1).mean().fillna(gr).values}
        for w in WINS:
            d[f"form_shots_{w}"] = g["shots"].shift(1).rolling(w, min_periods=1).mean().values
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns:
        pg[c] = F[c]
    defmap = ts.set_index(["team_id", "date"])["opp_shots_allowed"].to_dict()
    pg["opp_shots_allowed"] = [defmap.get((o, dt), glob_sa) for o, dt in zip(pg["opp_id"], pg["date"])]
    pg["form_rating_5"] = pg["form_rating_5"].fillna(gr)
    return pg.dropna(subset=FEATS + [f"ge{L}" for L in LINES]).reset_index(drop=True), gsh, gr, glob_sa


def temporal_validation(df, target="ge2"):
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4); res = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300:
            continue
        clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
        clf.fit(tr[FEATS], tr[target])
        p = clf.predict_proba(te[FEATS])[:, 1]
        # base: rank pela taxa-base de finalizações (base_shots)
        pbase = (te["base_shots"] / (te["base_shots"] + 2.0)).clip(1e-4, 1 - 1e-4).values
        edges = np.linspace(0, 1, 11); ece = 0.0
        for b in range(10):
            mk = (p >= edges[b]) & (p < edges[b + 1])
            if mk.mean() > 0:
                ece += mk.mean() * abs(te[target].values[mk].mean() - p[mk].mean())
        res.append(dict(fold=round(c, 2), n=len(te),
                        auc_base=roc_auc_score(te[target], pbase), auc_model=roc_auc_score(te[target], p),
                        ll_model=log_loss(te[target], p, labels=[0, 1]), ece=ece))
    return pd.DataFrame(res)


def main():
    print("Carregando cache...", flush=True)
    pg, ts = load_from_cache()
    ts, glob_sa = team_defense(ts)
    df, gsh, gr, glob_sa = build_features(pg, ts, glob_sa)
    print(f"player-games: {len(df)} | media finalizacoes={df.shots.mean():.2f} | "
          f">=1={df.ge1.mean():.3f} >=2={df.ge2.mean():.3f} >=3={df.ge3.mean():.3f} | jogadores={df.player_id.nunique()}", flush=True)

    print("\n=== VALIDACAO TEMPORAL (>=2 finalizacoes: modelo vs taxa-base) ===", flush=True)
    R = temporal_validation(df, "ge2")
    print(R.round(4).to_string(index=False), flush=True)
    dauc = (R.auc_model - R.auc_base).mean()
    print(f"  >> AUC base {R.auc_base.mean():.3f} -> modelo {R.auc_model.mean():.3f} ({dauc:+.3f}) "
          f"| LogLoss {R.ll_model.mean():.4f} | ECE {R.ece.mean()*100:.2f}%", flush=True)
    # Gate = padrao do site (goleador em producao: AUC ~0.74, ECE ~1%): discriminacao
    # no nivel do goleador, bem calibrado, e ganho POSITIVO e CONSISTENTE sobre a taxa-base.
    ok = (R.auc_model.mean() >= 0.72 and dauc > 0
          and int((R.auc_model > R.auc_base).sum()) == len(R) and R.ece.mean() < 0.02)
    print(f"  >> VEREDITO (padrao do site, ~goleador): {'PROMOVER' if ok else 'NAO PROMOVER'}", flush=True)
    if not ok:
        print("Nao promovido — nao salva artefato.", flush=True)
        return

    # ---- treina 3 classificadores calibrados (>=1/2/3) + estado de serving ----
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cut = int(len(d) * 0.85)
    models = {}
    for L in LINES:
        y = d[f"ge{L}"]
        clf_cal = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(d.iloc[:cut][FEATS], y.iloc[:cut])
        pv = clf_cal.predict_proba(d.iloc[cut:][FEATS])[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(pv, y.iloc[cut:].values)
        clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(d[FEATS], y)
        models[L] = {"model": clf, "calibrator": iso}

    latest = df.sort_values("date").groupby("player_id").tail(1).copy()
    state_cols = ["player_id", "name", "team_id", "pos", "date", "n_prior"] + [c for c in FEATS if c not in ("opp_shots_allowed", "is_home")]
    player_state = latest[state_cols].rename(columns={"date": "last_date"})
    team_def = ts.sort_values("date").groupby("team_id").tail(1)[["team_id", "opp_shots_allowed"]].rename(columns={"opp_shots_allowed": "sa"})

    joblib.dump({"models": models, "lines": LINES, "feats": FEATS,
                 "glob_sa": float(glob_sa), "glob_shots": float(gsh), "glob_rating": float(gr),
                 "player_state": player_state, "team_def": team_def,
                 "built_at": pd.Timestamp.now().isoformat(), "n_train": int(len(d))}, OUT)
    print(f"\nArtefato salvo: {OUT} | jogadores no estado: {len(player_state)} | times: {len(team_def)}", flush=True)


if __name__ == "__main__":
    main()
