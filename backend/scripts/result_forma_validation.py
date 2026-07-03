#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/result_forma_validation.py
===========================================
Parte 1, item 1 — gate honesto do RESULTADO (H/D/A) com forma de jogador.
Pergunta: a forma (rating residualizado + trend) agrega ALÉM do que a produção já usa?
A produção (Dixon-Coles) usa base_feats — que JÁ contém forma de resultado (gd_l5, ppg...).
Então o teste justo é: base_feats vs base_feats + forma, sob CV temporal, leakage-safe
(residualização de rating vs elo por fold). Também reporta o teste 'elo-only vs +forma'
do relatório 1, para reconciliar.

Saída: backend/data/reports/result_forma_validation.csv
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
OUT = ROOT / "data" / "reports" / "result_forma_validation.csv"
CLASSES = ["A", "D", "H"]

def ece_mc(y, P, nb=10):
    edges = np.linspace(0, 1, nb+1); vals=[]
    for i, c in enumerate(CLASSES):
        yb=(np.asarray(y)==c).astype(float); pb=P[:,i]; e=0.0
        for b in range(nb):
            m=(pb>=edges[b])&(pb<edges[b+1])
            if m.mean()>0: e+=m.mean()*abs(yb[m].mean()-pb[m].mean())
        vals.append(e)
    return float(np.mean(vals))

def align(P, classes):
    cls=list(classes); Pa=np.zeros((P.shape[0],3))
    for j,c in enumerate(CLASSES):
        if c in cls: Pa[:,j]=P[:,cls.index(c)]
    return Pa/Pa.sum(axis=1,keepdims=True)

def make(kind):
    if kind=="hgb": return HistGradientBoostingClassifier(max_depth=3,max_iter=300,learning_rate=0.05,min_samples_leaf=30,random_state=42)
    return Pipeline([("imp",SimpleImputer(strategy="median")),("sc",StandardScaler()),("lr",LogisticRegression(max_iter=3000,C=1.0))])

def main():
    f = pd.read_parquet(FORMA)
    csv = pd.read_csv(CSV, low_memory=False)
    # juntar base_feats por match_id
    keep = ["match_id"] + [c for c in BASE if c in csv.columns]
    df = f.merge(csv[keep], on="match_id", how="left", suffixes=("", "_csv")).dropna(subset=["result"]).sort_values("date").reset_index(drop=True)
    base_in = [c for c in BASE if c in df.columns]
    df["min_cov"] = df[["home_coverage","away_coverage"]].min(axis=1).fillna(0)
    print(f"N={len(df)} | base_feats disponíveis: {len(base_in)} | forma cols ok", flush=True)

    FORMA_FEATS = ["diff_form_rating","diff_form_trend"]  # rating(residualizado)+trend, conforme item 1
    cuts = np.linspace(0.5,0.85,4)
    rows=[]
    for seg_name, seg in [("todos", df), ("alta_cov(>=0.7)", df[df.min_cov>=0.7]), ("equilibrados|elo|<=100", df[df.elo_diff.abs()<=100])]:
        seg = seg.sort_values("date").reset_index(drop=True)
        if len(seg) < 120:
            rows.append({"segmento":seg_name,"n":len(seg),"obs":"N insuficiente"}); continue
        for kind in ["lr","hgb"]:
            for setname, feats, resid in [
                ("ELO", ["elo_diff"], []),
                ("ELO+forma", ["elo_diff"]+FORMA_FEATS, ["diff_form_rating"]),
                ("base_feats", base_in, []),
                ("base+forma", base_in+FORMA_FEATS, ["diff_form_rating"]),
            ]:
                feats=[c for c in feats if c in seg.columns]; colidx={c:i for i,c in enumerate(feats)}
                lls,eces,accs=[],[],[]
                for c in cuts:
                    n=int(len(seg)*c); m=int(len(seg)*min(c+0.15,1.0))
                    tr,te=seg.iloc[:n],seg.iloc[n:m]
                    if len(te)<25: continue
                    Xtr=tr[feats].to_numpy(float).copy(); Xte=te[feats].to_numpy(float).copy()
                    ytr=tr["result"].astype(str).to_numpy(); yte=te["result"].astype(str).to_numpy()
                    elotr=tr["elo_diff"].to_numpy(float); elote=te["elo_diff"].to_numpy(float)
                    for rc in resid:
                        if rc in colidx:
                            j=colidx[rc]; mk=~np.isnan(Xtr[:,j])&~np.isnan(elotr)
                            if mk.sum()>10:
                                lr=LinearRegression().fit(elotr[mk].reshape(-1,1),Xtr[mk,j])
                                Xtr[:,j]=Xtr[:,j]-lr.predict(elotr.reshape(-1,1)); Xte[:,j]=Xte[:,j]-lr.predict(elote.reshape(-1,1))
                    mdl=make(kind).fit(Xtr,ytr); Pa=align(mdl.predict_proba(Xte),mdl.classes_)
                    lls.append(log_loss(yte,Pa,labels=CLASSES)); eces.append(ece_mc(yte,Pa))
                    accs.append(accuracy_score(yte,[CLASSES[i] for i in Pa.argmax(1)]))
                rows.append({"segmento":seg_name,"n":len(seg),"modelo":kind,"feature_set":setname,
                             "cv_logloss":float(np.mean(lls)),"cv_ll_sd":float(np.std(lls)),
                             "cv_ece":float(np.mean(eces)),"cv_acc":float(np.mean(accs))})
        pd.DataFrame(rows).to_csv(OUT,index=False)
        print(f"  segmento {seg_name} ok", flush=True)
    pd.DataFrame(rows).to_csv(OUT,index=False)
    print(f"FEITO -> {OUT}", flush=True)

if __name__=="__main__":
    main()
