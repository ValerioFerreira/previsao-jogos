#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/forma_dc_blend.py
=================================
FOLLOW-UP do item 6 (o unico sinal "ambar"): testar a forma blendada na saida do
DIXON-COLES REAL de producao (nao num proxy HGB). Mesma familia de modelo (DC), com
vs sem forma, misturados por cobertura, peso forward. Gate: reduzir LogLoss do
RESULTADO sem piorar ECE, CONSISTENTE EM TODOS OS FOLDS (incl. o mais recente).

Por fold (CV temporal expanding):
  DC_base  = DixonColesNB(base_feats).fit -> P_base[A,D,H]
  DC_forma = DixonColesNB(base_feats+forma).fit -> P_forma
  P = (1 - w*cov)*P_base + w*cov*P_forma ; w calibrado em split interno do treino.
Compara vs P_base. Saida: data/reports/forma_dc_blend.csv
"""
from __future__ import annotations
import warnings, json, sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.metrics import log_loss, accuracy_score
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
FORMA = ROOT / "player_ranking" / "data" / "processed" / "pergame_form.parquet"
CSV = ROOT / "international_features_enriched_apifootball.csv"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE = [f for f in META["base_feats"]]
OUT = ROOT / "data" / "reports" / "forma_dc_blend.csv"
CLASSES = ["A", "D", "H"]
FORMA_FEATS = ["diff_form_rating", "diff_form_trend", "diff_form_games30", "diff_unavail_rate"]

def ece_mc(y, P, nb=10):
    edges = np.linspace(0, 1, nb + 1); vals = []
    for i, c in enumerate(CLASSES):
        yb = (np.asarray(y) == c).astype(float); pb = P[:, i]; e = 0.0
        for b in range(nb):
            mk = (pb >= edges[b]) & (pb < edges[b + 1])
            if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - pb[mk].mean())
        vals.append(e)
    return float(np.mean(vals))

def fit_dc(Xtr, yh, ya):
    m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    m.fit(Xtr, yh, ya)
    return m

def dc_result(m, X):
    P = m.predict_proba_markets(X)["result"]  # [A,D,H]
    return P / P.sum(1, keepdims=True)

def main():
    f = pd.read_parquet(FORMA)
    csv = pd.read_csv(CSV, low_memory=False)
    cols = ["match_id", "home_score", "away_score"] + [c for c in BASE if c in csv.columns]
    in_f = set(f.columns)
    keep = ["match_id", "home_score", "away_score"] + [c for c in BASE if c in csv.columns and c not in in_f]
    df = f.merge(csv[keep].drop_duplicates("match_id"), on="match_id", how="left")
    df = df.dropna(subset=["home_score", "away_score", "result"]).sort_values("date").reset_index(drop=True)
    base_in = [c for c in BASE if c in df.columns]
    forma_in = [c for c in FORMA_FEATS if c in df.columns]
    df["min_cov"] = df[["home_coverage", "away_coverage"]].min(axis=1).fillna(0.0)
    print(f"N={len(df)} base={len(base_in)} forma={forma_in}", flush=True)
    cuts = np.linspace(0.5, 0.85, 4)
    W0 = [0.0, 0.25, 0.5, 0.75, 1.0]
    rows = []
    for seg_name, sg in [("todos", df), ("alta_cov(>=0.7)", df[df.min_cov >= 0.7])]:
        sg = sg.sort_values("date").reset_index(drop=True)
        if len(sg) < 150:
            rows.append({"segmento": seg_name, "n": len(sg), "obs": "N insuf"}); continue
        prev_w = 0.0
        for c in cuts:
            n = int(len(sg) * c); m = int(len(sg) * min(c + 0.15, 1.0))
            tr, te = sg.iloc[:n], sg.iloc[n:m]
            if len(te) < 25: continue
            yhtr = tr["home_score"].astype(int).values; yatr = tr["away_score"].astype(int).values
            yte = te["result"].astype(str).values; cov = te["min_cov"].to_numpy(float)
            dc_b = fit_dc(tr[base_in], yhtr, yatr)
            dc_f = fit_dc(tr[base_in + forma_in], yhtr, yatr)
            Pb = dc_result(dc_b, te[base_in]); Pf = dc_result(dc_f, te[base_in + forma_in])
            # calibra w no split interno do treino
            ni = int(len(tr) * 0.8); tri, tei = tr.iloc[:ni], tr.iloc[ni:]
            best_w = prev_w
            if len(tei) >= 25:
                yhi = tri["home_score"].astype(int).values; yai = tri["away_score"].astype(int).values
                dcb_i = fit_dc(tri[base_in], yhi, yai); dcf_i = fit_dc(tri[base_in + forma_in], yhi, yai)
                Pbi = dc_result(dcb_i, tei[base_in]); Pfi = dc_result(dcf_i, tei[base_in + forma_in])
                covi = tei["min_cov"].to_numpy(float); yi = tei["result"].astype(str).values
                best_ll = 1e9
                for w0 in W0:
                    wi = (w0 * covi).clip(0, 1)[:, None]; Pm = (1 - wi) * Pbi + wi * Pfi
                    ll = log_loss(yi, Pm / Pm.sum(1, keepdims=True), labels=CLASSES)
                    if ll < best_ll: best_ll, best_w = ll, w0
                prev_w = best_w
            wv = (best_w * cov).clip(0, 1)[:, None]; Pm = (1 - wv) * Pb + wv * Pf; Pm = Pm / Pm.sum(1, keepdims=True)
            rows.append({"segmento": seg_name, "fold": round(c, 2), "n_test": len(te), "w0": best_w,
                         "base_ll": log_loss(yte, Pb, labels=CLASSES), "blend_ll": log_loss(yte, Pm, labels=CLASSES),
                         "dLL": log_loss(yte, Pm, labels=CLASSES) - log_loss(yte, Pb, labels=CLASSES),
                         "base_ece": ece_mc(yte, Pb), "blend_ece": ece_mc(yte, Pm),
                         "base_acc": accuracy_score(yte, [CLASSES[i] for i in Pb.argmax(1)]),
                         "blend_acc": accuracy_score(yte, [CLASSES[i] for i in Pm.argmax(1)])})
            pd.DataFrame(rows).to_csv(OUT, index=False)
        sm = pd.DataFrame([r for r in rows if r.get("segmento") == seg_name and "dLL" in r])
        if len(sm):
            print(f"[{seg_name}] dLL medio={sm.dLL.mean():+.4f} | por fold: "
                  + " ".join(f"{x:+.4f}" for x in sm.dLL.values) + f" | w0~{sm.w0.mean():.2f}", flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
