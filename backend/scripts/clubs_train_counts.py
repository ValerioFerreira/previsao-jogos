#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_train_counts.py
==============================
Fase 2.1-2.4 do plano de pesquisa de clubes: replica a CASCATA de contagem de
produção (finalizações -> escanteios/cartões, com ortogonalização de estilo) sobre
o dataset de clubes, sob o protocolo único (research_clubs/protocol.py) — 5 folds
temporais expanding, idêntico ao gate §6.

Cascata por fold (evita leakage):
  1. Ortogonalização de estilo (fit_ortho_regressions) SÓ no train do fold.
  2. Finalizações: ShotsNB com grid de time-decay H em {None,4,3,2,1} — escolhido
     por ECE da linha O/U numa sub-validação (últimos 15% do train, por data).
     Depois refit em TODO o train do fold. Gera "pred_shots" (lambdas/mus): para
     o TREINO usa-se uma versão OOF simplificada (fit em 80% mais antigo do train,
     prediz os 20% mais recentes) para alimentar corners/cards sem leakage direto;
     para o TESTE usa a previsão do modelo final do fold.
  3. Finalizações a gol: ShotsNB (grade menor, sem cascade upstream).
  4. Escanteios: CornersNB com estilo residualizado + interações de mando + pred_shots.
  5. Cartões: CardsGP (GP) com pred_shots.

Métricas: PMF log-loss, MAE, cobertura80, tail-ECE (linhas por mercado) via
research_clubs/protocol.py. Grava data/reports/clubs_counts/<mercado>.csv (resumível).

Uso: python scripts/clubs_train_counts.py [--only shots,shots_on_target,corners,cards]
"""
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from shots_nb_model import ShotsNB
from corners_nb_model import CornersNB
from cards_gp_model import CardsGP
from ortho_sinais import fit_ortho_regressions, apply_ortho_residuals, STYLE_FEATS_FULL
from corner_interactions import add_corner_interactions, CORNER_INTERACTIONS
from research_clubs.protocol import temporal_folds, pmf_logloss, pmf_mae, coverage80, tail_ece

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_DIR = ROOT / "data" / "reports" / "clubs_counts"

STYLE_RAW = [f"{s}_{sfx}" for s in ["home_style", "away_style", "diff_style"]
             for sfx in ["crosses_l5", "crosses_l10", "ppda_l5", "ppda_l10",
                        "fouls_suff_ratio_l5", "fouls_suff_ratio_l10"]]
H_GRID = [None, 4, 3, 2, 1]


def _ece_ou(y, p, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    e = 0.0
    for i in range(n_bins):
        m = (p >= bins[i]) & (p < bins[i + 1])
        if m.sum() > 0:
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return e


def decay_w(dates, anchor, H):
    if H is None:
        return None
    return 0.5 ** ((anchor - dates).dt.days.values.astype(float) / (H * 365.0))


def base_feats(df, meta_full_feats, extra_exclude=()):
    style_excl = set(STYLE_RAW) | set(extra_exclude)
    return [f for f in meta_full_feats if f in df.columns and f not in style_excl]


def fit_shots_with_decay(df_tr, feats, y_col_h, y_col_a, max_corners, line):
    """Seleciona H por ECE da linha O/U numa sub-validação temporal (15% final do train)."""
    df_tr = df_tr.sort_values("date")
    cut = int(len(df_tr) * 0.85)
    tr_in, va = df_tr.iloc[:cut], df_tr.iloc[cut:]
    if len(va) < 100:
        best_H = None
    else:
        best_H, best_ece = None, np.inf
        for H in H_GRID:
            w = decay_w(tr_in["date"], tr_in["date"].max(), H)
            m = ShotsNB(max_corners=max_corners, feats=feats)
            m.fit(tr_in[feats], tr_in[y_col_h], tr_in[y_col_a], sample_weight=w)
            dist = m.predict_distributions(va[feats])
            pt = dist["total"]
            y_over = (va[y_col_h] + va[y_col_a] > line).astype(int).to_numpy()
            p_over = pt[:, int(line) + 1:].sum(axis=1)
            e = _ece_ou(y_over, p_over)
            if e < best_ece:
                best_ece, best_H = e, H
    w_full = decay_w(df_tr["date"], df_tr["date"].max(), best_H)
    model = ShotsNB(max_corners=max_corners, feats=feats)
    model.fit(df_tr[feats], df_tr[y_col_h], df_tr[y_col_a], sample_weight=w_full)
    return model, best_H


def oof_shots_for_train(df_tr, feats, y_col_h, y_col_a, max_corners, H):
    """OOF simplificado: fit nos 80% mais antigos, prediz os 20% mais recentes; o
    resto (80% mais antigos) usa fit incremental grosseiro (refit só 1x, aceitável
    para uma feature auxiliar, não o alvo)."""
    df_tr = df_tr.sort_values("date").reset_index(drop=True)
    cut = int(len(df_tr) * 0.80)
    early, late = df_tr.iloc[:cut], df_tr.iloc[cut:]
    w_early = decay_w(early["date"], early["date"].max(), H)
    m_early = ShotsNB(max_corners=max_corners, feats=feats)
    m_early.fit(early[feats], early[y_col_h], early[y_col_a], sample_weight=w_early)
    pred_early = m_early.predict_distributions(early[feats])
    pred_late = m_early.predict_distributions(late[feats])
    out = pd.Series(index=df_tr.index, dtype=float)
    out_a = pd.Series(index=df_tr.index, dtype=float)
    out.iloc[:cut] = pred_early["lambdas"]
    out.iloc[cut:] = pred_late["lambdas"]
    out_a.iloc[:cut] = pred_early["mus"]
    out_a.iloc[cut:] = pred_late["mus"]
    return out.to_numpy(), out_a.to_numpy()


def eval_market(name, df, y_h_col, y_a_col, max_corners, ou_lines, feats_fn):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"{name}.csv"
    if out_csv.exists():
        print(f"[skip] {name} já existe")
        return pd.read_csv(out_csv)
    rows = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx].copy(), df.loc[te_idx].copy()
        m = tr[y_h_col].notna() & tr[y_a_col].notna()
        tr = tr[m]
        m2 = te[y_h_col].notna() & te[y_a_col].notna()
        te = te[m2]
        if len(tr) < 300 or len(te) < 30:
            continue
        # ortogonalização de estilo — SEMPRE, ajustada só no train (mesmo p/ shots,
        # ver train_shots_nb.py: FEATS inclui resid_* mesmo excluindo home_style_ raw)
        w_ortho = fit_ortho_regressions(tr)
        tr = apply_ortho_residuals(tr, w_ortho)
        te = apply_ortho_residuals(te, w_ortho)
        feats, extra = feats_fn(tr, te)
        tr, te = extra["tr"], extra["te"]
        model, H = fit_shots_with_decay(tr, feats, y_h_col, y_a_col, max_corners,
                                        line=ou_lines[0]) if name in ("shots", "shots_on_target") \
            else (None, None)
        if model is None:
            model = extra["model_fn"](tr, feats)
        dist_te = model.predict_distributions(te[feats])
        pmf_t = dist_te["total"]
        y_t = (te[y_h_col] + te[y_a_col]).to_numpy()
        ll = pmf_logloss(y_t, pmf_t)
        mae = pmf_mae(y_t, pmf_t)
        cov = coverage80(y_t, pmf_t)
        tece = tail_ece(y_t, pmf_t, ou_lines)
        row = {"fold": fold, "n": len(te), "logloss": ll, "mae": mae, "coverage80": cov,
              "H": H}
        row.update({f"tailece_{k}": v for k, v in tece.items()})
        rows.append(row)
        print(f"  {name} {fold}: ll={ll:.4f} mae={mae:.3f} cov80={cov:.3f} H={H}", flush=True)
    res = pd.DataFrame(rows)
    if len(res):
        res.loc["media"] = res.mean(numeric_only=True)
        res.loc["media", "fold"] = "MEDIA"
    res.to_csv(out_csv, index=False)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None

    import json
    meta = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
    full_feats = meta["full_feats"]

    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["has_advanced_stats"] == 1].sort_values("date").reset_index(drop=True)
    print(f"jogos com box-score: {len(df)}")

    # ---- finalizações (sem cascade upstream) ----
    if not only or "shots" in only:
        def feats_fn_shots(tr, te):
            feats = base_feats(tr, full_feats, extra_exclude=["pred_home_shots", "pred_away_shots"])
            return feats, {"tr": tr, "te": te}
        eval_market("shots", df, "home_cur_sb_shots", "away_cur_sb_shots", 55, [10.5, 28.5],
                   feats_fn_shots)

    if not only or "shots_on_target" in only:
        def feats_fn_sot(tr, te):
            feats = base_feats(tr, full_feats, extra_exclude=["pred_home_shots", "pred_away_shots"])
            return feats, {"tr": tr, "te": te}
        eval_market("shots_on_target", df, "home_cur_sb_shots_on_target",
                   "away_cur_sb_shots_on_target", 25, [3.5, 10.5], feats_fn_sot)

    # ---- escanteios (cascade: ortho + pred_shots) ----
    if not only or "corners" in only:
        def feats_fn_corners(tr, te):
            tr2 = add_corner_interactions(tr)
            te2 = add_corner_interactions(te)
            ph, pa = oof_shots_for_train(tr2, base_feats(tr2, full_feats,
                                         extra_exclude=["pred_home_shots", "pred_away_shots"]),
                                         "home_cur_sb_shots", "away_cur_sb_shots", 55, 2)
            tr2["pred_home_shots"], tr2["pred_away_shots"] = ph, pa
            shots_full, _ = fit_shots_with_decay(tr2, base_feats(tr2, full_feats,
                                                 extra_exclude=["pred_home_shots", "pred_away_shots"]),
                                                 "home_cur_sb_shots", "away_cur_sb_shots", 55, 22.5)
            sfeats = base_feats(tr2, full_feats, extra_exclude=["pred_home_shots", "pred_away_shots"])
            dist_te = shots_full.predict_distributions(te2[sfeats])
            te2["pred_home_shots"], te2["pred_away_shots"] = dist_te["lambdas"], dist_te["mus"]
            feats = base_feats(tr2, full_feats) + CORNER_INTERACTIONS
            feats = [f for f in feats if f in tr2.columns]

            def model_fn(tr_, feats_):
                m = CornersNB(feats=feats_)
                m.model_home_ = m._create_base_regressor()
                m.model_away_ = m._create_base_regressor()
                m.model_home_.fit(tr_[feats_], tr_["home_cur_sb_corners"])
                m.model_away_.fit(tr_[feats_], tr_["away_cur_sb_corners"])
                m.r_H_ = m._optimize_r(tr_["home_cur_sb_corners"].to_numpy(dtype=float),
                                       np.maximum(m.model_home_.predict(tr_[feats_]), 0.1))
                m.r_A_ = m._optimize_r(tr_["away_cur_sb_corners"].to_numpy(dtype=float),
                                       np.maximum(m.model_away_.predict(tr_[feats_]), 0.1))
                return m
            return feats, {"tr": tr2, "te": te2, "model_fn": model_fn}
        eval_market("corners", df, "home_cur_sb_corners", "away_cur_sb_corners", 25,
                   [8.5, 11.5], feats_fn_corners)

    # ---- cartões (cascade: pred_shots, sem ortho) ----
    if not only or "cards" in only:
        def feats_fn_cards(tr, te):
            sfeats = base_feats(tr, full_feats, extra_exclude=["pred_home_shots", "pred_away_shots"])
            ph, pa = oof_shots_for_train(tr, sfeats, "home_cur_sb_shots", "away_cur_sb_shots", 55, 2)
            tr2 = tr.copy(); tr2["pred_home_shots"], tr2["pred_away_shots"] = ph, pa
            shots_full, _ = fit_shots_with_decay(tr2, sfeats, "home_cur_sb_shots",
                                                 "away_cur_sb_shots", 55, 22.5)
            dist_te = shots_full.predict_distributions(te[sfeats])
            te2 = te.copy()
            te2["pred_home_shots"], te2["pred_away_shots"] = dist_te["lambdas"], dist_te["mus"]
            feats = base_feats(tr2, full_feats)

            def model_fn(tr_, feats_):
                m = CardsGP(feats=feats_)
                m.model_home_ = m._create_base_regressor()
                m.model_away_ = m._create_base_regressor()
                m.model_home_.fit(tr_[feats_], tr_["home_cur_sb_cards"])
                m.model_away_.fit(tr_[feats_], tr_["away_cur_sb_cards"])
                m.gp_lambda_H_ = m._optimize_gp_lambda(
                    tr_["home_cur_sb_cards"].to_numpy(dtype=float),
                    np.maximum(m.model_home_.predict(tr_[feats_]), 0.1))
                m.gp_lambda_A_ = m._optimize_gp_lambda(
                    tr_["away_cur_sb_cards"].to_numpy(dtype=float),
                    np.maximum(m.model_away_.predict(tr_[feats_]), 0.1))
                return m
            return feats, {"tr": tr2, "te": te2, "model_fn": model_fn}
        eval_market("cards", df, "home_cur_sb_cards", "away_cur_sb_cards", 15,
                   [3.5, 5.5], feats_fn_cards)

    print("\n===== RESUMO (média dos folds) =====")
    for f in sorted(OUT_DIR.glob("*.csv")):
        r = pd.read_csv(f)
        media = r[r["fold"] == "MEDIA"]
        if len(media):
            row = media.iloc[0]
            print(f"  {f.stem:20s} ll={row['logloss']:.4f} mae={row['mae']:.3f} "
                  f"cov80={row['coverage80']:.3f}")


if __name__ == "__main__":
    main()
