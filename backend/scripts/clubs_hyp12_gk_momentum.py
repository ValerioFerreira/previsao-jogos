#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp12_gk_momentum.py
====================================
Hipotese H12 (passo 2/2): momentum de goleiro para BTTS/clean-sheet.

Constroi, a partir de data/built/club_gk_stats.parquet (goleiro titular por
jogo, extraido de players[].statistics.goals.{saves,conceded} do espelho
bruto -- ver clubs_hyp12_gk_extract.py):

  - momentum individual do goleiro: media movel (shift1, point-in-time) de
    saves e gols sofridos nas ultimas N=5 partidas EM QUE ELE JOGOU (segue o
    jogador entre times, mesmo espirito do estudo de momentum de jogador que
    passou pra props -- ver docs/PESQUISA_CLUBES.md secao momentum/jogador);
  - flag de titularidade recorrente: o goleiro de hoje é o mais frequente do
    TIME nas ultimas 10 partidas com goleiro identificado (detecta reserva
    em campo vs titular habitual).

Testa contra o protocolo unico (5 folds temporais) em TRES targets binarios:
btts, home_clean_sheet, away_clean_sheet. Baseline = HistGradientBoosting
sobre as 158 base_feats de producao; candidato = baseline + 8 features de
goleiro. Gate: >=4/5 folds melhoram logloss E delta medio < -0.001 (mesmo
gate do resto da bateria).

Uso: python scripts/clubs_hyp12_gk_momentum.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_clubs.protocol import temporal_folds, ece_binary, compare, FoldResult

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
GK_STATS = ROOT / "data" / "built" / "club_gk_stats.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_new_hyp"
N_ROLL = 5
N_REGULAR_WINDOW = 10


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def build_gk_features(df: pd.DataFrame, gk: pd.DataFrame) -> pd.DataFrame:
    """Retorna features de goleiro indexadas como df (join por fixture_id+team)."""
    # data por fixture (de df) para poder ordenar o historico do goleiro no tempo
    fx_date = df.set_index("fixture_id")["date"]
    gk = gk.copy()
    gk["date"] = gk["fixture_id"].map(fx_date)
    gk = gk.dropna(subset=["date"]).sort_values(["gk_id", "date"]).reset_index(drop=True)

    # momentum individual do goleiro (shift1 -> point-in-time, sem vazamento)
    g = gk.groupby("gk_id", sort=False)
    gk["gk_mom_saves"] = g["saves"].transform(
        lambda s: s.shift(1).rolling(N_ROLL, min_periods=2).mean())
    gk["gk_mom_conceded"] = g["conceded"].transform(
        lambda s: s.shift(1).rolling(N_ROLL, min_periods=2).mean())
    gk["gk_n_prior_games"] = g.cumcount()

    # titularidade recorrente: goleiro mais frequente do TIME nas ultimas
    # N_REGULAR_WINDOW partidas anteriores (point-in-time)
    gk = gk.sort_values(["team", "date"]).reset_index(drop=True)
    is_regular = np.zeros(len(gk), dtype=float)
    is_regular[:] = np.nan
    history: dict[str, list] = {}
    for i, row in gk.iterrows():
        team = row["team"]
        hist = history.get(team, [])
        if len(hist) >= 3:
            recent = hist[-N_REGULAR_WINDOW:]
            vals, counts = np.unique(recent, return_counts=True)
            usual_gk = vals[np.argmax(counts)]
            is_regular[i] = float(row["gk_id"] == usual_gk)
        history.setdefault(team, []).append(row["gk_id"])
    gk["gk_is_regular"] = is_regular

    return gk[["fixture_id", "team", "gk_mom_saves", "gk_mom_conceded",
              "gk_n_prior_games", "gk_is_regular"]]


def attach_sides(df: pd.DataFrame, gk_feats: pd.DataFrame) -> pd.DataFrame:
    home = gk_feats.rename(columns={c: f"home_{c}" for c in gk_feats.columns if c not in ("fixture_id", "team")})
    home = home.rename(columns={"team": "home_team"})
    away = gk_feats.rename(columns={c: f"away_{c}" for c in gk_feats.columns if c not in ("fixture_id", "team")})
    away = away.rename(columns={"team": "away_team"})

    out = df.merge(home, on=["fixture_id", "home_team"], how="left")
    out = out.merge(away, on=["fixture_id", "away_team"], how="left")
    out["diff_gk_mom_saves"] = out["home_gk_mom_saves"] - out["away_gk_mom_saves"]
    out["diff_gk_mom_conceded"] = out["home_gk_mom_conceded"] - out["away_gk_mom_conceded"]
    return out


GK_FEATS = ["home_gk_mom_saves", "away_gk_mom_saves", "diff_gk_mom_saves",
            "home_gk_mom_conceded", "away_gk_mom_conceded", "diff_gk_mom_conceded",
            "home_gk_is_regular", "away_gk_is_regular"]


def binary_logloss(y, p, eps=1e-12):
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def run_target(df: pd.DataFrame, target_col: str, feats_extra: list[str] | None, name: str):
    from sklearn.ensemble import HistGradientBoostingClassifier
    feats = bf() + (feats_extra or [])
    out = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr[feats].median(numeric_only=True))
        y_tr = tr[target_col].to_numpy(dtype=float)
        y_te = te[target_col].to_numpy(dtype=float)
        m = HistGradientBoostingClassifier(max_iter=200, random_state=42)
        m.fit(X_tr, y_tr)
        p_te = m.predict_proba(X_te)[:, 1]
        ll = binary_logloss(y_te, p_te)
        ece = ece_binary(y_te, p_te)
        out.append(FoldResult(fold, len(te), {"logloss": ll, "ece": ece}))
        print(f"  [{name}] {fold}: ll={ll:.4f} ece={ece:.4f}", flush=True)
    return out


def evaluate(df: pd.DataFrame, target_col: str, label: str):
    print(f"\n=== target: {target_col} ===", flush=True)
    baseline = run_target(df, target_col, None, f"{label}_baseline")
    cand = run_target(df, target_col, GK_FEATS, f"{label}_gk_momentum")
    comp = compare(baseline, cand, metric="logloss")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    comp.to_csv(OUT_DIR / f"h12_gk_momentum_{target_col}.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    delta = comp.iloc[-1]["delta"]
    nfolds = len(comp) - 1
    veredito = "PASSA" if wins >= 4 and delta < -0.001 else ("misto" if wins >= 2 else "REPROVADO")
    print(f"[{target_col}] {wins}/{nfolds} folds melhoram | delta medio {delta:+.4f} -> {veredito}")
    print(comp.to_string(index=False))
    return veredito, wins, nfolds, delta


def main():
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    gk = pd.read_parquet(GK_STATS)
    print(f"dataset base: {len(df)} jogos | gk_stats: {len(gk)} linhas goleiro-jogo "
          f"({gk['fixture_id'].nunique()} fixtures)", flush=True)

    print("construindo features de momentum de goleiro (point-in-time)...", flush=True)
    gk_feats = build_gk_features(df, gk)
    df = attach_sides(df, gk_feats)

    df2 = df[(df["home_matches_played_before"] >= 5) &
             (df["away_matches_played_before"] >= 5)].sort_values("date").reset_index(drop=True)
    cov = df2["diff_gk_mom_saves"].notna().mean()
    cov_regular = df2[["home_gk_is_regular", "away_gk_is_regular"]].notna().all(axis=1).mean()
    print(f"dataset pos burn-in: {len(df2)} jogos | cobertura momentum goleiro (ambos os lados): "
          f"{cov*100:.1f}% | cobertura is_regular: {cov_regular*100:.1f}%", flush=True)

    # só faz sentido testar o subconjunto com cobertura -- sem imputar sinal
    # inexistente como se fosse "zero momentum" (isso enviesaria pra baixo)
    dfc = df2.dropna(subset=GK_FEATS).reset_index(drop=True)
    print(f"dataset com goleiro identificado nos dois lados: {len(dfc)} jogos "
          f"({100*len(dfc)/len(df2):.1f}% do pos burn-in)", flush=True)

    dfc["home_clean_sheet"] = (dfc["away_score"] == 0).astype(int)
    dfc["away_clean_sheet"] = (dfc["home_score"] == 0).astype(int)

    results = {}
    for target, label in [("btts", "btts"), ("home_clean_sheet", "home_cs"),
                          ("away_clean_sheet", "away_cs")]:
        results[target] = evaluate(dfc, target, label)

    print("\n===== RESUMO H12 =====")
    for target, (veredito, wins, nfolds, delta) in results.items():
        print(f"  {target}: {wins}/{nfolds} | delta {delta:+.4f} -> {veredito}")


if __name__ == "__main__":
    main()
