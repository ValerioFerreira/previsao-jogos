#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_cartoes_1t_market.py
====================================
Mercado cartões 1º TEMPO -- candidato de produção formalizado a partir do
achado H2 da investigação de Fase 1 do PLANO 8
(backend/data/reports/investigacao_multiagente/cartoes_1t.md):

O candidato oficial anterior (base_feats_170, sem histórico do próprio alvo
nem identidade de liga) reprova o gate §6-C:
  folds=1/5, delta_ll=+0,01149, tail_ece=0,0232 (baseline 0,0179), coverage80=0,9169
  (backend/data/reports/gate_mercados/cartoes_1t_clube.json)

H2 mostrou que adicionar (a) rolling do PRÓPRIO alvo (cartões, jogo inteiro --
proxy, pois não existe rolling específico de 1T no parquet hoje) e (b)
identidade de liga (target-encoding com shrinkage bayesiano) fecha 3 dos 4
critérios do gate:
  folds=5/5, delta_ll=-0,00454, tail_ece=0,0143 (< baseline 0,0179), coverage80=0,9302

Só coverage80 continua fora de [0,75;0,85] -- e H5 (mesma investigação) provou
que isso é limite ESTRUTURAL de métrica em mu_total baixo (mu_total real
~1,63; coverage80 do modelo PERFEITAMENTE especificado sai em 0,9176 --
idêntico ao valor real, dentro do ruído de simulação; nenhum r em grid de
0,3 a 1000 atinge o alvo). Não é erro de ajuste, não é resolvível por
recalibração isolada (cartoes_1t_clube_calibracao.json já testou isotônico:
0/5 folds bate baseline). Critério de coverage80 do gate §6-C ainda está em
decisão do dono do projeto (threshold por mu vs descartar pra mu baixo vs
manter fixo) -- reportado explicitamente pelo script de validação oficial
(scripts/run_official_gate_cartoes_1t.py), não decidido aqui.

Arquitetura: MESMA CornersNB da cascata de escanteios/cartões/impedimentos
(model_home_/model_away_/r_H_/r_A_), mas com feature set ESTENDIDO em relação
ao candidato base_feats_170 de produção:
  - base_feats_170 (produção -- Elo, GAP ratings, etc., via load_clubs_df()
    pra ficar consistente com o gate oficial e não recomputar GAP ratings na
    mão)
  - + 12 colunas de rolling do PRÓPRIO alvo (cartões, jogo inteiro -- proxy
    de 1T, já existem em club_features_enriched.parquet):
    home/away_sb_cards_{l3,l5}, _against_{l3,l5}, diff_sb_cards_{l3,l5},
    diff_sb_cards_against_{l3,l5}
  - + 1 feature de identidade de liga: target-encoding de `tournament` com
    shrinkage bayesiano (k=50), fitado no dataset de TREINO inteiro (artefato
    final de produção -- sem fold aqui; a generalização já foi medida pelo
    gate oficial via CV temporal, que refita o candidato por fold)

O encoding de liga (dict tournament->valor + média global de fallback) e a
lista de colunas de rolling usadas ficam salvos como atributos extras no
próprio objeto do modelo (`league_encoding_map_`, `league_global_mean_`,
`roll_cols_`, `league_shrink_k_`) -- pickle via CornersNB.save() já carrega
tudo junto, sem precisar tocar o meta.json compartilhado (que define
base_feats_170 pra TODOS os mercados de clube).

Nota de isolamento (worktree, PLANO 8): sessão roda num worktree isolado sem
`backend/model_artifacts_clubes/`, `backend/corners_nb_model.py`, etc.
materializados (só `backend/data` e `backend/scripts` existem localmente).
LEITURA (meta.json, parquets, módulo CornersNB, GAP ratings) usa o checkout
principal via caminho absoluto -- mesmo padrão dos scripts de investigação
H0-H5. ESCRITA do artefato treinado vai pro `model_artifacts_clubes/` DENTRO
DESTE WORKTREE (autorizado pelo dono -- "não mais proibido", mas escopado ao
worktree, não sobrescreve o artefato compartilhado do checkout principal, que
outros agentes-irmãos também usam em paralelo nesta mesma sessão).

Uso: python -m scripts.train_cartoes_1t_market --scope clube
     (scope=selecao tem os mesmos dados/colunas disponíveis, mas NÃO foi
     validado nesta investigação -- toda a bateria H0-H5 rodou só em
     scope=clube; rodar selecao é responsabilidade de uma investigação
     própria, não coberta pela autorização do dono aqui.)
"""
from __future__ import annotations

import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# LEITURA: checkout principal (worktree não tem model_artifacts_clubes/,
# corners_nb_model.py, research_clubs/ etc. materializados -- só backend/data
# e backend/scripts).
READ_ROOT = Path(r"C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend")
# ESCRITA do artefato: worktree local (autorizado pelo dono, escopado --
# não sobrescreve o compartilhado do checkout principal).
WRITE_ROOT = Path(__file__).resolve().parents[1]  # backend/ dentro do worktree

sys.path.insert(0, str(READ_ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from corners_nb_model import CornersNB  # noqa: E402
from scripts.battery_dataset import load_clubs_df, base_feats_170  # noqa: E402

MAX_K = 15  # mesma grade de scripts/gate_count_market.py::MARKETS["cartoes_1t"]
TH, TA = "home_cards_1t", "away_cards_1t"
LEAGUE_SHRINK_K = 50  # mesmo valor usado e validado no H2 da investigação

ROLL_COLS = [
    "home_sb_cards_l3", "home_sb_cards_against_l3", "home_sb_cards_l5", "home_sb_cards_against_l5",
    "away_sb_cards_l3", "away_sb_cards_against_l3", "away_sb_cards_l5", "away_sb_cards_against_l5",
    "diff_sb_cards_l3", "diff_sb_cards_l5", "diff_sb_cards_against_l3", "diff_sb_cards_against_l5",
]

CONFIG = {
    "selecao": {
        "csv": READ_ROOT / "international_features_enriched_apifootball.csv",
        "art_read": READ_ROOT / "model_artifacts",
        "art_write": WRITE_ROOT / "model_artifacts",
        "halftime": READ_ROOT / "data" / "built" / "halftime_targets.parquet",
        "merge_keys": ["date", "home_team", "away_team"],  # halftime_targets.parquet de selecao não tem fixture_id
    },
    "clube": {
        "csv": READ_ROOT / "data" / "built" / "club_features_enriched.parquet",
        "art_read": READ_ROOT / "model_artifacts_clubes",
        "art_write": WRITE_ROOT / "model_artifacts_clubes",
        "halftime": READ_ROOT / "data" / "built" / "club_halftime_targets.parquet",
        "merge_keys": ["fixture_id"],
    },
}


def league_target_encoding(train: pd.DataFrame, y_col: str, k: int = LEAGUE_SHRINK_K):
    """Target-encoding com shrinkage bayesiano de `tournament`. Fitado no
    TREINO -- para o artefato final de produção isso é o dataset inteiro (sem
    holdout aqui; a generalização já foi medida pelo gate oficial via CV
    temporal com refit por fold, não por este script)."""
    global_mu = float(train[y_col].mean())
    stats = train.groupby("tournament")[y_col].agg(["mean", "count"])
    enc = (stats["count"] * stats["mean"] + k * global_mu) / (stats["count"] + k)
    return enc.to_dict(), global_mu


def build_dataset(scope: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    cfg = CONFIG[scope]
    if scope == "clube":
        # load_clubs_df já desambigua colisão de nome de time e computa GAP
        # ratings (mesmo caminho do gate oficial -- scripts/gate_count_market.py
        # e da investigação H0-H5; NÃO ler o parquet cru direto, que não tem
        # as 12 colunas gap_shots_*/gap_corners_* que base_feats_170 exige).
        df = load_clubs_df(min_matches=0)
    else:
        df = pd.read_csv(cfg["csv"], low_memory=False)
        df["date"] = pd.to_datetime(df["date"])

    tgt = pd.read_parquet(cfg["halftime"])
    d = df.merge(tgt, on=cfg["merge_keys"], how="inner")
    d = d[d["has_card_events"] == 1]
    d = d.dropna(subset=[TH, TA, "date"]).copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)

    meta = json.load(open(cfg["art_read"] / "meta.json", encoding="utf-8"))
    feats_170 = [f for f in base_feats_170() if f in d.columns] if scope == "clube" else \
        [f for f in meta["base_feats"] if f in d.columns]
    roll_cols = [c for c in ROLL_COLS if c in d.columns]
    return d, feats_170, roll_cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    a = ap.parse_args()
    cfg = CONFIG[a.scope]

    d, feats_170, roll_cols = build_dataset(a.scope)
    y_total_check = d[TH].astype(int).clip(0, MAX_K).values + d[TA].astype(int).clip(0, MAX_K).values
    print(f"[{a.scope}] N={len(d)} | media real 1T total {y_total_check.mean():.4f} "
          f"| base_feats_170={len(feats_170)} | roll_cols={len(roll_cols)}", flush=True)

    # target-encoding de liga (H2, k=50) -- fitado no dataset de TREINO
    # completo (artefato final; sem holdout aqui, ver docstring do módulo)
    d_y1t = d.assign(_y1t=d[TH].astype(float) + d[TA].astype(float))
    league_map, league_global_mean = league_target_encoding(d_y1t, "_y1t", k=LEAGUE_SHRINK_K)
    d["league_te"] = d["tournament"].map(league_map).fillna(league_global_mean)

    use_feats = feats_170 + roll_cols + ["league_te"]
    print(f"[{a.scope}] total de features do candidato H2: {len(use_feats)}", flush=True)

    yh = d[TH].astype(int).clip(0, MAX_K).values
    ya = d[TA].astype(int).clip(0, MAX_K).values
    X = d[use_feats].fillna(d[use_feats].median(numeric_only=True))

    m = CornersNB(feats=use_feats, max_corners=MAX_K)
    m.fit(X, yh, ya)

    # metadata extra anexada ao proprio objeto (pickled junto no .save() --
    # nao mexe no meta.json compartilhado, que define base_feats_170 pra
    # TODOS os mercados de clube)
    m.league_encoding_map_ = league_map
    m.league_global_mean_ = league_global_mean
    m.league_shrink_k_ = LEAGUE_SHRINK_K
    m.roll_cols_ = roll_cols
    m.base_feats_170_ = feats_170
    m.candidato_origem_ = "H2 -- backend/data/reports/investigacao_multiagente/cartoes_1t.md"

    dist = m.predict_distributions(X)
    ks = np.arange(m.max_corners + 1)
    kt = np.arange(2 * m.max_corners + 1)
    print(f"  E[PMF] mand {(dist['home']@ks).mean():.4f} vis {(dist['away']@ks).mean():.4f} "
          f"total {(dist['total']@kt).mean():.4f} (sanidade in-sample)", flush=True)
    print(f"  r_H_={m.r_H_:.4f} r_A_={m.r_A_:.4f}", flush=True)

    cfg["art_write"].mkdir(parents=True, exist_ok=True)
    out = cfg["art_write"] / "cartoes_1t_nb.joblib"
    m.save(str(out))
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
