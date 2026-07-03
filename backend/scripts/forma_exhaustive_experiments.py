#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/forma_exhaustive_experiments.py
================================================
Bateria EXAUSTIVA de experimentos sobre a forma-por-jogo (pergame_form.parquet):
descobrir se/como as features de jogadores (rating, minutos, fadiga, momentum,
xG/xGA de clube, disponibilidade) complementam o Elo na previsão de RESULTADO (H/D/A).

- Dezenas de FEATURE SETS (teorias): Elo-only (baseline), cada grupo isolado, combos,
  ortogonalização vs Elo (leakage-free por fold), xG-líquido, disponibilidade ponderada,
  per-team vs diff, interações com cobertura, etc.
- Vários MODELOS com grade de hiperparâmetros: LogisticRegression (C), HistGradientBoosting
  (depth/iter/lr/leaf), RandomForest (n/depth).
- 4 SUBCONJUNTOS por cobertura/equilíbrio.
- Avaliação PAREADA: mesmos folds (RepeatedStratifiedKFold 5x3) -> delta de log-loss vs
  o baseline Elo do MESMO modelo (isola a contribuição das features). + split temporal.
- Métricas: log-loss (primária), ECE multiclasse, acurácia. Salva CSV com tudo.

Uso: python backend/scripts/forma_exhaustive_experiments.py
"""
from __future__ import annotations
import warnings, itertools, time, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "player_ranking" / "data" / "processed" / "pergame_form.parquet"
OUTDIR = ROOT / "data" / "reports"
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUTDIR / "forma_experiments_results.csv"
CLASSES = ["A", "D", "H"]

# --------------------------------------------------------------------------- dados + engenharia
def load_data():
    d = pd.read_parquet(DATA).copy()
    d = d.dropna(subset=["result", "elo_diff"]).reset_index(drop=True)
    if "neutral" not in d.columns:
        d["neutral"] = 0.0
    # engenharia determinística (sem leakage)
    d["xg_net_for_diff"] = d["diff_form_xg_for"] - d["diff_form_xg_against"]
    d["home_xg_net"] = d["home_form_xg_for"] - d["home_form_xg_against"]
    d["away_xg_net"] = d["away_form_xg_for"] - d["away_form_xg_against"]
    d["unavail_count_diff"] = d["home_unavail_count"] - d["away_unavail_count"]
    # interações com cobertura (sinal só "vale" onde há dado)
    mincov = d[["home_coverage", "away_coverage"]].min(axis=1).fillna(0.0)
    d["min_cov"] = mincov
    d["rating_x_cov"] = d["diff_form_rating"].fillna(0) * mincov
    d["xgnet_x_cov"] = d["xg_net_for_diff"].fillna(0) * mincov
    return d

# grupos de features (todas já existem ou foram engenheiradas acima)
G = {
    "elo": ["elo_diff"],
    "rating": ["diff_form_rating"],
    "minutes": ["diff_form_minutes"],
    "fatigue": ["diff_form_games30"],
    "trend": ["diff_form_trend"],
    "xg": ["diff_form_xg_for", "diff_form_xg_against"],
    "xgnet": ["xg_net_for_diff"],
    "avail": ["diff_unavail_rate"],
    "availfull": ["home_unavail_rate", "away_unavail_rate", "unavail_count_diff"],
    "cov": ["home_coverage", "away_coverage"],
    "covint": ["rating_x_cov", "xgnet_x_cov"],
    "perteam_rating": ["home_form_rating", "away_form_rating"],
    "perteam_xg": ["home_form_xg_for", "home_form_xg_against", "away_form_xg_for", "away_form_xg_against"],
    "context": ["tournament_weight", "neutral"] ,
}

# FEATURE SETS (teorias). residualize=lista de cols a ortogonalizar vs elo_diff (por fold)
def build_feature_sets():
    fs = {}
    def add(name, groups, residualize=None):
        feats = []
        for g in groups:
            feats += G[g]
        # dedup preservando ordem
        seen = set(); feats = [f for f in feats if not (f in seen or seen.add(f))]
        fs[name] = {"feats": feats, "resid": residualize or []}
    add("00_ELO_baseline", ["elo"])
    add("01_elo+rating", ["elo", "rating"])
    add("02_elo+xg", ["elo", "xg"])
    add("03_elo+xgnet", ["elo", "xgnet"])
    add("04_elo+avail", ["elo", "avail"])
    add("05_elo+availfull", ["elo", "availfull"])
    add("06_elo+fatigue", ["elo", "minutes", "fatigue"])
    add("07_elo+trend", ["elo", "trend"])
    add("08_elo+ALLform", ["elo", "rating", "minutes", "fatigue", "trend", "xg", "avail"])
    add("09_ALLform_only", ["rating", "minutes", "fatigue", "trend", "xg", "avail"])
    add("10_elo+rating+xg+avail", ["elo", "rating", "xg", "avail"])
    add("11_elo+xgnet+avail+trend", ["elo", "xgnet", "avail", "trend"])
    add("12_elo+perteam_rating", ["elo", "perteam_rating"])
    add("13_elo+perteam_xg", ["elo", "perteam_xg"])
    add("14_elo+covint", ["elo", "covint"])
    add("15_elo+ALLform+cov", ["elo", "rating", "minutes", "fatigue", "trend", "xg", "avail", "cov"])
    add("16_elo+context+ALLform", ["elo", "context", "rating", "minutes", "fatigue", "trend", "xg", "avail"])
    # ortogonalizadas (resíduo vs elo) — a hipótese ortogonal-por-construção
    add("17_elo+resid_rating", ["elo", "rating"], residualize=["diff_form_rating"])
    add("18_elo+resid_xgnet", ["elo", "xgnet"], residualize=["xg_net_for_diff"])
    add("19_elo+resid_ALLform", ["elo", "rating", "minutes", "fatigue", "trend", "xg", "avail"],
        residualize=["diff_form_rating", "diff_form_minutes", "diff_form_games30", "diff_form_trend",
                     "diff_form_xg_for", "diff_form_xg_against", "diff_unavail_rate"])
    add("20_elo+resid_rating+resid_xgnet+avail", ["elo", "rating", "xgnet", "avail"],
        residualize=["diff_form_rating", "xg_net_for_diff", "diff_unavail_rate"])
    return fs

# --------------------------------------------------------------------------- modelos
def model_grid():
    grid = []
    for C in [0.1, 0.3, 1.0, 3.0]:
        grid.append((f"LR_C{C}", "lr", {"C": C}))
    for md, mi, lr, leaf in itertools.product([2, 3], [200, 400], [0.03, 0.06], [20, 40]):
        grid.append((f"HGB_d{md}_i{mi}_lr{lr}_l{leaf}", "hgb",
                     {"max_depth": md, "max_iter": mi, "learning_rate": lr, "min_samples_leaf": leaf}))
    for n, md in itertools.product([300, 600], [4, 8]):
        grid.append((f"RF_n{n}_d{md}", "rf", {"n_estimators": n, "max_depth": md}))
    return grid

def make_model(kind, params):
    if kind == "hgb":
        return HistGradientBoostingClassifier(random_state=42, **params)
    if kind == "rf":
        return Pipeline([("imp", SimpleImputer(strategy="median")),
                         ("rf", RandomForestClassifier(random_state=42, n_jobs=1, **params))])
    return Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler()),
                     ("lr", LogisticRegression(max_iter=3000, **params))])

# --------------------------------------------------------------------------- métricas
def ece_mc(y_str, P, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1); vals = []
    for i, c in enumerate(CLASSES):
        yb = (np.asarray(y_str) == c).astype(float); pb = P[:, i]; e = 0.0
        for b in range(n_bins):
            m = (pb >= edges[b]) & (pb < edges[b + 1])
            if m.mean() > 0:
                e += m.mean() * abs(yb[m].mean() - pb[m].mean())
        vals.append(e)
    return float(np.mean(vals))

def align(P, classes):
    cls = list(classes); Pa = np.zeros((P.shape[0], 3))
    for j, c in enumerate(CLASSES):
        if c in cls:
            Pa[:, j] = P[:, cls.index(c)]
    return Pa / Pa.sum(axis=1, keepdims=True)

def residualize_fold(Xtr, Xte, elo_tr, elo_te, cols, colidx):
    Xtr, Xte = Xtr.copy(), Xte.copy()
    for c in cols:
        if c not in colidx:
            continue
        j = colidx[c]
        mask = ~np.isnan(Xtr[:, j]) & ~np.isnan(elo_tr)
        if mask.sum() < 10:
            continue
        lr = LinearRegression().fit(elo_tr[mask].reshape(-1, 1), Xtr[mask, j])
        Xtr[:, j] = Xtr[:, j] - lr.predict(elo_tr.reshape(-1, 1))
        Xte[:, j] = Xte[:, j] - lr.predict(elo_te.reshape(-1, 1))
    return Xtr, Xte

# --------------------------------------------------------------------------- avaliação
def eval_subset(df, fsets, grid, subset_name, rows, done):
    y = df["result"].astype(str).to_numpy()
    elo = df["elo_diff"].to_numpy(float)
    skf = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=42)
    folds = list(skf.split(np.zeros(len(y)), y))
    for mname, kind, params in grid:
        if (subset_name, mname) in done:
            print(f"  [{subset_name}] modelo {mname} (já feito, pulando)", flush=True)
            continue
        # baseline elo p/ este modelo (folds pareados)
        base_fold_ll = None
        for fsname, spec in fsets.items():
            feats = [f for f in spec["feats"] if f in df.columns]
            colidx = {f: i for i, f in enumerate(feats)}
            X = df[feats].to_numpy(float)
            lls, eces, accs = [], [], []
            for (tr, te) in folds:
                Xtr, Xte = X[tr], X[te]
                if spec["resid"]:
                    Xtr, Xte = residualize_fold(Xtr, Xte, elo[tr], elo[te], spec["resid"], colidx)
                m = make_model(kind, params).fit(Xtr, y[tr])
                Pa = align(m.predict_proba(Xte), m.classes_)
                lls.append(log_loss(y[te], Pa, labels=CLASSES))
                eces.append(ece_mc(y[te], Pa))
                accs.append(accuracy_score(y[te], [CLASSES[i] for i in Pa.argmax(1)]))
            lls = np.array(lls)
            if fsname == "00_ELO_baseline":
                base_fold_ll = lls.copy()
            delta = float((lls - base_fold_ll).mean()) if base_fold_ll is not None else 0.0
            win = int((lls < base_fold_ll).sum()) if base_fold_ll is not None else 0
            rows.append({
                "subset": subset_name, "n": len(df), "model": mname, "kind": kind,
                "feature_set": fsname, "n_feats": len(feats),
                "cv_logloss": float(lls.mean()), "cv_logloss_sd": float(lls.std()),
                "cv_ece": float(np.mean(eces)), "cv_acc": float(np.mean(accs)),
                "delta_ll_vs_elo": delta, "folds_better": win, "folds_total": len(folds),
            })
        # checkpoint por modelo (resumível a re-execuções, sobrevive a interrupções)
        pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
        print(f"  [{subset_name}] modelo {mname} OK ({len(rows)} linhas salvas)", flush=True)

def main():
    t0 = time.time()
    d = load_data()
    fsets = build_feature_sets()
    grid = model_grid()
    print(f"N total={len(d)} | feature_sets={len(fsets)} | modelos={len(grid)} | "
          f"configs/subset={len(fsets)*len(grid)}", flush=True)
    subsets = [
        ("COMPLETO", d),
        ("cov>=0.5", d[d["min_cov"] >= 0.5]),
        ("cov>=0.7", d[d["min_cov"] >= 0.7]),
        ("equilibrados |elo|<=100 & cov>=0.5", d[(d["elo_diff"].abs() <= 100) & (d["min_cov"] >= 0.5)]),
    ]
    # retomada: carrega o que já foi feito (resume após interrupções de sessão)
    rows, done = [], set()
    if OUT_CSV.exists():
        prev = pd.read_csv(OUT_CSV)
        rows = prev.to_dict("records")
        done = set(zip(prev["subset"], prev["model"]))
        print(f"Retomando: {len(rows)} linhas já feitas ({len(done)} combos subset×modelo).", flush=True)
    for sname, sub in subsets:
        sub = sub.reset_index(drop=True)
        print(f"\n=== SUBCONJUNTO {sname} (N={len(sub)}) ===", flush=True)
        if len(sub) < 80:
            print("  (N insuficiente — pulado)", flush=True); continue
        eval_subset(sub, fsets, grid, sname, rows, done)
    res = pd.DataFrame(rows)
    res.to_csv(OUT_CSV, index=False)
    print(f"\nFEITO em {(time.time()-t0)/60:.1f} min | {len(res)} resultados -> {OUT_CSV}", flush=True)

if __name__ == "__main__":
    main()
