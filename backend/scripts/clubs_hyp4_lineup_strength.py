#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp4_lineup_strength.py
======================================
Hipótese H4: força de escalação real via lineups -- diferente de `squad_rotation`
(Fase5, marginal: só mede turnover vs a partida ANTERIOR). Aqui: `lineup_novelty` =
fração da XI titular de hoje que NÃO estava entre os 11 jogadores mais frequentes do
time nas últimas 10 partidas (point-in-time) -- captura desfalque real (lesão/suspensão/
rotação de mata-mata) de forma mais direta que "mudou vs jogo passado".
"""
import sys, json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, compare, FoldResult)

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
LINEUPS = ROOT / "data" / "built" / "club_lineups.parquet"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]
OUT_DIR = ROOT / "data" / "reports" / "clubs_new_hyp"
Y_MAP = {"H": 0, "D": 1, "A": 2}
WINDOW = 10


def build_novelty(df: pd.DataFrame, lineups: pd.DataFrame) -> pd.DataFrame:
    lu = lineups.set_index(["fixture_id", "team"])["player_ids"].to_dict()
    d = df.sort_values("date").reset_index(drop=True)
    history: dict[str, list[set]] = {}
    home_nov = np.full(len(d), np.nan)
    away_nov = np.full(len(d), np.nan)
    for i, row in d.iterrows():
        for side, col_out in (("home", home_nov), ("away", away_nov)):
            team = row[f"{side}_team"]
            fid = row["fixture_id"]
            xi = lu.get((fid, team))
            hist = history.get(team, [])
            if xi and len(hist) >= 3:
                recent_players: dict[int, int] = {}
                for past_xi in hist[-WINDOW:]:
                    for pid in past_xi:
                        recent_players[pid] = recent_players.get(pid, 0) + 1
                usual11 = {pid for pid, _ in sorted(recent_players.items(), key=lambda x: -x[1])[:11]}
                novel = len([p for p in xi if p not in usual11]) / max(len(xi), 1)
                col_out[i] = novel
            if xi:
                history.setdefault(team, []).append(set(xi))
    out = pd.DataFrame(index=d.index)
    out["home_lineup_novelty"] = home_nov
    out["away_lineup_novelty"] = away_nov
    out["diff_lineup_novelty"] = home_nov - away_nov
    return out.set_axis(df.sort_values("date").index)


def bf():
    return BASE_FEATS


def result_probs(model, X):
    return model.predict_proba_markets(X)["result"][:, ::-1]


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
        print(f"  [{name}] {fold}: ll={met['logloss']:.4f}", flush=True)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    lineups = pd.read_parquet(LINEUPS)
    print("construindo lineup_novelty (point-in-time)...", flush=True)
    nov = build_novelty(df, lineups)
    df = df.join(nov)
    df2 = df[(df["home_matches_played_before"] >= 5) &
             (df["away_matches_played_before"] >= 5)].sort_values("date").reset_index(drop=True)
    cov = df2["diff_lineup_novelty"].notna().mean()
    print(f"cobertura lineup_novelty: {cov*100:.1f}% dos jogos pos burn-in", flush=True)

    feats = ["home_lineup_novelty", "away_lineup_novelty", "diff_lineup_novelty"]
    base_feats = bf()
    print("\n=== baseline ===", flush=True)
    baseline = run_dc(df2, base_feats, "baseline")
    print("\n=== ablacao: lineup_novelty ===", flush=True)
    cand = run_dc(df2, base_feats + feats, "lineup_novelty")
    comp = compare(baseline, cand, metric="logloss")
    comp.to_csv(OUT_DIR / "h4_lineup_novelty.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    delta = comp.iloc[-1]["delta"]
    veredito = "PASSA" if wins >= 4 and delta < -0.001 else ("misto" if wins >= 2 else "REPROVADO")
    print(f"\nlineup_novelty: {wins}/5 folds melhoram | delta {delta:+.4f} -> {veredito}")


if __name__ == "__main__":
    main()
