#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/xg_club_experiment.py
=====================================
PROXIMO PASSO #5 — xG DE CLUBE (form_xg_for/against, ja coletado em pergame_form)
agrega ALEM do base_feats da producao, sob o gate temporal honesto?

Duas frentes, mesma maquina de validacao das baterias anteriores:
  (A) MERCADOS DE CONTAGEM (gols, finalizacoes, finalizacoes a gol, escanteios):
      GBR + NB de producao; base_feats vs base_feats+xG_clube; CV temporal expanding;
      COMPARACAO JUSTA -> restringe as MESMAS linhas onde o xG existe.
  (B) RESULTADO (H/D/A): base_feats vs base_feats+xG_clube (LR e HGB), CV temporal.

Segmentado (equilibrio/competicao/continente/cobertura). Gate: reduzir LogLoss vs
producao SEM piorar ECE, consistente em folds E segmentos. Saidas em data/reports/.
Resumivel (checkpoint por mercado/lado escrito a cada passo).
"""
from __future__ import annotations
import warnings, json
from pathlib import Path
import sys
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import log_loss, accuracy_score

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
FORMA = ROOT / "player_ranking" / "data" / "processed" / "pergame_form.parquet"
OUT_C = ROOT / "data" / "reports" / "xg_club_counts.csv"
OUT_R = ROOT / "data" / "reports" / "xg_club_result.csv"
CLASSES = ["A", "D", "H"]

XG_DIFF = ["diff_form_xg_for", "diff_form_xg_against"]
XG_HA = ["home_form_xg_for", "home_form_xg_against", "away_form_xg_for", "away_form_xg_against"]

# segmentadores (reuso da bateria 3)
def comp_group(t):
    t = str(t)
    if 'World Cup' in t and 'qualif' in t.lower(): return 'Eliminatorias'
    if t == 'FIFA World Cup': return 'Copa do Mundo'
    if 'Nations League' in t: return 'Nations League'
    if t in ('Friendly', 'Friendlies'): return 'Amistoso'
    if 'qualif' in t.lower(): return 'Eliminatorias'
    if any(k in t for k in ['Euro', 'Copa Am', 'African Cup', 'Asian Cup', 'Gold Cup', 'COSAFA']): return 'Continental'
    return 'Outros'

def balance(elo):
    a = abs(elo)
    return 'equilibrado' if a <= 80 else ('intermediario' if a <= 150 else 'favorito_forte')

def load_merged():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    f = pd.read_parquet(FORMA)
    xgcols = [c for c in (XG_DIFF + XG_HA) if c in f.columns] + ["home_xg_coverage", "away_xg_coverage"]
    keep = ["match_id"] + xgcols
    df = df.merge(f[keep].drop_duplicates("match_id"), on="match_id", how="left")
    return df

# ----------------------------------------------------------------- (A) contagem
def ece_ou(y, over, line):
    yb = (y > line).astype(float); e = 0.0; edges = np.linspace(0, 1, 11)
    for b in range(10):
        mk = (over >= edges[b]) & (over < edges[b + 1])
        if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - over[mk].mean())
    return float(e)

def cv_counts(sub, ch, ca, lado, feats, grade, line, seg_col=None, seg_val=None):
    cuts = np.linspace(0.5, 0.85, 4); lls, eces, maes, ns = [], [], [], []
    for c in cuts:
        n = int(len(sub) * c); m = int(len(sub) * min(c + 0.15, 1.0))
        tr, te = sub.iloc[:n], sub.iloc[n:m]
        if seg_col is not None:
            te = te[te[seg_col] == seg_val]
        if len(te) < 25: continue
        Xtr = tr[feats]; Xte = te[feats]
        if lado == "total":
            Ph, _ = M.build_pmf("gbr", "nb", Xtr, tr[ch].astype(int).values, Xte, grade)
            Pa, _ = M.build_pmf("gbr", "nb", Xtr, tr[ca].astype(int).values, Xte, grade)
            P = np.zeros((len(te), 2 * grade + 1))
            for i in range(len(te)): P[i] = np.convolve(Ph[i], Pa[i])
            y = te[ch].astype(int).values + te[ca].astype(int).values
            mean = Ph @ np.arange(grade + 1) + Pa @ np.arange(grade + 1)
        else:
            col = ch if lado == "mandante" else ca
            y = te[col].astype(int).values
            P, mean = M.build_pmf("gbr", "nb", Xtr, tr[col].astype(int).values, Xte, grade)
        idx = np.clip(y, 0, P.shape[1] - 1)
        lls.append(float(-np.mean(np.log(P[np.arange(len(y)), idx] + 1e-15))))
        over = P[:, int(np.floor(line)) + 1:].sum(1)
        eces.append(ece_ou(y, over, line)); maes.append(float(np.mean(np.abs(y - mean)))); ns.append(len(te))
    if not lls: return None
    return np.mean(lls), np.std(lls), np.mean(eces), np.mean(maes), int(np.mean(ns))

def run_counts():
    df = load_merged()
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    xg_diff = [c for c in XG_DIFF if c in adv.columns]
    xg_all = [c for c in (XG_DIFF + XG_HA) if c in adv.columns]
    MARKETS = [
        ("gols", "home_score", "away_score", 2.5, 12),
        ("finalizacoes", "home_cur_sb_shots", "away_cur_sb_shots", 22.5, 55),
        ("finalizacoes_gol", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 7.5, 30),
        ("escanteios", "home_cur_sb_corners", "away_cur_sb_corners", 9.5, 25),
    ]
    rows = []
    for mkt, ch, ca, line, grade in MARKETS:
        sub = adv.dropna(subset=[ch, ca]).reset_index(drop=True)
        # comparacao JUSTA: somente linhas com xG presente
        sub_xg = sub.dropna(subset=xg_diff).reset_index(drop=True)
        sub_xg["comp"] = sub_xg["tournament"].map(comp_group)
        sub_xg["bal"] = sub_xg["elo_diff"].map(balance)
        n_full, n_xg = len(sub), len(sub_xg)
        for lado, ln in [("mandante", line / 2), ("visitante", line / 2), ("total", line)]:
            for fsname, feats in [("base", M.FEATS), ("base+xg_diff", M.FEATS + xg_diff),
                                  ("base+xg_all", M.FEATS + xg_all)]:
                r = cv_counts(sub_xg, ch, ca, lado, feats, grade, ln)
                if r is None: continue
                ll, sd, ece, mae, nt = r
                rows.append({"mercado": mkt, "lado": lado, "seg": "todos", "feature_set": fsname,
                             "n_full": n_full, "n_xg": n_xg, "cv_logloss": ll, "cv_ll_sd": sd,
                             "cv_ece": ece, "cv_mae": mae, "n_test_avg": nt})
            # segmentos (so base vs base+xg_diff p/ enxugar)
            for seg_col in ["bal", "comp"]:
                for seg_val in sorted(sub_xg[seg_col].dropna().unique()):
                    if (sub_xg[seg_col] == seg_val).sum() < 150: continue
                    for fsname, feats in [("base", M.FEATS), ("base+xg_diff", M.FEATS + xg_diff)]:
                        r = cv_counts(sub_xg, ch, ca, lado, feats, grade, ln, seg_col, seg_val)
                        if r is None: continue
                        ll, sd, ece, mae, nt = r
                        rows.append({"mercado": mkt, "lado": lado, "seg": f"{seg_col}={seg_val}",
                                     "feature_set": fsname, "n_full": n_full, "n_xg": n_xg,
                                     "cv_logloss": ll, "cv_ll_sd": sd, "cv_ece": ece, "cv_mae": mae, "n_test_avg": nt})
            pd.DataFrame(rows).to_csv(OUT_C, index=False)
            print(f"[counts {mkt}/{lado}] ok  (N_full={n_full} N_xg={n_xg})", flush=True)
    print(f"FEITO counts -> {OUT_C}", flush=True)

# ----------------------------------------------------------------- (B) resultado
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

def make_clf(kind):
    if kind == "hgb":
        return HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05,
                                              min_samples_leaf=30, random_state=42)
    return Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler()),
                     ("lr", LogisticRegression(max_iter=3000, C=1.0))])

def run_result():
    df = load_merged()
    csv = df.copy()
    # alvo de resultado
    if "result" not in csv.columns:
        csv["result"] = np.where(csv["home_score"] > csv["away_score"], "H",
                          np.where(csv["home_score"] < csv["away_score"], "A", "D"))
    base_in = [c for c in M.FEATS if c in csv.columns]
    xg_diff = [c for c in XG_DIFF if c in csv.columns]
    seg = csv.dropna(subset=xg_diff + ["result"]).sort_values("date").reset_index(drop=True)
    seg["min_xgcov"] = seg[["home_xg_coverage", "away_xg_coverage"]].min(axis=1).fillna(0)
    print(f"[result] N com xG={len(seg)} | base_feats={len(base_in)}", flush=True)
    cuts = np.linspace(0.5, 0.85, 4)
    rows = []
    for seg_name, sg in [("todos", seg), ("alta_xgcov(>=0.6)", seg[seg.min_xgcov >= 0.6]),
                         ("equilibrados|elo|<=100", seg[seg.elo_diff.abs() <= 100])]:
        sg = sg.sort_values("date").reset_index(drop=True)
        if len(sg) < 150:
            rows.append({"segmento": seg_name, "n": len(sg), "obs": "N insuficiente"}); continue
        for kind in ["lr", "hgb"]:
            for setname, feats in [("base_feats", base_in), ("base+xg", base_in + xg_diff)]:
                feats = [c for c in feats if c in sg.columns]
                lls, eces, accs = [], [], []
                for c in cuts:
                    n = int(len(sg) * c); m = int(len(sg) * min(c + 0.15, 1.0))
                    tr, te = sg.iloc[:n], sg.iloc[n:m]
                    if len(te) < 25: continue
                    Xtr = tr[feats].to_numpy(float); Xte = te[feats].to_numpy(float)
                    ytr = tr["result"].astype(str).to_numpy(); yte = te["result"].astype(str).to_numpy()
                    mdl = make_clf(kind).fit(Xtr, ytr); Pa = align(mdl.predict_proba(Xte), mdl.classes_)
                    lls.append(log_loss(yte, Pa, labels=CLASSES)); eces.append(ece_mc(yte, Pa))
                    accs.append(accuracy_score(yte, [CLASSES[i] for i in Pa.argmax(1)]))
                rows.append({"segmento": seg_name, "n": len(sg), "modelo": kind, "feature_set": setname,
                             "cv_logloss": float(np.mean(lls)), "cv_ll_sd": float(np.std(lls)),
                             "cv_ece": float(np.mean(eces)), "cv_acc": float(np.mean(accs))})
        pd.DataFrame(rows).to_csv(OUT_R, index=False)
        print(f"[result {seg_name}] ok", flush=True)
    print(f"FEITO result -> {OUT_R}", flush=True)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["counts", "result"], default=None)
    a = ap.parse_args()
    if a.only in (None, "counts"): run_counts()
    if a.only in (None, "result"): run_result()
