#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_btts.py
==========================
Estudo de melhoria do mercado AMBAS MARCAM (BTTS).

Em produção o BTTS sai da matriz conjunta do Dixon-Coles NB (predictor.py ->
dc_probs["btts"]). Este script avalia, na MESMA validação temporal do projeto,
uma bateria de intervenções e diz qual (ou conjunto) melhora — com gate honesto:
calibração/blends são ajustados em OOF do TREINO (TimeSeriesSplit) e medidos só no
TESTE out-of-sample; significância por bootstrap no teste.

Métricas: Log-Loss (primária, binária), Brier, ECE, AUC, Acc@0.5.
Saídas: reports/btts_experimentos.json e reports/btts_relatorio.md
"""
import os
import json
import warnings
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from scipy.optimize import minimize_scalar
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.ensemble import HistGradientBoostingClassifier, GradientBoostingClassifier
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
from joblib import Parallel, delayed

from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
RS = 42
M_GOALS = 12
CSV_PATH = Path("international_features_enriched_apifootball.csv")
OUT_DIR = Path("reports")
OUT_DIR.mkdir(exist_ok=True)

LEAK_OR_ID = {
    "match_id", "date", "home_team", "away_team", "city", "country", "tournament",
    "home_score", "away_score", "goal_diff", "total_goals", "result",
    "home_win", "away_win", "draw", "btts", "over_2_5",
    "has_advanced_stats", "year", "month", "decade",
}


def base_features(df):
    cols = []
    for c in df.columns:
        if c in LEAK_OR_ID or c.startswith(("home_cur_", "away_cur_")) or "sb_" in c:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


def silent_fit(model, X, yh, ya):
    with contextlib.redirect_stdout(io.StringIO()):
        model.fit(X, yh, ya)
    return model


# ---- BTTS a partir dos parâmetros (permite override de rho / escala) ----------
def btts_from(lam, mu, rH, rA, rho, M=M_GOALS):
    lam = np.maximum(lam, 1e-4); mu = np.maximum(mu, 1e-4)
    k = np.arange(M + 1)
    pH = rH / (rH + lam); pA = rA / (rA + mu)
    probH = nbinom.pmf(k[None, :], n=rH, p=pH[:, None])
    probA = nbinom.pmf(k[None, :], n=rA, p=pA[:, None])
    Pj = probH[:, :, None] * probA[:, None, :]
    N = len(lam)
    tau = np.ones((N, M + 1, M + 1))
    tau[:, 0, 0] = 1 - lam * mu * rho
    tau[:, 0, 1] = 1 + lam * rho
    tau[:, 1, 0] = 1 + mu * rho
    tau[:, 1, 1] = 1 - rho
    Pc = np.maximum(Pj * tau, 0.0)
    s = Pc.sum(axis=(1, 2), keepdims=True); s[s == 0] = 1e-15
    Pn = Pc / s
    return Pn[:, 1:, 1:].sum(axis=(1, 2))


def lam_mu(model, X):
    lam = np.maximum(model.model_home_.predict(X), 1e-4)
    mu = np.maximum(model.model_away_.predict(X), 1e-4)
    return lam, mu


# ---- métricas ----------------------------------------------------------------
def ece(y, p, n_bins=10):
    b = np.linspace(0, 1, n_bins + 1); e = 0.0
    for i in range(n_bins):
        m = (p >= b[i]) & (p < b[i + 1])
        if m.mean() > 0:
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return e


def metrics(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "ece": float(ece(y, p)),
        "auc": float(roc_auc_score(y, p)),
        "acc": float(((p >= 0.5).astype(int) == y).mean()),
    }


def boot_winrate(y, p_base, p_cand, n=2000, seed=RS):
    """% de reamostragens em que o candidato tem log-loss menor que a baseline,
    e delta médio (cand - base; negativo = melhora)."""
    rng = np.random.default_rng(seed)
    yb = np.clip(p_base, 1e-6, 1 - 1e-6); yc = np.clip(p_cand, 1e-6, 1 - 1e-6)
    ll_b = -(y * np.log(yb) + (1 - y) * np.log(1 - yb))
    ll_c = -(y * np.log(yc) + (1 - y) * np.log(1 - yc))
    N = len(y); deltas = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, N, N)
        deltas[i] = ll_c[idx].mean() - ll_b[idx].mean()
    return float((deltas < 0).mean()), float(deltas.mean()), float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


# ---- OOF helpers (TimeSeriesSplit expanding) ---------------------------------
def time_folds(n, k=5):
    """Índices (tr, va) expanding window, sem embaralhar (respeita o tempo)."""
    fold = n // (k + 1)
    for i in range(1, k + 1):
        tr_end = fold * i
        va_end = fold * (i + 1) if i < k else n
        yield np.arange(0, tr_end), np.arange(tr_end, va_end)


def oof_dc(Xtr, yh, ya, k=5):
    Xtr = Xtr.reset_index(drop=True); yh = yh.reset_index(drop=True); ya = ya.reset_index(drop=True)
    oof = np.full(len(Xtr), np.nan)

    def run(tr, va):
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=M_GOALS, random_state=RS)
        silent_fit(m, Xtr.iloc[tr], yh.iloc[tr], ya.iloc[tr])
        lam, mu = lam_mu(m, Xtr.iloc[va])
        return va, btts_from(lam, mu, m.r_H_, m.r_A_, m.rho_)

    res = Parallel(n_jobs=5)(delayed(run)(tr, va) for tr, va in time_folds(len(Xtr), k))
    for va, p in res:
        oof[va] = p
    return oof


def oof_clf(make, Xtr, ytr, k=5):
    Xtr = Xtr.reset_index(drop=True); ytr = np.asarray(ytr)
    oof = np.full(len(Xtr), np.nan)

    def run(tr, va):
        clf = make()
        clf.fit(Xtr.iloc[tr], ytr[tr])
        return va, clf.predict_proba(Xtr.iloc[va])[:, 1]

    res = Parallel(n_jobs=5)(delayed(run)(tr, va) for tr, va in time_folds(len(Xtr), k))
    for va, p in res:
        oof[va] = p
    return oof


# ---- calibradores ------------------------------------------------------------
def fit_platt(p_oof, y):
    z = np.log(np.clip(p_oof, 1e-6, 1 - 1e-6) / (1 - np.clip(p_oof, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    lr = LogisticRegression(C=1e6, solver="lbfgs")
    lr.fit(z, y)
    return lambda p: lr.predict_proba(np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(-1, 1))[:, 1]


def fit_iso(p_oof, y):
    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(p_oof, y)
    return lambda p: ir.predict(p)


def fit_temp(p_oof, y):
    z = np.log(np.clip(p_oof, 1e-6, 1 - 1e-6) / (1 - np.clip(p_oof, 1e-6, 1 - 1e-6)))
    def nll(T):
        pz = 1 / (1 + np.exp(-z / T))
        pz = np.clip(pz, 1e-6, 1 - 1e-6)
        return -(y * np.log(pz) + (1 - y) * np.log(1 - pz)).mean()
    T = minimize_scalar(nll, bounds=(0.3, 3.0), method="bounded").x
    return T, (lambda p: 1 / (1 + np.exp(-np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))) / T)))


def best_blend_w(p1_oof, p2_oof, y):
    ws = np.linspace(0, 1, 21); best, bw = 1e9, 0.0
    for w in ws:
        ll = log_loss(y, np.clip(w * p1_oof + (1 - w) * p2_oof, 1e-6, 1 - 1e-6), labels=[0, 1])
        if ll < best:
            best, bw = ll, w
    return bw


def main():
    print("Carregando dataset...")
    df = pd.read_csv(CSV_PATH, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    feats = base_features(df)
    adv = df[df["has_advanced_stats"] == 1]
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr = df[df["date"] <= cut].reset_index(drop=True)
    te = df[(df["date"] > cut) & (df["has_advanced_stats"] == 1)].reset_index(drop=True)
    Xtr, Xte = tr[feats], te[feats]
    ytr_b = tr["btts"].astype(int).values
    yte = te["btts"].astype(int).values
    yh, ya = tr["home_score"], tr["away_score"]
    print(f"feats={len(feats)} | train={len(tr)} | test={len(te)} | cutoff={cut.date()} | base_rate_test={yte.mean():.3f}")

    # DC full-train (produção) -------------------------------------------------
    print("Ajustando DC no treino completo...")
    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                               max_goals=M_GOALS, random_state=RS)
    silent_fit(dc, Xtr, yh, ya)
    lam_te, mu_te = lam_mu(dc, Xte)
    rho0, rH0, rA0 = dc.rho_, dc.r_H_, dc.r_A_
    base = btts_from(lam_te, mu_te, rH0, rA0, rho0)
    print(f"  rho={rho0:.4f} r_H={rH0:.3f} r_A={rA0:.3f}")

    # OOF no treino (para calibrar/blend sem vazamento) ------------------------
    print("Gerando OOF do DC no treino (5 folds)...")
    oof_base = oof_dc(Xtr, yh, ya, k=5)
    mask = ~np.isnan(oof_base)
    oof_y = ytr_b[mask]; oof_p = oof_base[mask]

    cands = {}  # nome -> prob no teste
    extra = {}  # nome -> infos

    # 0) baseline
    cands["DC_baseline (produção)"] = base

    # 1) Sweep de rho (>=13) ---------------------------------------------------
    rho_grid = np.round(np.linspace(0.0, 0.12, 13), 4)
    for r in rho_grid:
        cands[f"rho={r:.3f}"] = btts_from(lam_te, mu_te, rH0, rA0, r)

    # 2) Escala de gols (lambda/mu) (>=13) -------------------------------------
    scale_grid = np.round(np.linspace(0.85, 1.15, 13), 3)
    for s in scale_grid:
        cands[f"gols×{s:.2f}"] = btts_from(lam_te * s, mu_te * s, rH0, rA0, rho0)

    # 3) Escala de dispersão r (afeta P(0)) ------------------------------------
    for rs in [0.6, 0.8, 1.25, 1.5, 2.0]:
        cands[f"disp_r×{rs:.2f}"] = btts_from(lam_te, mu_te, rH0 * rs, rA0 * rs, rho0)

    # 4) Melhor rho e melhor escala escolhidos por OOF (sem peek no teste) ------
    lam_oof, mu_oof = lam_mu(dc, Xtr.iloc[np.where(mask)[0]])  # aprox: usa DC full em treino p/ escolher hiperparâmetro de forma
    # (escolha do hiperparâmetro por log-loss no próprio treino OOF do DC)
    best_r = min(rho_grid, key=lambda r: log_loss(oof_y, np.clip(btts_from(lam_oof, mu_oof, rH0, rA0, r), 1e-6, 1-1e-6), labels=[0, 1]))
    best_s = min(scale_grid, key=lambda s: log_loss(oof_y, np.clip(btts_from(lam_oof*s, mu_oof*s, rH0, rA0, rho0), 1e-6, 1-1e-6), labels=[0, 1]))
    cands[f"rho*={best_r:.3f}+gols×{best_s:.2f} (OOF)"] = btts_from(lam_te*best_s, mu_te*best_s, rH0, rA0, best_r)
    extra["sel_rho"] = float(best_r); extra["sel_scale"] = float(best_s)

    # 5) Calibração pós-hoc do BTTS do DC (ajuste em OOF) ----------------------
    cands["DC + Platt"] = fit_platt(oof_p, oof_y)(base)
    cands["DC + Isotônica"] = fit_iso(oof_p, oof_y)(base)
    Tval, ftemp = fit_temp(oof_p, oof_y)
    cands[f"DC + Temperatura (T={Tval:.2f})"] = ftemp(base)
    extra["temp_T"] = float(Tval)

    # 6) Shrinkage para a base rate (w por OOF) --------------------------------
    rate = ytr_b.mean()
    w_sh = best_blend_w(oof_p, np.full_like(oof_p, rate), oof_y)
    cands[f"DC×{w_sh:.2f}+baserate (OOF)"] = np.clip(w_sh * base + (1 - w_sh) * rate, 0, 1)

    # 7) Classificadores dedicados (modelo à parte) ----------------------------
    makers = {
        "LogReg": lambda: Pipeline([("imp", SimpleImputer(strategy="median")),
                                    ("sc", StandardScaler()),
                                    ("clf", LogisticRegression(max_iter=2000, C=1.0))]),
        "HistGBM": lambda: Pipeline([("imp", SimpleImputer(strategy="median")),
                                     ("clf", HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                                                            max_iter=400, l2_regularization=1.0,
                                                                            random_state=RS))]),
        "GBM": lambda: Pipeline([("imp", SimpleImputer(strategy="median")),
                                 ("clf", GradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                                                    n_estimators=300, subsample=0.9,
                                                                    random_state=RS))]),
    }
    clf_oof = {}
    for name, make in makers.items():
        print(f"Classificador dedicado: {name} (OOF + full)...")
        oof_c = oof_clf(make, Xtr, ytr_b, k=5)
        m2 = ~np.isnan(oof_c)
        clf = make(); clf.fit(Xtr, ytr_b)
        p_te = clf.predict_proba(Xte)[:, 1]
        cands[f"Dedicado {name}"] = p_te
        clf_oof[name] = (oof_c, m2, p_te)

    # 8) Blends DC + classificador (w por OOF) ---------------------------------
    for name, (oof_c, m2, p_te) in clf_oof.items():
        common = mask & m2
        w = best_blend_w(oof_base[common], oof_c[common], ytr_b[common])
        cands[f"Blend DC×{w:.2f}+{name} (OOF)"] = np.clip(w * base + (1 - w) * p_te, 0, 1)

    # 9) Blend DC(Platt) + melhor classificador --------------------------------
    platt = fit_platt(oof_p, oof_y)
    best_clf_name = min(clf_oof, key=lambda n: log_loss(ytr_b[clf_oof[n][1]], np.clip(clf_oof[n][0][clf_oof[n][1]], 1e-6, 1-1e-6), labels=[0, 1]))
    oof_c, m2, p_te = clf_oof[best_clf_name]
    common = mask & m2
    w = best_blend_w(platt(oof_base[common]), oof_c[common], ytr_b[common])
    cands[f"Blend Platt×{w:.2f}+{best_clf_name} (OOF)"] = np.clip(w * platt(base) + (1 - w) * p_te, 0, 1)

    # ---- avaliação no TESTE + bootstrap vs baseline --------------------------
    print("Avaliando no teste + bootstrap...")
    rows = []
    base_ll = metrics(yte, base)["log_loss"]
    for name, p in cands.items():
        mt = metrics(yte, p)
        if name.startswith("DC_baseline"):
            win, dmean, dlo, dhi = 0.5, 0.0, 0.0, 0.0
        else:
            win, dmean, dlo, dhi = boot_winrate(yte, base, p, n=2000)
        rows.append({"modelo": name, **mt, "d_logloss": mt["log_loss"] - base_ll,
                     "boot_winrate": win, "boot_dmean": dmean, "boot_ci": [dlo, dhi]})

    rows.sort(key=lambda r: r["log_loss"])
    out = {"meta": {"train": len(tr), "test": len(te), "cutoff": str(cut.date()),
                    "base_rate_test": float(yte.mean()), "n_feats": len(feats),
                    "rho0": float(rho0), "r_H": float(rH0), "r_A": float(rA0),
                    "baseline_log_loss": base_ll, **extra},
           "resultados": rows}
    (OUT_DIR / "btts_experimentos.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- tabela no stdout ----------------------------------------------------
    print("\n" + "=" * 110)
    print(f"{'#':>2}  {'modelo':<42} {'logloss':>9} {'d_ll':>9} {'brier':>8} {'ece':>7} {'auc':>7} {'win%':>6}")
    print("-" * 110)
    for i, r in enumerate(rows):
        flag = " *" if (r["d_logloss"] < 0 and r["boot_winrate"] >= 0.9) else ""
        print(f"{i:>2}  {r['modelo']:<42} {r['log_loss']:>9.5f} {r['d_logloss']:>+9.5f} "
              f"{r['brier']:>8.5f} {r['ece']:>7.4f} {r['auc']:>7.4f} {r['boot_winrate']*100:>5.0f}%{flag}")
    print("=" * 110)
    print(f"baseline (produção) log-loss = {base_ll:.5f}  | '*' = melhora com winrate bootstrap >= 90%")
    print(f"JSON salvo em {OUT_DIR/'btts_experimentos.json'}")


if __name__ == "__main__":
    main()
