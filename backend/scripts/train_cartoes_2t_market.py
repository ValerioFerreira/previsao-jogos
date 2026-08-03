#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_cartoes_2t_market.py
===================================
Retreino oficial de `cartoes_2t` (clube) com o candidato H1 promovido em
`backend/data/reports/investigacao_multiagente/cartoes_2t.md` (2026-08-01,
dono aprovou seguir). Mesma arquitetura `CornersNB` da cascata de
escanteios/impedimentos/cartões (ver `train_clubs_halftime_markets.py`), mas
com DUAS features extras em relação ao candidato original (que estava
REPROVADO no gate §6-C: 0/5 folds, delta_ll +0,01608):

  1. Rolling do PRÓPRIO alvo: `home_sb_cards_l5` / `away_sb_cards_l5` /
     `diff_sb_cards_l5` (já existem em `club_features_enriched.parquet`,
     nunca estiveram em `base_feats_170` -- achado de `cluster_a.md`, r=0,239
     com o alvo real, a correlação mais forte de longe entre todas as
     candidatas). Proxy do jogo INTEIRO -- não existe variante rolling
     específica de 2º tempo no parquet (limitação já registrada).
  2. Identidade de liga via target-encoding com shrinkage bayesiano
     (`_tournament_te`, m=50 pseudo-jogos de prior = média global do TREINO
     -- ver `cluster_a.md §1.2`, uma média-por-liga crua já bate o candidato
     de produção em 19/20 folds nos 4 mercados de cartão).

Essa receita, testada sob CV temporal em
`_cartoes_2t_scratch/cartoes_2t_h1.json`, corrigiu 2 dos 4 critérios do gate
(folds_ok 0/5→4/5, delta_ok +0,01608→−0,00259) e reduziu tail_ece em 44%
(0,0239→0,0135), validado por controle negativo (rolling embaralhado dá só
metade do ganho). Ainda REPROVADO em tail_ece/coverage80 -- ver
`--calibration-check` equivalente rodado após este treino.

IMPORTANTE -- pendência de wiring: a target-encoding de liga
(`_tournament_te`) e o rolling do alvo são servidos aqui a partir do dataset
de TREINO já materializado; para uma partida futura em produção real,
`predictor.py::build_row()` precisaria computar essas duas features do mesmo
jeito (rolling já é um padrão comum a outras features *_l5 do pipeline;
`_tournament_te` é NOVO e não tem wiring em `predictor.py` ainda -- fora do
escopo desta tarefa, que é só o artefato + validação). O mapa
liga→encoded value e os metadados de reconstrução vão junto no próprio
joblib (atributo `extra_state_`, ver `_build_tournament_te_map`) para quem
for fazer esse wiring depois.

Uso: python scripts/train_cartoes_2t_market.py --scope clube
(scope selecao não foi validado por esta investigação -- suportado por
simetria com os outros scripts do padrão, mas não deve ir para produção sem
antes rodar o gate com a MESMA receita em escopo seleção.)
"""
import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from corners_nb_model import CornersNB  # noqa: E402
from scripts.battery_dataset import load_clubs_df, base_feats_170  # noqa: E402

CONFIG = {
    "selecao": {
        "csv": ROOT / "international_features_enriched_apifootball.csv",
        "art": ROOT / "model_artifacts",
        "halftime": ROOT / "data" / "built" / "halftime_targets.parquet",
    },
    "clube": {
        "csv": ROOT / "data" / "built" / "club_features_enriched.parquet",
        "art": ROOT / "model_artifacts_clubes",
        "halftime": ROOT / "data" / "built" / "club_halftime_targets.parquet",
    },
}

TH, TA, MAX_K = "home_cards_2t", "away_cards_2t", 15
ROLL_COLS = ["home_sb_cards_l5", "away_sb_cards_l5", "diff_sb_cards_l5"]
TE_SHRINK_M = 50.0


def _build_tournament_te_map(train: pd.DataFrame, y_train_total: np.ndarray, m: float = TE_SHRINK_M):
    """Média por competição com shrinkage bayesiano (mesma receita testada em
    `_cartoes_2t_scratch/run_variants.py::tournament_te`, agora ajustada UMA
    vez sobre TODO o histórico disponível -- não há fold de teste em
    produção, o "treino" aqui é o dataset inteiro até a data de corte)."""
    global_mu = float(y_train_total.mean())
    tr = train.assign(_y=y_train_total)
    grp = tr.groupby("tournament")["_y"].agg(["mean", "count"])
    smoothed = (grp["mean"] * grp["count"] + global_mu * m) / (grp["count"] + m)
    return smoothed.to_dict(), global_mu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    a = ap.parse_args()
    cfg = CONFIG[a.scope]

    if a.scope == "clube":
        # load_clubs_df ja desambigua colisao de nome de time e computa GAP
        # ratings -- mesma pipeline usada pelo gate (gate_count_market.py)
        # e pelo H1 desta investigacao, para nao divergir do que foi validado.
        df = load_clubs_df(min_matches=0)
    else:
        df = pd.read_csv(cfg["csv"], low_memory=False) if cfg["csv"].suffix == ".csv" else pd.read_parquet(cfg["csv"])

    meta = json.load(open(cfg["art"] / "meta.json", encoding="utf-8"))
    base_feats = [f for f in meta["base_feats"] if f in df.columns]

    tgt = pd.read_parquet(cfg["halftime"])
    d0 = df.merge(tgt, on="fixture_id", how="inner")
    d = d0.dropna(subset=[TH, TA]).copy()
    d = d[d["has_card_events"] == 1]
    if "date" in d.columns:
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)

    for c in ROLL_COLS:
        if c not in d.columns:
            raise SystemExit(f"coluna de rolling ausente: {c} -- receita H1 exige club_features_enriched.parquet atualizado")
    if "tournament" not in d.columns:
        raise SystemExit("coluna 'tournament' ausente -- receita H1 exige identidade de liga")

    yh = d[TH].astype(int).clip(0, MAX_K).values
    ya = d[TA].astype(int).clip(0, MAX_K).values
    y_total = yh + ya
    print(f"[{a.scope}] N={len(d)} | media real mand {yh.mean():.3f} vis {ya.mean():.3f} total {y_total.mean():.3f}", flush=True)

    te_map, te_global_mu = _build_tournament_te_map(d, y_total)
    d = d.assign(_tournament_te=d["tournament"].map(te_map).fillna(te_global_mu).astype(float))

    feats = list(base_feats) + list(ROLL_COLS) + ["_tournament_te"]
    print(f"  feats: {len(base_feats)} base + {len(ROLL_COLS)} rolling + 1 tournament_te = {len(feats)} total", flush=True)

    X = d[feats].fillna(d[feats].median(numeric_only=True))
    m = CornersNB(feats=feats, max_corners=MAX_K)
    m.fit(X, yh, ya)

    # estado extra (nao usado por CornersNB.predict_distributions, que so
    # olha self.feats -- persistido aqui pra quem for servir esse candidato
    # em producao real precisar computar _tournament_te de um jogo futuro
    # sem re-treinar: mapear d["tournament"] pelo dict, com fallback pra
    # media global do treino em ligas novas/nao vistas).
    m.extra_state_ = {
        "tournament_te_map": te_map,
        "tournament_te_global_mean": te_global_mu,
        "tournament_te_shrink_m": TE_SHRINK_M,
        "roll_cols": ROLL_COLS,
        "recipe": "H1 (cartoes_2t.md, 2026-08-01) -- rolling do proprio alvo + tournament TE",
        "trained_n": int(len(d)),
    }

    dist = m.predict_distributions(X)
    ks = np.arange(m.max_corners + 1)
    kt = np.arange(2 * m.max_corners + 1)
    print(f"  E[PMF] mand {(dist['home']@ks).mean():.3f} vis {(dist['away']@ks).mean():.3f} "
          f"total {(dist['total']@kt).mean():.3f} (sanidade in-sample)", flush=True)
    print(f"  r_H_={m.r_H_:.4f} r_A_={m.r_A_:.4f}", flush=True)

    out = cfg["art"] / "cartoes_2t_nb.joblib"
    m.save(str(out))
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
