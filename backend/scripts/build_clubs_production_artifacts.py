#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_clubs_production_artifacts.py
=============================================
Empacota a arquitetura vencedora da pesquisa de clubes (branch `clubs`, Linha A —
DC-NB + cascata de contagem, EXATAMENTE a arquitetura de produção de seleções, sem
mudança estrutural) como artefatos SERVÍVEIS em `model_artifacts_clubes/`.

Diferença deste script para `clubs_train_counts.py`/`clubs_tune_dc.py`: aqueles
fazem avaliação (5 folds temporais, grava métrica em CSV, não salva peso nenhum).
Este é o equivalente de produção — reaproveita as MESMAS classes/funções (import
direto, não reimplementação) mas ajusta na base INTEIRA (sem holdout, como
`train_dc_apifootball.py` faz para seleções) e persiste cada modelo.

Hiperparâmetros e feature schema (base_feats/full_feats/bases) são os já
confirmados pela pesquisa como ótimos mesmo com a base de clubes (Fase 2.5 —
tuning não deslocou o ponto ótimo; ver DOCUMENTACAO_CENTRAL.md §13.1) — copiados
de model_artifacts/meta.json (schema idêntico, confirmado em clubs_tune_dc.py).

Mercados NÃO incluídos nesta rodada (não validados pela pesquisa para clubes,
ficam de fora até um fast-follow): impedimentos, O/U por tempo (1º/2º), props de
jogador. `predictor.py` já tolera artefato ausente para os dois primeiros
(offsides_nb/ou_calibrators); os por-tempo (gols_1t/2t, cartoes_1t/2t) precisam
virar opcionais lá antes de rodar este script contra um Predictor real (ver
plano da sessão).

Uso: python scripts/build_clubs_production_artifacts.py
"""
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from dixon_coles_model import DixonColesNBRegressor
from shots_nb_model import ShotsNB
from corners_nb_model import CornersNB
from cards_gp_model import CardsGP
from ortho_sinais import fit_ortho_regressions, apply_ortho_residuals
from corner_interactions import add_corner_interactions, CORNER_INTERACTIONS
# Reaproveita os helpers já validados na pesquisa (mesmo código, não duplicado).
from scripts.clubs_train_counts import (
    base_feats, decay_w, fit_shots_with_decay, oof_shots_for_train, STYLE_RAW,
)

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
SELECAO_META = ROOT / "model_artifacts" / "meta.json"
OUT = ROOT / "model_artifacts_clubes"

DC_PARAMS = dict(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)


def per_team_bases(df):
    """Mesma lógica de train_and_save_apifootball.py::per_team_bases (genérica,
    não específica de seleção) — todo par home_{b}/away_{b} vira uma base."""
    bases = []
    for c in df.columns:
        if c.startswith("home_") and not c.startswith("home_cur_"):
            b = c[len("home_"):]
            if f"away_{b}" in df.columns and b not in ("team", "score", "win", "team_id"):
                bases.append(b)
    return sorted(set(bases))


def build_team_snapshot(df, bases):
    """Mesma lógica de train_and_save_apifootball.py::build_team_snapshot — pega
    o valor mais recente não-nulo de cada base por time (snapshot de forma atual)."""
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


_HASH_ID_RE = re.compile(r"#\d+$")


def disambiguate_collisions(df):
    """`build_clubs_dataset.py` grava cada time como "Nome#id" (chave interna
    p/ evitar colisão na COLETA entre países/ligas). Isso não pode vazar cru
    pro produto -- primeiro removemos o sufixo "#id" pra obter o nome limpo, e
    só then detectamos colisões REAIS (nome limpo com mais de um team_id) pra
    aplicar o sufixo " (Liga)" -- a esmagadora maioria fica só com o nome limpo."""
    clean_home = df["home_team"].str.replace(_HASH_ID_RE, "", regex=True)
    clean_away = df["away_team"].str.replace(_HASH_ID_RE, "", regex=True)
    long = pd.concat([
        pd.DataFrame({"team": clean_home, "team_id": df["home_team_id"], "tournament": df["tournament"]}),
        pd.DataFrame({"team": clean_away, "team_id": df["away_team_id"], "tournament": df["tournament"]}),
    ], ignore_index=True)
    n_ids = long.groupby("team")["team_id"].nunique()
    colliding = set(n_ids[n_ids > 1].index)
    if colliding:
        print(f">> Colisões de nome detectadas: {sorted(colliding)}")
    # Liga mais frequente por (nome_limpo, id) -- vira o sufixo de desambiguação
    # só para os nomes colidentes; os demais ficam só com o nome limpo.
    tag = (long.groupby(["team", "team_id"])["tournament"]
           .agg(lambda s: s.value_counts().idxmax()))
    rename = {(team, tid): (f"{team} ({liga})" if team in colliding else team)
              for (team, tid), liga in tag.items()}
    df = df.copy()
    df["home_team"] = [rename.get((t, i), t) for t, i in zip(clean_home, df["home_team_id"])]
    df["away_team"] = [rename.get((t, i), t) for t, i in zip(clean_away, df["away_team_id"])]
    return rename, df


def main():
    print("=" * 80)
    print(" BUILD DE PRODUÇÃO — artefatos de clubes (model_artifacts_clubes/)")
    print("=" * 80)

    sel_meta = json.load(open(SELECAO_META, encoding="utf-8"))
    base_feats_list = sel_meta["base_feats"]
    full_feats_list = list(sel_meta["full_feats"])
    bases_list = sel_meta["bases"]

    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Base de clubes: {len(df)} jogos ({df['date'].min().date()} -> {df['date'].max().date()})")

    _, df = disambiguate_collisions(df)

    # ---- 1. Ortogonalização de estilo (fit na base inteira, é produção) ----
    print(">> Ortogonalização de estilo...")
    ortho_weights = fit_ortho_regressions(df)
    df = apply_ortho_residuals(df, ortho_weights)

    # ---- 2. Dixon-Coles NB (resultado/BTTS/O-U gols) ----
    print(">> Dixon-Coles NB (gols)...")
    dc_feats = [f for f in base_feats_list if f in df.columns]
    dc_model = DixonColesNBRegressor(**DC_PARAMS)
    dc_model.fit(df[dc_feats], df["home_score"], df["away_score"])

    # ---- 3. Cascata de contagem (só nos jogos com box-score) ----
    adv = df[df["has_advanced_stats"] == 1].copy()
    print(f"Jogos com box-score: {len(adv)}")

    print(">> Finalizações (ShotsNB)...")
    shots_feats = base_feats(adv, full_feats_list, extra_exclude=["pred_home_shots", "pred_away_shots"])
    shots_full, shots_H = fit_shots_with_decay(
        adv.dropna(subset=["home_cur_sb_shots", "away_cur_sb_shots"]),
        shots_feats, "home_cur_sb_shots", "away_cur_sb_shots", 55, line=10.5)
    print(f"   H escolhido: {shots_H}")

    print(">> Finalizações a gol (ShotsNB)...")
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

    print(">> Cartões (cascata: pred_shots OOF)...")
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

    # ---- 4. meta_clubes.json ----
    print(">> Montando meta_clubes.json...")
    bases_present = [b for b in bases_list if b in df.columns or f"home_{b}" in df.columns]
    snapshot = build_team_snapshot(df, per_team_bases(df))
    teams = sorted(snapshot.keys())
    medians = {c: (float(df[c].median()) if c in df.columns and pd.notna(df[c].median()) else 0.0)
               for c in full_feats_list}
    tournament_weights = df.groupby("tournament")["tournament_weight"].mean().round(3).to_dict()

    # nome_limpo -> team_id (api-football) p/ escudo -- `team_ids` do Neon é só
    # de seleção, então clube resolve localmente a partir do próprio dataset
    # (home_team_id/away_team_id, já usados em disambiguate_collisions).
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
        "n_train": {
            # vencedor/BTTS/over_2_5 saem da mesma matriz conjunta do DC-NB (ver
            # predictor.py) -- mesmo tamanho de amostra que "goals". Preenchidos p/
            # app/services/odds.py::enrich_with_odds não cair no default de n=1
            # (intervalo de confiança da odd ficaria absurdamente largo).
            "goals": len(df), "result": len(df), "btts": len(df), "over25": len(df),
            "shots": len(adv), "corners": len(corners_df), "cards": len(cards_df),
        },
        "source": "api-football (clubes, 13 competições -- ver DOCUMENTACAO_CENTRAL.md §13/§14)",
    }

    # ---- 5. Salvar tudo ----
    OUT.mkdir(parents=True, exist_ok=True)
    dc_model.save(str(OUT / "dixon_coles_goals.joblib"))
    shots_full.save(str(OUT / "shots_nb.joblib"))
    sot_full.save(str(OUT / "shots_on_target_nb.joblib"))
    corners_model.save(str(OUT / "corners_cascade_rfixo.joblib"))
    cards_model.save(str(OUT / "cards_gp.joblib"))
    joblib.dump(ortho_weights, str(OUT / "style_ortho_weights.joblib"))
    with open(OUT / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    slim_cols = ["date", "home_team", "away_team", "home_score", "away_score"]
    df[slim_cols].to_csv(OUT / "results_slim.csv", index=False)

    print(f"\n>> OK. Artefatos em {OUT}/")
    print(f"   times: {len(teams)} | torneios: {len(tournament_weights)}")
    print("   (h2h_stats.csv/h2h_results.csv NÃO gerados -- Predictor já degrada com "
          "graça pro results_slim.csv quando ausentes, ver predictor.py:136-145)")


if __name__ == "__main__":
    main()
