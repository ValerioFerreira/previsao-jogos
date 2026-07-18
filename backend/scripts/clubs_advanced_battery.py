#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_advanced_battery.py
===================================
Fase 6.3, 6.4, 6.6 do plano — candidatos avançados da Linha B, sob o protocolo
único, contra o baseline vencedor da Fase 1 (DC-NB produção):

  6.3 state_space : GAS dynamic ratings (Koopman-Lit-like), por liga.
  6.4 gap_counts  : GAP ratings de chutes/escanteios como λ direto de NB (compara
                    com a cascata GBM da Fase 2 nos mesmos mercados).
  6.6 ensemble    : stacking (regressão logística multinomial) sobre as probs
                    OOF do baseline + B1_cat_pi + state_space.

Uso: python scripts/clubs_advanced_battery.py [--only state_space,gap_counts,ensemble]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from corners_nb_model import CornersNB
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, pmf_logloss, pmf_mae,
                                     compare, FoldResult, RESULT_ORDER)
from research_clubs.state_space import GASDynamicRatings
from research_clubs.ratings import compute_gap_ratings
from research_clubs.gbm_models import add_rating_features, fit_predict_catboost, PI_FEATS, ELO_FEATS
import json

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_advanced"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def result_probs_dc(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "ece": ece_multiclass(y_idx, probs), "accuracy": accuracy(y_idx, probs)}


def load_df():
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    return df.sort_values("date").reset_index(drop=True)


def run_baseline(df):
    out = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[bf()].fillna(tr[bf()].median(numeric_only=True))
        X_te = te[bf()].fillna(tr[bf()].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, result_probs_dc(m, X_te))
        out.append(FoldResult(fold, len(te), met))
        print(f"  [baseline] {fold}: ll={met['logloss']:.4f}", flush=True)
    return out


# ─── 6.3 state-space por liga ─────────────────────────────────────────────────
def h_state_space(df, baseline):
    out = []
    freq_fallback_cache = {}
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        probs = np.zeros((len(te), 3))
        freq = tr["result"].value_counts(normalize=True)
        fb = np.array([freq.get(c, 1e-3) for c in RESULT_ORDER]); fb /= fb.sum()
        for lid, te_grp in te.groupby("league_id"):
            tr_grp = tr[tr["league_id"] == lid]
            pos = te.index.get_indexer(te_grp.index)
            if len(tr_grp) < 300:
                probs[pos] = fb
                continue
            try:
                m = GASDynamicRatings().fit(tr_grp)
                probs[pos] = m.predict_hda(te_grp)
            except Exception as e:
                print(f"    [aviso] liga {lid}: {e}")
                probs[pos] = fb
        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, probs)
        out.append(FoldResult(fold, len(te), met))
        print(f"  [state_space] {fold}: ll={met['logloss']:.4f} rps={met['rps']:.4f}", flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    comp = compare(baseline, out, metric="logloss")
    comp.to_csv(OUT_DIR / "state_space.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    print(f"\n[state_space] {wins}/5 folds melhoram | delta {comp.iloc[-1]['delta']:+.4f}\n")
    return out


# ─── 6.4 GAP ratings -> NB direto (vs cascata GBM) ────────────────────────────
def h_gap_counts(df):
    dfa = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]).reset_index(drop=True)
    dfa = dfa.sort_values("date").reset_index(drop=True)
    gap = compute_gap_ratings(dfa, "home_cur_sb_shots", "away_cur_sb_shots", prefix="gap_shots")
    dfa = pd.concat([dfa, gap], axis=1)
    rows = []
    for fold, tr_idx, te_idx in temporal_folds(dfa):
        tr, te = dfa.loc[tr_idx], dfa.loc[te_idx]
        if len(tr) < 300 or len(te) < 30:
            continue
        # GAP direto: exp_home/exp_away do rating JÁ é a expectativa de chutes —
        # usa como lambda/mu direto de uma NB (só precisa do r por MLE)
        from scipy.stats import nbinom
        from scipy.optimize import minimize as _min
        yh = tr["home_cur_sb_shots"].to_numpy(dtype=float)
        ya = tr["away_cur_sb_shots"].to_numpy(dtype=float)
        lam_tr = np.maximum(tr["gap_shots_exp_home"].to_numpy(dtype=float), 0.5)
        mu_tr = np.maximum(tr["gap_shots_exp_away"].to_numpy(dtype=float), 0.5)

        def _r(y, lam):
            def obj(r):
                if r[0] <= 0.05: return 1e10
                p = r[0] / (r[0] + lam)
                return -np.sum(nbinom.logpmf(y, n=r[0], p=p))
            res = _min(obj, [10.0], bounds=[(0.1, 1000.0)], method="L-BFGS-B")
            return float(res.x[0])
        r_h, r_a = _r(yh, lam_tr), _r(ya, mu_tr)

        lam_te = np.maximum(te["gap_shots_exp_home"].to_numpy(dtype=float), 0.5)
        mu_te = np.maximum(te["gap_shots_exp_away"].to_numpy(dtype=float), 0.5)
        M = 55
        k = np.arange(M + 1)
        ph = nbinom.pmf(k[None, :], n=r_h, p=(r_h / (r_h + lam_te))[:, None])
        pa = nbinom.pmf(k[None, :], n=r_a, p=(r_a / (r_a + mu_te))[:, None])
        ph /= ph.sum(axis=1, keepdims=True); pa /= pa.sum(axis=1, keepdims=True)
        pt = np.array([np.convolve(ph[i], pa[i]) for i in range(len(te))])
        y_t = (te["home_cur_sb_shots"] + te["away_cur_sb_shots"]).to_numpy()
        ll, mae = pmf_logloss(y_t, pt), pmf_mae(y_t, pt)
        rows.append({"fold": fold, "n": len(te), "logloss": ll, "mae": mae})
        print(f"  [gap_counts shots] {fold}: ll={ll:.4f} mae={mae:.3f}", flush=True)
    res = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_DIR / "gap_counts_shots.csv", index=False)
    # referência: cascata GBM da fase 2 (clubs_train_counts.py -> data/reports/clubs_counts/shots.csv)
    cascade_csv = ROOT / "data" / "reports" / "clubs_counts" / "shots.csv"
    if cascade_csv.exists():
        casc = pd.read_csv(cascade_csv)
        casc_ll = casc[casc["fold"] == "MEDIA"]["logloss"].iloc[0] if "MEDIA" in casc["fold"].values else casc["logloss"].mean()
        print(f"  [gap_counts] GAP médio ll={res['logloss'].mean():.4f} vs cascata GBM ll={casc_ll:.4f}")
    else:
        print("  [gap_counts] cascata GBM (fase 2) ainda não disponível p/ comparação direta")


# ─── 6.6 stacking/ensemble ────────────────────────────────────────────────────
def h_ensemble(df, baseline):
    from sklearn.linear_model import LogisticRegression
    df2 = add_rating_features(df)
    out = []
    for fold, tr_idx, te_idx in temporal_folds(df2):
        tr, te = df2.loc[tr_idx], df2.loc[te_idx]
        # sub-split do treino p/ gerar probs "out-of-fold" que treinam o meta-learner
        cut = int(len(tr) * 0.85)
        tr_in, val = tr.iloc[:cut], tr.iloc[cut:]

        X_tr_in = tr_in[bf()].fillna(tr_in[bf()].median(numeric_only=True))
        X_val = val[bf()].fillna(tr_in[bf()].median(numeric_only=True))
        X_te = te[bf()].fillna(tr[bf()].median(numeric_only=True))
        m_dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                     max_goals=12, random_state=42)
        m_dc.fit(X_tr_in, tr_in["home_score"].to_numpy(), tr_in["away_score"].to_numpy())
        p_dc_val = result_probs_dc(m_dc, X_val)
        p_cat_val = fit_predict_catboost(tr_in, val, PI_FEATS + ELO_FEATS)

        m_dc_full = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                          max_goals=12, random_state=42)
        m_dc_full.fit(tr[bf()].fillna(tr[bf()].median(numeric_only=True)),
                     tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        p_dc_te = result_probs_dc(m_dc_full, X_te)
        p_cat_te = fit_predict_catboost(tr, te, PI_FEATS + ELO_FEATS)

        y_val = val["result"].map(Y_MAP).to_numpy()
        meta_X_val = np.column_stack([p_dc_val, p_cat_val])
        meta_X_te = np.column_stack([p_dc_te, p_cat_te])
        meta = LogisticRegression(max_iter=1000)
        meta.fit(meta_X_val, y_val)
        probs = meta.predict_proba(meta_X_te)
        # reordena colunas do meta (classes_ pode não estar em ordem H,D,A)
        order = [list(meta.classes_).index(k) for k in range(3)]
        probs = probs[:, order]

        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, probs)
        out.append(FoldResult(fold, len(te), met))
        print(f"  [ensemble] {fold}: ll={met['logloss']:.4f}", flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    comp = compare(baseline, out, metric="logloss")
    comp.to_csv(OUT_DIR / "ensemble.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    print(f"\n[ensemble] {wins}/5 folds melhoram | delta {comp.iloc[-1]['delta']:+.4f}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None

    df = load_df()
    print(f"dataset: {len(df)} jogos")
    print("\n=== baseline ===")
    baseline = run_baseline(df)

    if not only or "state_space" in only:
        print("\n=== 6.3 state_space ===")
        h_state_space(df, baseline)
    if not only or "gap_counts" in only:
        print("\n=== 6.4 gap_counts ===")
        h_gap_counts(df)
    if not only or "ensemble" in only:
        print("\n=== 6.6 ensemble ===")
        h_ensemble(df, baseline)


if __name__ == "__main__":
    main()
