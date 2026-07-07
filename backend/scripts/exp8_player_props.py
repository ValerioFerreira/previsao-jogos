#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp8_player_props.py — EXPERIMENTO 3: Player Props (finalizações / cartões)
==================================================================================
Hipótese: o /fixtures?players (já cacheado) tem granularidade subutilizada. Protótipo de
props individuais, cruzando a MÉDIA do jogador com a CONCESSÃO DEFENSIVA do adversário.
Props:
  A) Finalizações do jogador: P(chutes ≥ 2)  e  P(chutes a gol ≥ 1)
  B) Cartão do jogador: P(recebe cartão amarelo/vermelho)
Features point-in-time: taxa-base encolhida do jogador + forma recente + defesa/intensidade
do ADVERSÁRIO (finalizações concedidas; faltas — proxy de intensidade). Modelo GBM.
Gate §6: CV temporal expanding; AUC/LogLoss/ECE, modelo vs taxa-base. Compara com o baseline.
Saída: docs/EXP8_PLAYER_PROPS.md + console.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, log_loss
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load():
    from app.db.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        rows = c.execute(text("SELECT raw FROM match_detail_cache")).fetchall()
    pg = []
    for (raw,) in rows:
        try: d = json.loads(raw)
        except Exception: continue
        fx = d.get("fixture") or {}; date = (fx.get("date") or "")[:10]
        teams = d.get("teams") or {}; hid = (teams.get("home") or {}).get("id"); aid = (teams.get("away") or {}).get("id")
        if not (date and d.get("players")): continue
        for pb in d["players"]:
            tid = (pb.get("team") or {}).get("id"); opp = aid if tid == hid else hid
            for p in pb.get("players", []):
                pl = p.get("player") or {}; st = (p.get("statistics") or [{}])[0]; g = st.get("games") or {}
                mins = g.get("minutes")
                if mins is None: continue
                cards = st.get("cards") or {}
                pg.append(dict(date=date, player_id=pl.get("id"), team_id=tid, opp_id=opp,
                               minutes=mins or 0, pos=g.get("position"),
                               shots=(st.get("shots") or {}).get("total") or 0,
                               shots_on=(st.get("shots") or {}).get("on") or 0,
                               carded=int(((cards.get("yellow") or 0) + (cards.get("red") or 0)) > 0),
                               fouls=(st.get("fouls") or {}).get("committed") or 0))
    return pd.DataFrame(pg).dropna(subset=["player_id"]).drop_duplicates(["date", "player_id", "team_id"])


def team_concession(pg):
    """Por (time, data): finalizações concedidas e faltas do jogo (intensidade), média móvel 10."""
    ts = pg.groupby(["date", "team_id", "opp_id"]).agg(shots=("shots", "sum"), fouls=("fouls", "sum")).reset_index()
    # concessão do time = finalizações do adversário nesse jogo
    opp = ts.rename(columns={"team_id": "opp_id", "opp_id": "team_id", "shots": "shots_conc", "fouls": "fouls_opp"})
    ts = ts.merge(opp[["date", "team_id", "shots_conc", "fouls_opp"]], on=["date", "team_id"], how="left")
    ts = ts.sort_values(["team_id", "date"])
    ts["opp_shots_allowed"] = ts.groupby("team_id")["shots_conc"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    ts["opp_intensity"] = ts.groupby("team_id")["fouls"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    gsa = ts["shots_conc"].mean(); gin = ts["fouls"].mean()
    ts["opp_shots_allowed"] = ts["opp_shots_allowed"].fillna(gsa); ts["opp_intensity"] = ts["opp_intensity"].fillna(gin)
    return ts[["date", "team_id", "opp_shots_allowed", "opp_intensity"]], gsa, gin


def feats_target(pg, tconc, target, thr, extra_opp):
    pg = pg[pg["minutes"] >= 1].copy().sort_values(["player_id", "date"]).reset_index(drop=True)
    pg["y"] = (pg[target] >= thr).astype(int) if target != "carded" else pg["carded"]
    gy = pg["y"].mean()
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cum = g["y"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri, "base": (cum + 5 * gy) / (npri + 5),
             "mins_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values,
             "form5": g["y"].shift(1).rolling(5, min_periods=1).mean().values,
             "form10": g["y"].shift(1).rolling(10, min_periods=1).mean().values}
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns: pg[c] = F[c]
    # cruza com defesa do adversário (opp por opp_id+date)
    o = tconc.rename(columns={"team_id": "opp_id"})
    pg = pg.merge(o, on=["date", "opp_id"], how="left")
    feats = ["base", "n_prior", "mins_base", "form5", "form10", extra_opp]
    return pg.dropna(subset=feats + ["y"]).reset_index(drop=True), feats


def cv(df, feats):
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    base = ["base", "n_prior"]; cuts = np.linspace(0.5, 0.85, 4); res = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300: continue
        mb = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42).fit(tr[base], tr.y)
        mf = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42).fit(tr[feats], tr.y)
        pb = mb.predict_proba(te[base])[:, 1]; pf = mf.predict_proba(te[feats])[:, 1]
        edges = np.linspace(0, 1, 11); ece = 0.0
        for b in range(10):
            mk = (pf >= edges[b]) & (pf < edges[b + 1])
            if mk.mean() > 0: ece += mk.mean() * abs(te.y.values[mk].mean() - pf[mk].mean())
        res.append(dict(ab=roc_auc_score(te.y, pb), af=roc_auc_score(te.y, pf),
                        lb=log_loss(te.y, pb, labels=[0, 1]), lf=log_loss(te.y, pf, labels=[0, 1]), ece=ece))
    return pd.DataFrame(res)


def main():
    pg = load()
    print(f"player-games: {len(pg)} | jogadores {pg.player_id.nunique()}", flush=True)
    tconc, gsa, gin = team_concession(pg)

    print(f"\n{'Prop':30s} | taxa | AUC base->modelo (folds↑) | dLL | ECE")
    print("-" * 80)
    specs = [("Finalizações ≥2", "shots", 2, "opp_shots_allowed"),
             ("Finalização a gol ≥1", "shots_on", 1, "opp_shots_allowed"),
             ("Recebe cartão", "carded", 1, "opp_intensity")]
    out = {}
    for name, col, thr, extra in specs:
        df, feats = feats_target(pg, tconc, col, thr, extra)
        R = cv(df, feats)
        if len(R) == 0: print(f"{name:30s} | sem folds"); continue
        rate = df[df.n_prior >= 3].y.mean()
        out[name] = R
        print(f"{name:30s} | {rate:.2f} | {R.ab.mean():.3f}->{R.af.mean():.3f} (+{(R.af-R.ab).mean():.3f}, {int((R.af>R.ab).sum())}/{len(R)}) | {(R.lf-R.lb).mean():+.4f} | {R.ece.mean()*100:.2f}%")
    (ROOT / "data" / "reports").mkdir(parents=True, exist_ok=True)
    for k, R in out.items():
        R.to_csv(ROOT / "data" / "reports" / f"exp8_{k.split()[0].lower()}.csv", index=False)


if __name__ == "__main__":
    main()
