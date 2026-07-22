#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_train_frozen_model.py
=======================================
Treina uma copia "CONGELADA" do artefato de clube usando SO dados anteriores a
um corte fixo (CUTOFF), para permitir um backtest de verdade da temporada
2025/26 sem vazamento -- o artefato de PRODUCAO (model_artifacts_clubes/) foi
(ou esta sendo) ajustado com o dataset inteiro, que ja inclui os proprios jogos
que queremos "prever" retroativamente.

Reaproveita as MESMAS classes/funcoes de build_clubs_production_artifacts.py
(DixonColesNBRegressor, ShotsNB, CornersNB, CardsGP, ortho_sinais,
clubs_train_counts) -- nao reimplementa nenhuma logica de ajuste, so filtra o
dataset de treino por data antes de chamar as mesmas rotinas, e acrescenta os
mercados que a producao treina em scripts separados (cartoes amarelo/vermelho
isolados, gols/cartoes por 1o/2o tempo) para o Predictor conseguir montar o
bloco "tempos" (ver predictor.py -- so aparece se os 4 artefatos por-tempo
existirem juntos).

As FEATURES (rolling l3/l5/l10, elo_pre, GAP ratings, h2h) continuam usando
TODO o historico disponivel ANTES do corte -- sao causais por construcao
(shift(1) na pipeline de build), so o AJUSTE dos modelos (parametros GBM/DC/
MLE) e que fica congelado no corte.

Saida: model_artifacts_clubes_2025frozen/ -- diretorio SEPARADO, nunca toca
model_artifacts_clubes/ (producao).

Uso: python scripts/backtest_train_frozen_model.py --cutoff 2025-07-01
"""
import argparse
import json
import re
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dixon_coles_model import DixonColesNBRegressor  # noqa: E402
from shots_nb_model import ShotsNB  # noqa: E402
from corners_nb_model import CornersNB  # noqa: E402
from cards_gp_model import CardsGP  # noqa: E402
from ortho_sinais import fit_ortho_regressions, apply_ortho_residuals  # noqa: E402
from corner_interactions import add_corner_interactions, CORNER_INTERACTIONS  # noqa: E402
from scripts.clubs_train_counts import (  # noqa: E402
    base_feats, fit_shots_with_decay, oof_shots_for_train,
)
from research_clubs.ratings import compute_gap_ratings  # noqa: E402

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
HALFTIME_TARGETS = ROOT / "data" / "built" / "club_halftime_targets.parquet"
SELECAO_META = ROOT / "model_artifacts" / "meta.json"

DC_PARAMS = dict(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)

GAP_RATINGS_FEATS = [
    "gap_shots_home_att", "gap_shots_home_def", "gap_shots_away_att", "gap_shots_away_def",
    "gap_shots_exp_home", "gap_shots_exp_away",
    "gap_corners_home_att", "gap_corners_home_def", "gap_corners_away_att", "gap_corners_away_def",
    "gap_corners_exp_home", "gap_corners_exp_away",
]

HALFTIME_MARKETS = [
    ("gols_1t", "home_goals_1t", "away_goals_1t", False, 12),
    ("gols_2t", "home_goals_2t", "away_goals_2t", False, 12),
    ("cartoes_1t", "home_cards_1t", "away_cards_1t", True, 15),
    ("cartoes_2t", "home_cards_2t", "away_cards_2t", True, 15),
]

_HASH_ID_RE = re.compile(r"#\d+$")


def disambiguate_collisions(df):
    """Copia de build_clubs_production_artifacts.py::disambiguate_collisions."""
    clean_home = df["home_team"].str.replace(_HASH_ID_RE, "", regex=True)
    clean_away = df["away_team"].str.replace(_HASH_ID_RE, "", regex=True)
    long = pd.concat([
        pd.DataFrame({"team": clean_home, "team_id": df["home_team_id"], "tournament": df["tournament"]}),
        pd.DataFrame({"team": clean_away, "team_id": df["away_team_id"], "tournament": df["tournament"]}),
    ], ignore_index=True)
    n_ids = long.groupby("team")["team_id"].nunique()
    colliding = set(n_ids[n_ids > 1].index)
    tag = (long.groupby(["team", "team_id"])["tournament"]
           .agg(lambda s: s.value_counts().idxmax()))
    rename = {(team, tid): (f"{team} ({liga})" if team in colliding else team)
              for (team, tid), liga in tag.items()}
    df = df.copy()
    df["home_team"] = [rename.get((t, i), t) for t, i in zip(clean_home, df["home_team_id"])]
    df["away_team"] = [rename.get((t, i), t) for t, i in zip(clean_away, df["away_team_id"])]
    return df


def per_team_bases(df):
    bases = []
    for c in df.columns:
        if c.startswith("home_") and not c.startswith("home_cur_"):
            b = c[len("home_"):]
            if f"away_{b}" in df.columns and b not in ("team", "score", "win", "team_id"):
                bases.append(b)
    return sorted(set(bases))


def build_team_snapshot(df, bases):
    long = []
    for _, r in df.iterrows():
        long.append((r["date"], r["home_team"], {b: r.get(f"home_{b}") for b in bases}))
        long.append((r["date"], r["away_team"], {b: r.get(f"away_{b}") for b in bases}))
    ldf = pd.DataFrame(long, columns=["date", "team", "vals"]).sort_values("date")
    snap = {}
    for team, grp in ldf.groupby("team"):
        acc = {}
        for _, rr in grp.iterrows():
            for b, v in rr["vals"].items():
                if pd.notna(v):
                    acc[b] = float(v)
        snap[team] = acc
    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="2025-07-01",
                    help="Data de corte (YYYY-MM-DD). So jogos ANTERIORES entram no ajuste dos modelos.")
    ap.add_argument("--out", default=str(ROOT / "model_artifacts_clubes_2025frozen"))
    a = ap.parse_args()
    cutoff = pd.Timestamp(a.cutoff)
    OUT = Path(a.out)

    print("=" * 80)
    print(f" BUILD CONGELADO (backtest 2025) -- corte em {cutoff.date()}")
    print("=" * 80)

    sel_meta = json.load(open(SELECAO_META, encoding="utf-8"))
    base_feats_list = sel_meta["base_feats"]
    full_feats_list = list(sel_meta["full_feats"])
    bases_list = sel_meta["bases"]

    df_all = pd.read_parquet(FEATURES)
    df_all["date"] = pd.to_datetime(df_all["date"])
    df_all = df_all.sort_values("date").reset_index(drop=True)
    df_all = disambiguate_collisions(df_all)

    df = df_all[df_all["date"] < cutoff].reset_index(drop=True)
    print(f"Base total: {len(df_all)} jogos | usados no treino (< corte): {len(df)} jogos "
          f"({df['date'].min().date()} -> {df['date'].max().date()})")

    # ---- GAP ratings: computados so no recorte pre-corte (causal, sem olhar o futuro) ----
    print(">> GAP ratings (chutes/escanteios), so ate o corte...")
    gap_shots_df, gap_shots_state = compute_gap_ratings(
        df, "home_cur_sb_shots", "away_cur_sb_shots", prefix="gap_shots", return_state=True)
    gap_corners_df, gap_corners_state = compute_gap_ratings(
        df, "home_cur_sb_corners", "away_cur_sb_corners", prefix="gap_corners", return_state=True)
    df = pd.concat([df, gap_shots_df, gap_corners_df], axis=1)
    base_feats_list = base_feats_list + GAP_RATINGS_FEATS

    print(">> Ortogonalizacao de estilo (fit so no pre-corte)...")
    ortho_weights = fit_ortho_regressions(df)
    df = apply_ortho_residuals(df, ortho_weights)

    print(">> Dixon-Coles NB (gols)...")
    dc_feats = [f for f in base_feats_list if f in df.columns]
    dc_model = DixonColesNBRegressor(**DC_PARAMS)
    dc_model.fit(df[dc_feats], df["home_score"], df["away_score"])

    adv = df[df["has_advanced_stats"] == 1].copy()
    print(f"Jogos com box-score (pre-corte): {len(adv)}")

    print(">> Finalizacoes (ShotsNB)...")
    shots_feats = base_feats(adv, full_feats_list, extra_exclude=["pred_home_shots", "pred_away_shots"])
    shots_full, shots_H = fit_shots_with_decay(
        adv.dropna(subset=["home_cur_sb_shots", "away_cur_sb_shots"]),
        shots_feats, "home_cur_sb_shots", "away_cur_sb_shots", 55, line=10.5)
    print(f"   H escolhido: {shots_H}")

    print(">> Finalizacoes a gol (ShotsNB)...")
    sot_full, sot_H = fit_shots_with_decay(
        adv.dropna(subset=["home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target"]),
        shots_feats, "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 25, line=3.5)
    print(f"   H escolhido: {sot_H}")

    print(">> Escanteios (cascata: ortho + pred_shots OOF)...")
    corners_df = adv.dropna(subset=["home_cur_sb_corners", "away_cur_sb_corners"]).copy()
    ph, pa = oof_shots_for_train(corners_df, shots_feats, "home_cur_sb_shots",
                                  "away_cur_sb_shots", 55, H=2)
    corners_df["pred_home_shots"], corners_df["pred_away_shots"] = ph, pa
    corners_df = add_corner_interactions(corners_df)
    corners_feats = base_feats(corners_df, full_feats_list) + CORNER_INTERACTIONS
    corners_feats = [f for f in corners_feats if f in corners_df.columns]
    corners_model = CornersNB(feats=corners_feats)
    corners_model.model_home_ = corners_model._create_base_regressor()
    corners_model.model_away_ = corners_model._create_base_regressor()
    corners_model.model_home_.fit(corners_df[corners_feats], corners_df["home_cur_sb_corners"])
    corners_model.model_away_.fit(corners_df[corners_feats], corners_df["away_cur_sb_corners"])
    corners_model.r_H_ = corners_model._optimize_r(
        corners_df["home_cur_sb_corners"].to_numpy(dtype=float),
        np.maximum(corners_model.model_home_.predict(corners_df[corners_feats]), 0.1))
    corners_model.r_A_ = corners_model._optimize_r(
        corners_df["away_cur_sb_corners"].to_numpy(dtype=float),
        np.maximum(corners_model.model_away_.predict(corners_df[corners_feats]), 0.1))
    print(f"   r_H={corners_model.r_H_:.2f} r_A={corners_model.r_A_:.2f}")

    print(">> Cartoes total (cascata: pred_shots OOF)...")
    cards_df = adv.dropna(subset=["home_cur_sb_cards", "away_cur_sb_cards"]).copy()
    ph, pa = oof_shots_for_train(cards_df, shots_feats, "home_cur_sb_shots",
                                  "away_cur_sb_shots", 55, H=2)
    cards_df["pred_home_shots"], cards_df["pred_away_shots"] = ph, pa
    cards_feats = base_feats(cards_df, full_feats_list)
    cards_feats = [f for f in cards_feats if f in cards_df.columns]
    cards_model = CardsGP(feats=cards_feats)
    cards_model.model_home_ = cards_model._create_base_regressor()
    cards_model.model_away_ = cards_model._create_base_regressor()
    cards_model.model_home_.fit(cards_df[cards_feats], cards_df["home_cur_sb_cards"])
    cards_model.model_away_.fit(cards_df[cards_feats], cards_df["away_cur_sb_cards"])
    cards_model.gp_lambda_H_ = cards_model._optimize_gp_lambda(
        cards_df["home_cur_sb_cards"].to_numpy(dtype=float),
        np.maximum(cards_model.model_home_.predict(cards_df[cards_feats]), 0.1))
    cards_model.gp_lambda_A_ = cards_model._optimize_gp_lambda(
        cards_df["away_cur_sb_cards"].to_numpy(dtype=float),
        np.maximum(cards_model.model_away_.predict(cards_df[cards_feats]), 0.1))
    print(f"   gp_lambda_H={cards_model.gp_lambda_H_:.3f} gp_lambda_A={cards_model.gp_lambda_A_:.3f}")

    print(">> Meta (snapshot/GAP state/etc, base pre-corte)...")
    bases_present = [b for b in bases_list if b in df.columns or f"home_{b}" in df.columns]
    snapshot = build_team_snapshot(df, per_team_bases(df))
    teams = sorted(snapshot.keys())
    medians = {c: (float(df[c].median()) if c in df.columns and pd.notna(df[c].median()) else 0.0)
               for c in full_feats_list}
    tournament_weights = df.groupby("tournament")["tournament_weight"].mean().round(3).to_dict()
    long_ids = pd.concat([
        df[["home_team", "home_team_id"]].rename(columns={"home_team": "team", "home_team_id": "team_id"}),
        df[["away_team", "away_team_id"]].rename(columns={"away_team": "team", "away_team_id": "team_id"}),
    ], ignore_index=True)
    team_ids = {k: int(v) for k, v in
                long_ids.groupby("team")["team_id"].agg(lambda s: s.value_counts().idxmax()).to_dict().items()}

    meta = {
        "base_feats": base_feats_list,
        "full_feats": full_feats_list,
        "bases": bases_present,
        "teams": teams,
        "medians": medians,
        "snapshot": snapshot,
        "tournament_weights": tournament_weights,
        "team_ids": team_ids,
        "gap_ratings_state": {
            "shots": {k: {t: float(v) for t, v in d.items()} for k, d in gap_shots_state.items() if k != "running_mean"}
                     | {"running_mean": float(gap_shots_state["running_mean"])},
            "corners": {k: {t: float(v) for t, v in d.items()} for k, d in gap_corners_state.items() if k != "running_mean"}
                       | {"running_mean": float(gap_corners_state["running_mean"])},
        },
        "n_train": {
            "goals": len(df), "result": len(df), "btts": len(df), "over25": len(df),
            "shots": len(adv), "corners": len(corners_df), "cards": len(cards_df),
        },
        "source": f"BACKTEST 2025 -- modelo congelado, treinado so com jogos anteriores a {cutoff.date()} "
                  f"({len(tournament_weights)} competicoes). NAO E o artefato de producao.",
        "frozen_cutoff": str(cutoff.date()),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    dc_model.save(str(OUT / "dixon_coles_goals.joblib"))
    shots_full.save(str(OUT / "shots_nb.joblib"))
    sot_full.save(str(OUT / "shots_on_target_nb.joblib"))
    corners_model.save(str(OUT / "corners_cascade_rfixo.joblib"))
    cards_model.save(str(OUT / "cards_gp.joblib"))
    joblib.dump(ortho_weights, str(OUT / "style_ortho_weights.joblib"))
    with open(OUT / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    slim_cols = ["date", "home_team", "away_team", "home_score", "away_score", "tournament"]
    df[slim_cols].to_csv(OUT / "results_slim.csv", index=False)

    # ---- Cartoes amarelo/vermelho isolados (mesmo padrao de train_{yellow,red}cards_market.py) ----
    for name, col, grade in (("cartoes_amarelos", "yellow", 6), ("cartoes_vermelhos", "red", 4)):
        d = df.dropna(subset=[f"home_cur_sb_{col}", f"away_cur_sb_{col}"]).copy()
        yh = d[f"home_cur_sb_{col}"].astype(int).clip(0, grade).values
        ya = d[f"away_cur_sb_{col}"].astype(int).clip(0, grade).values
        print(f">> {name}: N={len(d)} media mand {yh.mean():.3f} vis {ya.mean():.3f}")
        m = CornersNB(feats=base_feats_list, max_corners=grade)
        X = d[base_feats_list].fillna(d[base_feats_list].median(numeric_only=True))
        m.fit(X, yh, ya)
        m.save(str(OUT / f"{name}_nb.joblib"))

    # ---- Gols/cartoes por 1o/2o tempo (mesmo padrao de train_clubs_halftime_markets.py) ----
    if HALFTIME_TARGETS.exists():
        tgt = pd.read_parquet(HALFTIME_TARGETS)
        d0 = df.merge(tgt, on="fixture_id", how="inner")
        print(f">> Mercados por tempo: base casada {len(d0)} jogos (pre-corte)")
        for name, th, ta, need_cards, grade in HALFTIME_MARKETS:
            d = d0.dropna(subset=[th, ta]).copy()
            if need_cards:
                d = d[d["has_card_events"] == 1]
            if len(d) < 200:
                print(f"   {name}: amostra insuficiente ({len(d)}), pulando")
                continue
            yh = d[th].astype(int).values
            ya = d[ta].astype(int).values
            m = CornersNB(feats=base_feats_list, max_corners=grade)
            Xf = d[base_feats_list].fillna(d[base_feats_list].median(numeric_only=True))
            m.fit(Xf, yh, ya)
            m.save(str(OUT / f"{name}_nb.joblib"))
            print(f"   {name}: N={len(d)} salvo")
    else:
        print(">> club_halftime_targets.parquet ausente -- mercados por tempo nao treinados no congelado")

    print(f"\n>> OK. Artefatos CONGELADOS (corte {cutoff.date()}) em {OUT}/")
    print(f"   times: {len(teams)} | torneios: {len(tournament_weights)} | jogos de treino: {len(df)}")


if __name__ == "__main__":
    main()
