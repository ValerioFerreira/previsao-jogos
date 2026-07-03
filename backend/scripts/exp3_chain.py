#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/exp3_chain.py
=============================
EXP 3 — MODELAGEM CONJUNTA / CADEIAS DE REGRESSAO.
A producao ja encadeia finalizacoes -> escanteios (cascade). Aqui testamos se
ESTENDER a cadeia ajuda os mercados a jusante, vs modelos independentes, sob o
gate temporal de producao (GBR+NB):

  cadeia:  posse(rolling, ja em dados) -> finalizacoes -> finalizacoes a gol
                                                       -> escanteios -> cartoes
                                                       -> gols
  As predicoes a montante entram como features a jusante. Para evitar leakage as
  features a montante no TREINO sao OOF (KFold cross_val_predict); no TESTE sao
  preditas pelo modelo a montante treinado em todo o treino (igual generate_oof_shots).

Compara, por mercado a jusante: base (GBR+NB) vs base+upstream(predito), com
CV temporal expanding, log-loss da PMF marginal/total + ECE. Gate: reduzir LL sem
piorar ECE, consistente. Saida: data/reports/exp3_chain_results.csv
"""
from __future__ import annotations
import warnings
from pathlib import Path
import sys
import numpy as np, pandas as pd
from sklearn.model_selection import KFold
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reports" / "exp3_chain_results.csv"

# alvo -> (col_home, col_away, linha, grade, upstream targets que alimentam)
UP_SHOTS = [("home_cur_sb_shots", "away_cur_sb_shots")]
UP_CORN = [("home_cur_sb_corners", "away_cur_sb_corners")]
UP_SOT = [("home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target")]

MARKETS = {
    "finalizacoes_gol": ("home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 7.5, 30, UP_SHOTS),
    "escanteios": ("home_cur_sb_corners", "away_cur_sb_corners", 9.5, 25, UP_SHOTS),
    "cartoes": ("home_cur_sb_cards", "away_cur_sb_cards", 3.5, 15, UP_SHOTS + UP_CORN),
    "gols": ("home_score", "away_score", 2.5, 12, UP_SHOTS + UP_CORN + UP_SOT),
}

def oof_upstream(tr, te, feats, upstreams):
    """Gera colunas pred_* para cada alvo a montante (OOF no treino, modelo-cheio no teste)."""
    tr = tr.copy(); te = te.copy()
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    extra = []
    for (ch, ca) in upstreams:
        for side, col in [("home", ch), ("away", ca)]:
            name = f"pred_{side}_{col}"
            tr[name] = np.nan
            y = tr[col].astype(float).values
            for tri, vai in kf.split(tr):
                reg = M.make_reg("gbr").fit(tr.iloc[tri][feats], y[tri])
                tr.iloc[vai, tr.columns.get_loc(name)] = reg.predict(tr.iloc[vai][feats])
            reg_full = M.make_reg("gbr").fit(tr[feats], y)
            te[name] = reg_full.predict(te[feats])
            extra.append(name)
    return tr, te, extra

def ece_ou(y, over, line):
    yb = (y > line).astype(float); e = 0.0; edges = np.linspace(0, 1, 11)
    for b in range(10):
        mk = (over >= edges[b]) & (over < edges[b + 1])
        if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - over[mk].mean())
    return float(e)

def eval_set(sub, ch, ca, grade, line, base_feats, upstreams, use_chain):
    cuts = np.linspace(0.5, 0.85, 4)
    res = {lado: {"ll": [], "ece": []} for lado in ["mandante", "visitante", "total"]}
    for c in cuts:
        n = int(len(sub) * c); m = int(len(sub) * min(c + 0.15, 1.0))
        tr, te = sub.iloc[:n], sub.iloc[n:m]
        if len(te) < 30: continue
        feats = list(base_feats)
        if use_chain:
            tr, te, extra = oof_upstream(tr, te, base_feats, upstreams)
            feats = base_feats + extra
        for lado, ln in [("mandante", line / 2), ("visitante", line / 2), ("total", line)]:
            if lado == "total":
                Ph, _ = M.build_pmf("gbr", "nb", tr[feats], tr[ch].astype(int).values, te[feats], grade)
                Pa, _ = M.build_pmf("gbr", "nb", tr[feats], tr[ca].astype(int).values, te[feats], grade)
                P = np.zeros((len(te), 2 * grade + 1))
                for i in range(len(te)): P[i] = np.convolve(Ph[i], Pa[i])
                y = te[ch].astype(int).values + te[ca].astype(int).values
            else:
                col = ch if lado == "mandante" else ca
                y = te[col].astype(int).values
                P, _ = M.build_pmf("gbr", "nb", tr[feats], tr[col].astype(int).values, te[feats], grade)
            idx = np.clip(y, 0, P.shape[1] - 1)
            res[lado]["ll"].append(float(-np.mean(np.log(P[np.arange(len(y)), idx] + 1e-15))))
            over = P[:, int(np.floor(ln)) + 1:].sum(1)
            res[lado]["ece"].append(ece_ou(y, over, ln))
    return res

def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    rows = []
    for mkt, (ch, ca, line, grade, upstreams) in MARKETS.items():
        need = [ch, ca] + [c for pair in upstreams for c in pair]
        sub = adv.dropna(subset=need).reset_index(drop=True)
        base = eval_set(sub, ch, ca, grade, line, M.FEATS, upstreams, use_chain=False)
        chain = eval_set(sub, ch, ca, grade, line, M.FEATS, upstreams, use_chain=True)
        for lado in ["mandante", "visitante", "total"]:
            bll, bece = np.mean(base[lado]["ll"]), np.mean(base[lado]["ece"])
            cll, cece = np.mean(chain[lado]["ll"]), np.mean(chain[lado]["ece"])
            rows.append({"mercado": mkt, "lado": lado, "n": len(sub),
                         "base_ll": bll, "chain_ll": cll, "dLL": cll - bll,
                         "base_ece": bece, "chain_ece": cece, "dECE": cece - bece,
                         "upstream": "+".join(p[0].replace("home_cur_sb_", "").replace("home_", "") for p in upstreams)})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        print(f"[{mkt}] ok (N={len(sub)})", flush=True)
        for r in rows[-3:]:
            print(f"    {r['lado']:9} dLL={r['dLL']:+.4f} (base {r['base_ll']:.4f}) dECE={100*r['dECE']:+.2f}pp", flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
