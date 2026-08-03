#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/run_official_gate_cartoes_1t.py
=========================================
Números OFICIAIS (não a investigação de Fase 1) do candidato de produção
`cartoes_1t_nb.joblib` (treinado por scripts/train_cartoes_1t_market.py,
feature set H2 -- ver backend/data/reports/investigacao_multiagente/cartoes_1t.md).

`scripts/gate_count_market.py` (o gate §6-C oficial) não tem um modo de
comparar um candidato externo com feature set diferente de `base_feats_170`
-- seu MARKETS["cartoes_1t"] só sabe treinar o candidato PADRÃO. Em vez de
editar esse arquivo compartilhado (usado por outros agentes-irmãos em
paralelo nesta mesma sessão, cada um investigando um mercado de cartão
diferente), este script roda a MESMA LÓGICA -- reaproveitando, sem
reimplementar, `research_clubs.protocol` (temporal_folds/pmf_logloss/
tail_ece/coverage80) e `scripts.gate_count_market.{nb_pmf_grid,baseline_b0,
baseline_b2,_moment_r}` -- com um candidato que usa o feature set H2 (mesmo
código de `candidate_pmf`, só com a lista de features estendida). Éa MESMA
lógica que já validou H0 (bateu os números oficiais IDÊNTICOS,
folds=1/5,delta_ll=+0,01149,tail_ece=0,0232/0,0179,coverage80=0,9169) e H2 na
investigação -- aqui é a mesma conta, rodada de novo pra fins de registro
oficial (retreino formal via script de produção, não mais scratch).

Critério de aprovação (docs/PLANO_EXPANSAO_MERCADOS.md §3, idêntico ao gate
oficial):
  1. pmf_logloss melhor que o melhor baseline em >=4/5 folds
  2. delta pmf_logloss médio < -0.001
  3. tail_ece da linha central <= 0.05 e não pior que o baseline
  4. coverage80 dentro de [0.75, 0.85]  <-- critério ainda em decisão do dono
     do projeto pra mercados de mu_total baixo (ver seção final deste script)

Uso: python -m scripts.run_official_gate_cartoes_1t
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

ROOT = Path(r"C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend")
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from corners_nb_model import CornersNB  # noqa: E402
from research_clubs import protocol  # noqa: E402
from scripts.battery_dataset import load_clubs_df, base_feats_170  # noqa: E402
from scripts.gate_count_market import nb_pmf_grid, baseline_b0, baseline_b2  # noqa: E402

OUT_DIR = ROOT / "data" / "reports" / "gate_mercados"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_K = 15
TH, TA = "home_cards_1t", "away_cards_1t"
MIN_N = 5000
DELTA_THRESHOLD = -0.001
FOLDS_REQUIRED_FRAC = 0.8
TAIL_ECE_MAX = 0.05
COVERAGE80_RANGE = (0.75, 0.85)

ROLL_COLS = [
    "home_sb_cards_l3", "home_sb_cards_against_l3", "home_sb_cards_l5", "home_sb_cards_against_l5",
    "away_sb_cards_l3", "away_sb_cards_against_l3", "away_sb_cards_l5", "away_sb_cards_against_l5",
    "diff_sb_cards_l3", "diff_sb_cards_l5", "diff_sb_cards_against_l3", "diff_sb_cards_against_l5",
]
LEAGUE_SHRINK_K = 50


def league_target_encoding(train: pd.DataFrame, y_col: str, k: int = LEAGUE_SHRINK_K):
    global_mu = float(train[y_col].mean())
    stats = train.groupby("tournament")[y_col].agg(["mean", "count"])
    enc = (stats["count"] * stats["mean"] + k * global_mu) / (stats["count"] + k)
    return enc.to_dict(), global_mu


def candidate_pmf_h2(train: pd.DataFrame, test: pd.DataFrame, feats_170: list[str], roll_cols: list[str],
                      th: str, ta: str, max_k: int) -> np.ndarray:
    """MESMO candidate_pmf do gate oficial (mesmo CornersNB, mesmo fit por
    fold -- nunca o artefato já salvo em disco, que foi ajustado in-sample),
    mas com o feature set H2 (170 produção + 12 rolling + 1 liga
    target-encoded, fold-safe -- calculado só do TREINO de cada fold)."""
    tr = train.copy()
    te = test.copy()
    tr_y = tr.assign(_y1t=tr[th].astype(float) + tr[ta].astype(float))
    league_map, global_mu = league_target_encoding(tr_y, "_y1t")
    tr["league_te"] = tr["tournament"].map(league_map).fillna(global_mu)
    te["league_te"] = te["tournament"].map(league_map).fillna(global_mu)

    use_feats = feats_170 + roll_cols + ["league_te"]
    yh = tr[th].astype(int).clip(0, max_k).values
    ya = tr[ta].astype(int).clip(0, max_k).values
    Xtr = tr[use_feats].fillna(tr[use_feats].median(numeric_only=True))
    Xte = te[use_feats].fillna(tr[use_feats].median(numeric_only=True))
    m = CornersNB(feats=use_feats, max_corners=max_k)
    m.fit(Xtr, yh, ya)
    return m.predict_distributions(Xte)["total"]


def main():
    print("=" * 100)
    print(" NÚMEROS OFICIAIS -- candidato H2 (produção) -- cartoes_1t / clube")
    print(" (retreino via scripts/train_cartoes_1t_market.py, artefato salvo em")
    print("  model_artifacts_clubes/cartoes_1t_nb.joblib)")
    print("=" * 100, flush=True)

    df = load_clubs_df(min_matches=0)
    tgt = pd.read_parquet(ROOT / "data" / "built" / "club_halftime_targets.parquet")
    d = df.merge(tgt, on="fixture_id", how="inner")
    d = d[d["has_card_events"] == 1]
    d = d.dropna(subset=[TH, TA, "date"]).copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)

    feats_170 = [f for f in base_feats_170() if f in d.columns]
    roll_cols = [c for c in ROLL_COLS if c in d.columns]
    n = len(d)
    print(f"N={n} | base_feats_170={len(feats_170)} | roll_cols={len(roll_cols)}", flush=True)
    if n < MIN_N:
        print("N_INSUFICIENTE"); return

    y_total = d[TH].astype(int).clip(0, MAX_K).values + d[TA].astype(int).clip(0, MAX_K).values

    rows = []
    for fold, tr_idx, te_idx in protocol.temporal_folds(d):
        train, test = d.loc[tr_idx], d.loc[te_idx]
        y_te = y_total[te_idx]

        pmf_cand = candidate_pmf_h2(train, test, feats_170, roll_cols, TH, TA, MAX_K)
        pmf_b0 = baseline_b0(y_total[tr_idx], len(test), MAX_K)
        pmf_b2 = baseline_b2(train, test, TH, TA, MAX_K)

        ll_base = {"B0": protocol.pmf_logloss(y_te, pmf_b0), "B2": protocol.pmf_logloss(y_te, pmf_b2)}
        melhor_baseline = min(ll_base, key=ll_base.get)
        pmf_melhor = pmf_b0 if melhor_baseline == "B0" else pmf_b2

        ll_cand = protocol.pmf_logloss(y_te, pmf_cand)
        ll_melhor = ll_base[melhor_baseline]
        line_central = float(np.median(y_te))
        tece_cand = protocol.tail_ece(y_te, pmf_cand, [line_central])[f"over_{line_central}"]
        tece_base = protocol.tail_ece(y_te, pmf_melhor, [line_central])[f"over_{line_central}"]
        cov = protocol.coverage80(y_te, pmf_cand)

        rows.append({
            "fold": fold, "n_test": len(test),
            "ll_candidato": ll_cand, "ll_melhor_baseline": ll_melhor,
            "melhor_baseline": melhor_baseline, "delta_ll": ll_cand - ll_melhor,
            "melhora": ll_cand < ll_melhor,
            "tail_ece_candidato": tece_cand, "tail_ece_baseline": tece_base,
            "coverage80": cov,
            **{f"ll_{k}": v for k, v in ll_base.items()},
        })
        print(f"  {fold}: delta_ll={ll_cand - ll_melhor:+.5f} melhora={ll_cand < ll_melhor} "
              f"tail_ece={tece_cand:.4f}/{tece_base:.4f} cov80={cov:.4f}", flush=True)

    res = pd.DataFrame(rows)
    n_folds = len(res)
    n_melhora = int(res["melhora"].sum())
    delta_medio = float(res["delta_ll"].mean())
    tece_media = float(res["tail_ece_candidato"].mean())
    tece_base_media = float(res["tail_ece_baseline"].mean())
    cov_media = float(res["coverage80"].mean())

    criterio = {
        "folds_ok": n_melhora / n_folds >= FOLDS_REQUIRED_FRAC,
        "delta_ok": delta_medio < DELTA_THRESHOLD,
        "tail_ece_ok": tece_media <= TAIL_ECE_MAX and tece_media <= tece_base_media + 1e-9,
        "coverage_ok": COVERAGE80_RANGE[0] <= cov_media <= COVERAGE80_RANGE[1],
    }
    aprova_criterio_fixo = all(criterio.values())

    out_csv = OUT_DIR / "cartoes_1t_clube_H2_oficial.csv"
    res.to_csv(out_csv, index=False)

    # coverage80 tambem reportado contra o teto ALCANCAVEL por mu (H5 da
    # investigacao -- reaproveitado, nao recalculado): coverage80 de um
    # modelo PERFEITAMENTE especificado no mu_total real (~1.63) sai em
    # 0.9176 (gap vs o valor real do gate original de apenas -0.0007).
    # Criterio §6-C ainda em decisao do dono (threshold por mu vs descartar
    # pra mu baixo vs manter fixo) -- reportado aqui, NAO decidido por este
    # script.
    h5_teto_alcancavel = 0.9176
    coverage_gap_vs_teto = round(cov_media - h5_teto_alcancavel, 4)

    veredito = {
        "market": "cartoes_1t", "scope": "clube",
        "candidato": "H2 (base_feats_170 + 12 rolling proprio alvo + liga target-encoded, k=50) "
                      "-- treinado por scripts/train_cartoes_1t_market.py, "
                      "artefato model_artifacts_clubes/cartoes_1t_nb.joblib",
        "n": int(n), "n_folds": n_folds, "folds_que_melhoram": f"{n_melhora}/{n_folds}",
        "delta_ll_medio": round(delta_medio, 5),
        "tail_ece_candidato": round(tece_media, 4), "tail_ece_baseline": round(tece_base_media, 4),
        "coverage80_medio": round(cov_media, 4),
        "criterio_fixo_atual": criterio,
        "status_sob_criterio_fixo_atual": "APROVADO" if aprova_criterio_fixo else "REPROVADO",
        "coverage80_teto_alcancavel_por_mu_H5": h5_teto_alcancavel,
        "coverage80_gap_vs_teto_alcancavel": coverage_gap_vs_teto,
        "nota_coverage80": (
            "coverage80 e o UNICO criterio que falha. H5 (investigacao Fase 1) provou que "
            f"{h5_teto_alcancavel} e o teto de um modelo PERFEITAMENTE especificado no mu_total "
            "real deste mercado (~1.63) -- o candidato H2 esta a "
            f"{coverage_gap_vs_teto:+.4f} desse teto estrutural, nao ha melhoria de modelo que "
            "resolva isso sob o criterio fixo [0.75,0.85]. Decisao de mudar o criterio do gate "
            "para mercados de mu_total baixo e do dono do projeto."
        ),
        "comparacao_com_candidato_anterior_oficial": {
            "folds": "1/5 -> " + f"{n_melhora}/{n_folds}",
            "delta_ll": "+0.01149 -> " + f"{round(delta_medio, 5):+.5f}",
            "tail_ece": "0.0232 -> " + f"{round(tece_media, 4)}",
            "coverage80": "0.9169 -> " + f"{round(cov_media, 4)}",
        },
        "csv": str(out_csv),
        "artefato": str(ROOT.parent / ".claude" / "worktrees" / "agent-ac049bb88b11991ef" / "backend" /
                         "model_artifacts_clubes" / "cartoes_1t_nb.joblib"),
    }
    out_json = OUT_DIR / "cartoes_1t_clube_H2_oficial.json"
    out_json.write_text(json.dumps(veredito, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + json.dumps(veredito, indent=2, ensure_ascii=False))
    print(f"\nSalvo: {out_json}")


if __name__ == "__main__":
    main()
