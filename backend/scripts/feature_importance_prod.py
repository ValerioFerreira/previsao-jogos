#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/feature_importance_prod.py
==========================================
PROXIMO PASSO #4 — interpretabilidade dos MODELOS DE PRODUCAO (nao surrogates).
Importancia por PERMUTACAO calculada sobre os artefatos deployados de fato
(ShotsNB, CornersNB, ShotsOnTargetNB, CardsGP, DixonColesNB), avaliada num
HOLDOUT TEMPORAL (ultimos 25% por data), com a metrica nativa de cada mercado:
  - contagem -> log-loss da PMF marginal (home+away) no valor observado
  - resultado -> log-loss multiclasse (A/D/H) do Dixon-Coles
Para cada feature: delta(LL) = LL(feature embaralhada) - LL(base), media de n_rep
embaralhamentos. Ranqueia. Saida: data/reports/feature_importance_prod.csv (+ resumo).
"""
from __future__ import annotations
import warnings, json, sys
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.metrics import log_loss

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # modelos picklados (shots_nb_model, corners_nb_model, ...) na raiz do backend
from ortho_sinais import apply_ortho_residuals  # mesma transformacao de estilo do treino/inferencia
from corner_interactions import add_corner_interactions
ORTHO_W = joblib.load(ROOT / "model_artifacts" / "style_ortho_weights.joblib")
OOF_SHOTS = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")

def enrich_cascade(te):
    """Reproduz features do cascade de escanteios: pred shots OOF + interacoes rha_x_*."""
    te = te.merge(OOF_SHOTS, on="match_id", how="left")
    if "pred_home_shots_oof" in te.columns:
        te["pred_home_shots"] = te["pred_home_shots_oof"]
        te["pred_away_shots"] = te["pred_away_shots_oof"]
    te = add_corner_interactions(te)
    return te
ART = ROOT / "model_artifacts"
CSV = ROOT / "international_features_enriched_apifootball.csv"
OUT = ROOT / "data" / "reports" / "feature_importance_prod.csv"
RNG = np.random.default_rng(42)
N_REP = 4

def count_ll_marginal(model, X, yh, ya):
    d = model.predict_distributions(X)
    Ph, Pa = d["home"], d["away"]
    ih = np.clip(yh, 0, Ph.shape[1] - 1); ia = np.clip(ya, 0, Pa.shape[1] - 1)
    llh = -np.log(Ph[np.arange(len(yh)), ih] + 1e-15)
    lla = -np.log(Pa[np.arange(len(ya)), ia] + 1e-15)
    return float(np.mean(llh + lla))

def perm_importance_count(model, X, yh, ya):
    feats = list(model.feats)
    base = count_ll_marginal(model, X, yh, ya)
    rows = []
    for fcol in feats:
        deltas = []
        for _ in range(N_REP):
            Xp = X.copy()
            Xp[fcol] = RNG.permutation(Xp[fcol].values)
            deltas.append(count_ll_marginal(model, Xp, yh, ya) - base)
        rows.append((fcol, float(np.mean(deltas)), float(np.std(deltas))))
    return base, rows

def result_ll(model, X, y):
    P = model.predict_proba_markets(X)["result"]  # [A,D,H]
    P = P / P.sum(1, keepdims=True)
    return log_loss(y, P, labels=["A", "D", "H"])

def perm_importance_result(model, feats, X, y):
    base = result_ll(model, X, y)
    rows = []
    for fcol in feats:
        deltas = []
        for _ in range(N_REP):
            Xp = X.copy(); Xp[fcol] = RNG.permutation(Xp[fcol].values)
            deltas.append(result_ll(model, Xp, y) - base)
        rows.append((fcol, float(np.mean(deltas)), float(np.std(deltas))))
    return base, rows

def temporal_holdout(sub, frac=0.75):
    sub = sub.sort_values("date").reset_index(drop=True)
    n = int(len(sub) * frac)
    return sub.iloc[n:].reset_index(drop=True)

def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy()
    all_rows = []

    COUNT = [
        ("finalizacoes", "shots_nb.joblib", "home_cur_sb_shots", "away_cur_sb_shots"),
        ("escanteios", "corners_cascade_rfixo.joblib", "home_cur_sb_corners", "away_cur_sb_corners"),
        ("finalizacoes_gol", "shots_on_target_nb.joblib", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target"),
        ("cartoes", "cards_gp.joblib", "home_cur_sb_cards", "away_cur_sb_cards"),
    ]
    for mkt, art, ch, ca in COUNT:
        p = ART / art
        if not p.exists():
            print(f"[{mkt}] artefato ausente {art} — pulado", flush=True); continue
        model = joblib.load(p)
        sub = adv.dropna(subset=[ch, ca]).copy()
        te = temporal_holdout(sub)
        te = apply_ortho_residuals(te, ORTHO_W)  # gera resid_*_style_* exatamente como no treino
        if any(f not in te.columns for f in model.feats):
            te = enrich_cascade(te)  # escanteios precisa de pred-shots OOF + interacoes
        miss = [f for f in model.feats if f not in te.columns]
        if miss:
            print(f"[{mkt}] features ausentes ainda: {miss[:6]} — pulado", flush=True); continue
        X = te[model.feats].copy()
        yh = te[ch].astype(int).values; ya = te[ca].astype(int).values
        base, rows = perm_importance_count(model, X, yh, ya)
        for f, dm, ds in rows:
            all_rows.append({"mercado": mkt, "feature": f, "delta_ll": dm, "delta_ll_sd": ds,
                             "base_ll": base, "n_holdout": len(te)})
        rk = sorted(rows, key=lambda z: -z[1])[:12]
        print(f"\n[{mkt}] base_LL={base:.4f} n={len(te)} | TOP-12 features (delta_LL ao permutar):", flush=True)
        for f, dm, ds in rk:
            print(f"    {dm:+.4f}  {f}", flush=True)
        pd.DataFrame(all_rows).to_csv(OUT, index=False)

    # resultado (DC)
    dcp = ART / "dixon_coles_goals.joblib"
    if dcp.exists():
        dc = joblib.load(dcp)
        feats = list(dc.model_home_.feature_names_in_) if hasattr(dc.model_home_, "feature_names_in_") else \
                list(getattr(dc.model_home_[-1], "feature_names_in_", []))
        if not feats:
            meta = json.load(open(ART / "meta.json", encoding="utf-8")); feats = meta["base_feats"]
        full = df.copy()
        full["result"] = np.where(full["home_score"] > full["away_score"], "H",
                          np.where(full["home_score"] < full["away_score"], "A", "D"))
        full = full.dropna(subset=["result"])
        te = temporal_holdout(full)
        feats = [c for c in feats if c in te.columns]
        X = te[feats].copy(); y = te["result"].astype(str).values
        base, rows = perm_importance_result(dc, feats, X, y)
        for f, dm, ds in rows:
            all_rows.append({"mercado": "resultado", "feature": f, "delta_ll": dm, "delta_ll_sd": ds,
                             "base_ll": base, "n_holdout": len(te)})
        rk = sorted(rows, key=lambda z: -z[1])[:12]
        print(f"\n[resultado/DC] base_LL={base:.4f} n={len(te)} | TOP-12 features:", flush=True)
        for f, dm, ds in rk:
            print(f"    {dm:+.4f}  {f}", flush=True)
    pd.DataFrame(all_rows).to_csv(OUT, index=False)
    print(f"\nFEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
