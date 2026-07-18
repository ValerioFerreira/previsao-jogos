#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_revisit_hypotheses.py
====================================
Fase 4 do plano de pesquisa de clubes: revisita as 9 hipóteses reprovadas/inconclusivas
em seleções (DOCUMENTACAO_CENTRAL.md §8/§9), agora com 9-13× mais dados. Cada hipótese
é uma função independente, resumível (pula se o CSV de saída já existe), avaliada sob
o protocolo único (5 folds temporais) contra o MESMO baseline (DC-NB nas 158 base_feats,
sem a mudança testada).

Uso: python scripts/clubs_revisit_hypotheses.py [--only time_decay,momentum,...]
"""
import argparse
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from corners_nb_model import CornersNB
from cards_gp_model import CardsGP
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, pmf_logloss, pmf_mae,
                                     compare, FoldResult)

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_hypotheses"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def load_df():
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    return df.sort_values("date").reset_index(drop=True)


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def result_probs(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "ece": ece_multiclass(y_idx, probs), "accuracy": accuracy(y_idx, probs)}


def _run_dc_variant(df, feats, name, sw_fn=None, n_est=100, depth=3, lr=0.05):
    """Roda DC-NB nos 5 folds com features/pesos customizados; retorna list[FoldResult]."""
    out = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr[feats].median(numeric_only=True))
        sw = sw_fn(tr) if sw_fn else None
        m = DixonColesNBRegressor(n_estimators=n_est, max_depth=depth, learning_rate=lr,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy(), sample_weight=sw)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, result_probs(m, X_te))
        out.append(FoldResult(fold, len(te), met))
        print(f"  [{name}] {fold}: ll={met['logloss']:.4f} rps={met['rps']:.4f}", flush=True)
    return out


def _save_and_report(name, baseline, candidate):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    comp = compare(baseline, candidate, metric="logloss")
    comp.to_csv(OUT_DIR / f"{name}.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    nfolds = len(comp) - 1
    delta = comp.iloc[-1]["delta"]
    veredito = "PASSA (candidato à promoção)" if wins >= 4 and delta < -0.001 else \
        ("misto" if wins >= 2 else "REPROVADO")
    print(f"\n[{name}] {wins}/{nfolds} folds melhoram | delta médio {delta:+.4f} -> {veredito}\n")
    return veredito


# ─── 4.1 time-decay em gols ──────────────────────────────────────────────────
def h_time_decay(df, baseline):
    def decay_w(dates, anchor, H):
        return 0.5 ** ((anchor - dates).dt.days.values.astype(float) / (H * 365.0))
    best_h, best = None, None
    for H in [4, 3, 2, 1]:
        cand = _run_dc_variant(df, bf(), f"decay_H{H}",
                               sw_fn=lambda tr, H=H: decay_w(tr["date"], tr["date"].max(), H))
        v = _save_and_report(f"time_decay_H{H}", baseline, cand)
        if best is None or np.mean([c.metrics["logloss"] for c in cand]) < best:
            best, best_h = np.mean([c.metrics["logloss"] for c in cand]), H
    print(f"[time_decay] melhor H={best_h}")


# ─── 4.2 momentum de forma ────────────────────────────────────────────────────
def h_momentum(df, baseline):
    df2 = df.copy()
    df2["home_momentum"] = df2["home_ppg_l3"] - df2["home_ppg_l10"]
    df2["away_momentum"] = df2["away_ppg_l3"] - df2["away_ppg_l10"]
    df2["diff_momentum"] = df2["home_momentum"] - df2["away_momentum"]
    feats = bf() + ["home_momentum", "away_momentum", "diff_momentum"]
    cand = _run_dc_variant(df2, feats, "momentum")
    _save_and_report("momentum", baseline, cand)


# ─── 4.3 blend DC+HistGBM no BTTS ─────────────────────────────────────────────
def h_blend_btts(df, baseline):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from research_clubs.protocol import ece_binary
    rows = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        feats = bf()
        X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr[feats].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        p_dc = m.predict_proba_markets(X_te)["btts"]
        y_tr = tr["btts"].to_numpy()
        y_te = te["btts"].to_numpy()
        hgb = HistGradientBoostingClassifier(max_iter=200, random_state=42)
        hgb.fit(X_tr, y_tr)
        p_hgb = hgb.predict_proba(X_te)[:, 1]
        p_blend = 0.5 * p_dc + 0.5 * p_hgb
        from research_clubs.protocol import ece_binary as eceb
        eps = 1e-12
        ll_dc = -np.mean(y_te * np.log(np.clip(p_dc, eps, 1)) + (1 - y_te) * np.log(np.clip(1 - p_dc, eps, 1)))
        ll_bl = -np.mean(y_te * np.log(np.clip(p_blend, eps, 1)) + (1 - y_te) * np.log(np.clip(1 - p_blend, eps, 1)))
        rows.append({"fold": fold, "n": len(te), "ll_dc": ll_dc, "ll_blend": ll_bl,
                    "ece_dc": eceb(y_te, p_dc), "ece_blend": eceb(y_te, p_blend)})
        print(f"  [blend_btts] {fold}: DC={ll_dc:.4f} blend={ll_bl:.4f}", flush=True)
    res = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_DIR / "blend_btts.csv", index=False)
    wins = (res["ll_blend"] < res["ll_dc"]).sum()
    print(f"\n[blend_btts] {wins}/{len(res)} folds o blend melhora -> "
          f"{'PASSA' if wins >= 4 else 'REPROVADO'}\n")


# ─── 4.4 regressor XGBoost/LightGBM p/ λ/μ ────────────────────────────────────
class DCBoosterVariant:
    """Mini-DC reaproveitando a MLE de dispersão/rho da produção, com λ/μ via
    XGBRegressor ou LGBMRegressor em vez do sklearn GBM."""
    def __init__(self, booster="xgb", max_goals=12, **kw):
        self.booster = booster
        self.max_goals = max_goals
        self.kw = kw

    def fit(self, X, yh, ya):
        if self.booster == "xgb":
            from xgboost import XGBRegressor
            Reg = lambda: XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.03,
                                       subsample=0.9, colsample_bytree=0.9, random_state=42,
                                       n_jobs=-1, verbosity=0)
        else:
            from lightgbm import LGBMRegressor
            Reg = lambda: LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.03,
                                        subsample=0.9, colsample_bytree=0.9, random_state=42,
                                        n_jobs=-1, verbosity=-1)
        self.mh_, self.ma_ = Reg(), Reg()
        self.mh_.fit(X, yh); self.ma_.fit(X, ya)
        lam = np.maximum(self.mh_.predict(X), 1e-3)
        mu = np.maximum(self.ma_.predict(X), 1e-3)
        # reusa a MLE de r_H/r_A/rho copiando a lógica da produção
        dummy = DixonColesNBRegressor(max_goals=self.max_goals)
        from scipy.optimize import minimize
        def obj(p):
            r_H, r_A, rho = p
            if r_H <= 0.01 or r_A <= 0.01:
                return 1e10
            return dummy._calculate_nll(yh, ya, lam, mu, r_H, r_A, rho)
        res = minimize(obj, [4.0, 4.0, 0.0], method="L-BFGS-B",
                       bounds=[(0.1, 1000.0), (0.1, 1000.0), (-0.25, 0.25)])
        self.r_H_, self.r_A_, self.rho_ = res.x if res.success else (4.0, 4.0, 0.0)
        return self

    def predict_proba_markets(self, X):
        lam = np.maximum(self.mh_.predict(X), 1e-3)
        mu = np.maximum(self.ma_.predict(X), 1e-3)
        dummy = DixonColesNBRegressor(max_goals=self.max_goals)
        dummy.r_H_, dummy.r_A_, dummy.rho_ = self.r_H_, self.r_A_, self.rho_
        dummy.model_home_ = dummy.model_away_ = "sentinel"

        class _Fake:
            def predict(self_, Xin):
                return lam if Xin is X or True else None
        # reutiliza predict_joint_distribution manualmente (reimplementação leve)
        from scipy.stats import nbinom
        M = self.max_goals
        k = np.arange(M + 1)
        pH = self.r_H_ / (self.r_H_ + lam)
        pA = self.r_A_ / (self.r_A_ + mu)
        margH = nbinom.pmf(k[None, :], n=self.r_H_, p=pH[:, None])
        margA = nbinom.pmf(k[None, :], n=self.r_A_, p=pA[:, None])
        margH /= margH.sum(axis=1, keepdims=True)
        margA /= margA.sum(axis=1, keepdims=True)
        joint = margH[:, :, None] * margA[:, None, :]
        tau00 = 1 - lam * mu * self.rho_
        tau01 = 1 + lam * self.rho_
        tau10 = 1 + mu * self.rho_
        tau11 = 1 - self.rho_
        joint[:, 0, 0] *= tau00; joint[:, 0, 1] *= tau01
        joint[:, 1, 0] *= tau10; joint[:, 1, 1] *= tau11
        joint = np.clip(joint, 0, None)
        joint /= joint.sum(axis=(1, 2), keepdims=True)
        Xg, Yg = np.meshgrid(k, k, indexing="ij")
        p_h = joint[:, Xg > Yg].sum(axis=1)
        p_d = joint[:, Xg == Yg].sum(axis=1)
        p_a = joint[:, Xg < Yg].sum(axis=1)
        return {"result": np.column_stack([p_a, p_d, p_h])}


def h_xgb_lgbm(df, baseline):
    for booster in ["xgb", "lgbm"]:
        cand = []
        for fold, tr_idx, te_idx in temporal_folds(df):
            tr, te = df.loc[tr_idx], df.loc[te_idx]
            feats = bf()
            X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
            X_te = te[feats].fillna(tr[feats].median(numeric_only=True))
            m = DCBoosterVariant(booster=booster).fit(X_tr, tr["home_score"].to_numpy(),
                                                       tr["away_score"].to_numpy())
            probs = m.predict_proba_markets(X_te)["result"][:, ::-1]
            y_idx = te["result"].map(Y_MAP).to_numpy()
            met = metrics(y_idx, probs)
            cand.append(FoldResult(fold, len(te), met))
            print(f"  [{booster}_lambda] {fold}: ll={met['logloss']:.4f}", flush=True)
        _save_and_report(f"{booster}_lambda", baseline, cand)


# ─── 4.5 calibração post-hoc do resultado ────────────────────────────────────
def h_calibration(df, baseline):
    from sklearn.isotonic import IsotonicRegression
    cand = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        feats = bf()
        cut = int(len(tr) * 0.85)
        tr_in, val = tr.iloc[:cut], tr.iloc[cut:]
        X_tri = tr_in[feats].fillna(tr_in[feats].median(numeric_only=True))
        X_val = val[feats].fillna(tr_in[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr_in[feats].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tri, tr_in["home_score"].to_numpy(), tr_in["away_score"].to_numpy())
        p_val = result_probs(m, X_val)
        p_te = result_probs(m, X_te)
        y_val = val["result"].map(Y_MAP).to_numpy()
        cals = []
        for k in range(3):
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(p_val[:, k], (y_val == k).astype(float))
            cals.append(iso)
        p_te_cal = np.column_stack([cals[k].predict(p_te[:, k]) for k in range(3)])
        p_te_cal = np.clip(p_te_cal, 1e-6, None)
        p_te_cal /= p_te_cal.sum(axis=1, keepdims=True)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, p_te_cal)
        cand.append(FoldResult(fold, len(te), met))
        print(f"  [calibration] {fold}: ll={met['logloss']:.4f}", flush=True)
    _save_and_report("calibration_result", baseline, cand)


# ─── 4.6 árbitro ──────────────────────────────────────────────────────────────
def h_referee(df, baseline):
    # "referee" já vem no dataset de features (propagado do fixtures no build_clubs_dataset)
    df2 = df.copy()
    df2["referee"] = df2["referee"].fillna("__desconhecido__")
    # taxa histórica de vitória mandante por árbitro (point-in-time via expanding, shift1)
    df2 = df2.sort_values(["referee", "date"])
    df2["referee_home_winrate"] = (df2.groupby("referee")["home_win"]
                                   .transform(lambda s: s.shift(1).expanding().mean()))
    df2["referee_home_winrate"] = df2["referee_home_winrate"].fillna(df2["home_win"].mean())
    df2["referee_n_games"] = df2.groupby("referee").cumcount()
    df2 = df2.sort_values("date").reset_index(drop=True)
    feats = bf() + ["referee_home_winrate"]
    cand = _run_dc_variant(df2, feats, "referee")
    _save_and_report("referee", baseline, cand)


# ─── 4.7 perfil Elo-condicionado ──────────────────────────────────────────────
def h_elo_conditioned(df, baseline):
    df2 = df.copy()
    df2["home_pts"] = df2["home_win"] * 3 + df2["draw"]
    df2["home_expected_pts"] = 3 * df2["elo_home_winprob"] + (1 - df2["elo_home_winprob"]) * 0  # aprox
    df2["home_overperf"] = df2["home_pts"] - df2["home_expected_pts"]
    # média móvel (shift1) do overperf por time mandante — sinal ortogonal ao Elo por construção
    df2 = df2.sort_values(["home_team", "date"])
    df2["home_elo_overperf_l10"] = (df2.groupby("home_team")["home_overperf"]
                                    .transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean()))
    df2["home_elo_overperf_l10"] = df2["home_elo_overperf_l10"].fillna(0.0)
    df2 = df2.sort_values("date").reset_index(drop=True)
    feats = bf() + ["home_elo_overperf_l10"]
    cand = _run_dc_variant(df2, feats, "elo_conditioned")
    _save_and_report("elo_conditioned", baseline, cand)


# ─── 4.8 xG como feature ──────────────────────────────────────────────────────
def h_xg_feature(df, baseline):
    feats = bf() + ["home_sb_xg_l5", "away_sb_xg_l5", "diff_sb_xg_l5",
                    "home_sb_xg_l10", "away_sb_xg_l10", "diff_sb_xg_l10"]
    feats = [f for f in feats if f in df.columns]
    cand = _run_dc_variant(df, feats, "xg_feature")
    _save_and_report("xg_feature", baseline, cand)


# ─── 4.9 GP vs NB (escanteios) ────────────────────────────────────────────────
def h_gp_vs_nb(df):
    dfa = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]).reset_index(drop=True)
    feats = json.load(open(META, encoding="utf-8"))["full_feats"]
    feats = [f for f in feats if f in dfa.columns and "style" not in f]
    rows = []
    for fold, tr_idx, te_idx in temporal_folds(dfa):
        tr, te = dfa.loc[tr_idx], dfa.loc[te_idx]
        if len(tr) < 300 or len(te) < 30:
            continue
        yh_tr, ya_tr = tr["home_cur_sb_corners"].to_numpy(dtype=float), tr["away_cur_sb_corners"].to_numpy(dtype=float)
        y_t = (te["home_cur_sb_corners"] + te["away_cur_sb_corners"]).to_numpy()

        nb = CornersNB(feats=feats, max_corners=25)
        nb.model_home_ = nb._create_base_regressor(); nb.model_away_ = nb._create_base_regressor()
        nb.model_home_.fit(tr[feats], yh_tr); nb.model_away_.fit(tr[feats], ya_tr)
        nb.r_H_ = nb._optimize_r(yh_tr, np.maximum(nb.model_home_.predict(tr[feats]), 0.1))
        nb.r_A_ = nb._optimize_r(ya_tr, np.maximum(nb.model_away_.predict(tr[feats]), 0.1))
        d_nb = nb.predict_distributions(te[feats])
        ll_nb, mae_nb = pmf_logloss(y_t, d_nb["total"]), pmf_mae(y_t, d_nb["total"])

        gp = CardsGP(feats=feats, max_corners=25)
        gp.model_home_ = gp._create_base_regressor(); gp.model_away_ = gp._create_base_regressor()
        gp.model_home_.fit(tr[feats], yh_tr); gp.model_away_.fit(tr[feats], ya_tr)
        gp.gp_lambda_H_ = gp._optimize_gp_lambda(yh_tr, np.maximum(gp.model_home_.predict(tr[feats]), 0.1))
        gp.gp_lambda_A_ = gp._optimize_gp_lambda(ya_tr, np.maximum(gp.model_away_.predict(tr[feats]), 0.1))
        d_gp = gp.predict_distributions(te[feats])
        ll_gp, mae_gp = pmf_logloss(y_t, d_gp["total"]), pmf_mae(y_t, d_gp["total"])

        rows.append({"fold": fold, "n": len(te), "ll_nb": ll_nb, "ll_gp": ll_gp,
                    "mae_nb": mae_nb, "mae_gp": mae_gp})
        print(f"  [gp_vs_nb corners] {fold}: NB={ll_nb:.4f} GP={ll_gp:.4f}", flush=True)
    res = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_DIR / "gp_vs_nb_corners.csv", index=False)
    wins = (res["ll_gp"] < res["ll_nb"]).sum()
    print(f"\n[gp_vs_nb] GP melhor em {wins}/{len(res)} folds\n")


HYPOTHESES = {
    "time_decay": h_time_decay, "momentum": h_momentum, "blend_btts": h_blend_btts,
    "xgb_lgbm": h_xgb_lgbm, "calibration": h_calibration, "referee": h_referee,
    "elo_conditioned": h_elo_conditioned, "xg_feature": h_xg_feature,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None

    df = load_df()
    print(f"dataset: {len(df)} jogos")

    print("\n=== baseline DC-NB (produção) ===")
    baseline = _run_dc_variant(df, bf(), "baseline")

    for name, fn in HYPOTHESES.items():
        if only and name not in only:
            continue
        print(f"\n=== 4.x {name} ===")
        try:
            fn(df, baseline)
        except Exception as e:
            print(f"  [ERRO] {name}: {e}")

    if not only or "gp_vs_nb" in only:
        print("\n=== 4.9 gp_vs_nb ===")
        try:
            h_gp_vs_nb(df)
        except Exception as e:
            print(f"  [ERRO] gp_vs_nb: {e}")


if __name__ == "__main__":
    main()
