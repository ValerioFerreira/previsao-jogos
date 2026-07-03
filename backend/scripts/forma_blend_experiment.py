#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/forma_blend_experiment.py
=========================================
PROXIMO PASSO #6 — forma de jogador como BLEND de alta cobertura no RESULTADO
(H/D/A), NAO como substituicao. Hipotese: o sinalzinho da forma so aparece onde a
cobertura e alta; entao em vez de concatenar features (que diluem onde a cobertura
e baixa e foram REPROVADAS no relatorio 3), misturamos distribuicoes:

    P_final = (1 - w_i) * P_base + w_i * P_forma
    w_i = w0 * min(cov_home_i, cov_away_i)      # confia na forma so onde ha cobertura

P_base  = modelo so com base_feats (producao).
P_forma = modelo com base_feats + forma (rating residualizado, trend, fadiga, lesoes).
w0 e calibrado FORWARD (escolhido nos folds passados, aplicado no proximo) -> sem leakage.

Gate temporal expanding (cuts 0.5..0.85). Compara LogLoss/ECE/acc: base vs blend.
Saida: backend/data/reports/forma_blend_result.csv
"""
from __future__ import annotations
import warnings, json
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import log_loss, accuracy_score

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
FORMA = ROOT / "player_ranking" / "data" / "processed" / "pergame_form.parquet"
CSV = ROOT / "international_features_enriched_apifootball.csv"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE = [f for f in META["base_feats"]]
OUT = ROOT / "data" / "reports" / "forma_blend_result.csv"
CLASSES = ["A", "D", "H"]
FORMA_FEATS = ["diff_form_rating", "diff_form_trend", "diff_form_games30", "diff_unavail_rate"]
RESID = ["diff_form_rating"]

def ece_mc(y, P, nb=10):
    edges = np.linspace(0, 1, nb + 1); vals = []
    for i, c in enumerate(CLASSES):
        yb = (np.asarray(y) == c).astype(float); pb = P[:, i]; e = 0.0
        for b in range(nb):
            mk = (pb >= edges[b]) & (pb < edges[b + 1])
            if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - pb[mk].mean())
        vals.append(e)
    return float(np.mean(vals))

def align(P, classes):
    cls = list(classes); Pa = np.zeros((P.shape[0], 3))
    for j, c in enumerate(CLASSES):
        if c in cls: Pa[:, j] = P[:, cls.index(c)]
    return Pa / Pa.sum(axis=1, keepdims=True)

def make(kind):
    if kind == "hgb":
        return HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05,
                                              min_samples_leaf=30, random_state=42)
    return Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler()),
                     ("lr", LogisticRegression(max_iter=3000, C=1.0))])

def resid_fit(Xtr, Xte, feats, colidx, elotr, elote):
    Xtr = Xtr.copy(); Xte = Xte.copy()
    for rc in RESID:
        if rc in colidx:
            j = colidx[rc]; mk = ~np.isnan(Xtr[:, j]) & ~np.isnan(elotr)
            if mk.sum() > 10:
                lr = LinearRegression().fit(elotr[mk].reshape(-1, 1), Xtr[mk, j])
                Xtr[:, j] = Xtr[:, j] - lr.predict(elotr.reshape(-1, 1))
                Xte[:, j] = Xte[:, j] - lr.predict(elote.reshape(-1, 1))
    return Xtr, Xte

def fit_predict(kind, feats, tr, te):
    colidx = {c: i for i, c in enumerate(feats)}
    Xtr = tr[feats].to_numpy(float); Xte = te[feats].to_numpy(float)
    elotr = tr["elo_diff"].to_numpy(float); elote = te["elo_diff"].to_numpy(float)
    Xtr, Xte = resid_fit(Xtr, Xte, feats, colidx, elotr, elote)
    mdl = make(kind).fit(Xtr, tr["result"].astype(str).to_numpy())
    return align(mdl.predict_proba(Xte), mdl.classes_)

def main():
    f = pd.read_parquet(FORMA)
    csv = pd.read_csv(CSV, low_memory=False)
    in_f = set(f.columns)  # evita colisao elo_diff_x/_y: mantem versao do parquet p/ overlaps
    keep = ["match_id"] + [c for c in BASE if c in csv.columns and c not in in_f]
    df = f.merge(csv[keep].drop_duplicates("match_id"), on="match_id", how="left")
    df = df.dropna(subset=["result"]).sort_values("date").reset_index(drop=True)
    base_in = [c for c in BASE if c in df.columns]
    forma_in = [c for c in FORMA_FEATS if c in df.columns]
    df["min_cov"] = df[["home_coverage", "away_coverage"]].min(axis=1).fillna(0.0)
    print(f"N={len(df)} base_feats={len(base_in)} forma={forma_in}", flush=True)

    cuts = np.linspace(0.5, 0.85, 4)
    W0_GRID = [0.0, 0.15, 0.3, 0.5, 0.75, 1.0]
    rows = []
    for seg_name, sg in [("todos", df), ("alta_cov(>=0.7)", df[df.min_cov >= 0.7]),
                         ("equilibrados|elo|<=100", df[df.elo_diff.abs() <= 100])]:
        sg = sg.sort_values("date").reset_index(drop=True)
        if len(sg) < 150:
            rows.append({"segmento": seg_name, "n": len(sg), "obs": "N insuf"}); continue
        for kind in ["lr", "hgb"]:
            base_lls, blend_lls, base_eces, blend_eces, base_accs, blend_accs, w_used = [], [], [], [], [], [], []
            prev_best_w = 0.0  # forward: comeca neutro
            for c in cuts:
                n = int(len(sg) * c); m = int(len(sg) * min(c + 0.15, 1.0))
                tr, te = sg.iloc[:n], sg.iloc[n:m]
                if len(te) < 25: continue
                yte = te["result"].astype(str).to_numpy()
                Pb = fit_predict(kind, base_in, tr, te)
                Pf = fit_predict(kind, base_in + forma_in, tr, te)
                cov = te["min_cov"].to_numpy(float)
                # calibra w0 DENTRO do treino (split interno temporal), guarda p/ aplicar aqui
                ni = int(len(tr) * 0.8)
                tri, tei = tr.iloc[:ni], tr.iloc[ni:]
                best_w = prev_best_w
                if len(tei) >= 25:
                    Pbi = fit_predict(kind, base_in, tri, tei)
                    Pfi = fit_predict(kind, base_in + forma_in, tri, tei)
                    covi = tei["min_cov"].to_numpy(float); yi = tei["result"].astype(str).to_numpy()
                    best_ll, best_w = 1e9, 0.0
                    for w0 in W0_GRID:
                        wi = (w0 * covi).clip(0, 1)[:, None]
                        Pm = (1 - wi) * Pbi + wi * Pfi
                        Pm = Pm / Pm.sum(1, keepdims=True)
                        ll = log_loss(yi, Pm, labels=CLASSES)
                        if ll < best_ll: best_ll, best_w = ll, w0
                    prev_best_w = best_w
                wv = (best_w * cov).clip(0, 1)[:, None]
                Pm = (1 - wv) * Pb + wv * Pf; Pm = Pm / Pm.sum(1, keepdims=True)
                base_lls.append(log_loss(yte, Pb, labels=CLASSES)); blend_lls.append(log_loss(yte, Pm, labels=CLASSES))
                base_eces.append(ece_mc(yte, Pb)); blend_eces.append(ece_mc(yte, Pm))
                base_accs.append(accuracy_score(yte, [CLASSES[i] for i in Pb.argmax(1)]))
                blend_accs.append(accuracy_score(yte, [CLASSES[i] for i in Pm.argmax(1)]))
                w_used.append(best_w)
            rows.append({"segmento": seg_name, "n": len(sg), "modelo": kind,
                         "base_ll": float(np.mean(base_lls)), "blend_ll": float(np.mean(blend_lls)),
                         "dLL": float(np.mean(blend_lls) - np.mean(base_lls)),
                         "base_ece": float(np.mean(base_eces)), "blend_ece": float(np.mean(blend_eces)),
                         "base_acc": float(np.mean(base_accs)), "blend_acc": float(np.mean(blend_accs)),
                         "w0_medio": float(np.mean(w_used))})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        print(f"[{seg_name}] ok", flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
