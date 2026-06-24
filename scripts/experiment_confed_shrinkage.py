#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_confed_shrinkage.py  (#1)
============================================
Estima offsets de forca global por confederacao (gamma_C, em pontos de Elo) a partir
dos jogos inter-confederacao do TREINO, aplica como ajuste no Elo (forca efetiva =
elo + gamma_C; intra-confed nao muda), re-treina o Dixon-Coles e avalia ESTRATIFICADO:
  - inter-confed (esp. inflados CONCACAF/AFC/OFC): o residuo (real - esperado) -> ~0?
  - intra-confed: nao-regressao (log-loss/ECE inalterados)?
  - global: log-loss/ECE de resultado.

gamma_UEFA = gamma_CONMEBOL = 0 (referencias fortes). Sem leakage (gamma so do treino).
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from dixon_coles_model import DixonColesNBRegressor
warnings.filterwarnings("ignore")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

META = json.load(open(ROOT / "api/model_artifacts/meta.json", encoding="utf-8"))
BASE = META["base_feats"]
CM = {k: v for k, v in json.load(open(ROOT / "api/model_artifacts/confed_map.json", encoding="utf-8")).items() if not k.startswith("_")}
FIT_CONF = ["CONCACAF", "AFC", "CAF", "OFC"]   # UEFA, CONMEBOL = 0 (referencia)
HOME_ADV = 65.0


def mce(y, P, classes, nb=10):
    pred = np.array([classes[i] for i in P.argmax(1)]); conf = P.max(1)
    cor = (pred == np.asarray(y)).astype(float); b = np.linspace(0,1,nb+1); e=0.0; n=len(y)
    for i in range(nb):
        m=(conf>=b[i])&(conf<b[i+1])
        if m.sum()>0: e += (m.sum()/n)*abs(cor[m].mean()-conf[m].mean())
    return e


def eff_diff_from_winprob(E):
    E = np.clip(E, 1e-6, 1-1e-6)
    return -400.0 * np.log10(1.0/E - 1.0)   # diff efetivo (com mando embutido)


def estimate_gamma(tr):
    """gamma_C minimizando Brier do score esperado nos jogos inter-confed do treino."""
    g = tr[(tr.hc != tr.ac)].copy()
    d_raw = eff_diff_from_winprob(g["elo_home_winprob"].values)
    hpts = g["result"].map({"H":1.0,"D":0.5,"A":0.0}).values
    hc = g["hc"].values; ac = g["ac"].values
    def gamma_vec(params):
        gm = {"UEFA":0.0,"CONMEBOL":0.0}
        for i,c in enumerate(FIT_CONF): gm[c]=params[i]
        gh = np.array([gm.get(c,0.0) for c in hc]); ga = np.array([gm.get(c,0.0) for c in ac])
        return gh, ga
    def obj(params):
        gh, ga = gamma_vec(params)
        d_adj = d_raw + gh - ga
        E = 1.0/(1.0+10.0**(-d_adj/400.0))
        return np.mean((E - hpts)**2)
    # Powell + x0 informado pelo diagnostico (inflados ~ -80 Elo); robusto a escala
    res = minimize(obj, [-80.0, -80.0, 0.0, -120.0], method="Powell",
                   options={"xtol": 0.5, "ftol": 1e-9, "maxiter": 20000})
    return {**{"UEFA":0.0,"CONMEBOL":0.0}, **{FIT_CONF[i]:float(res.x[i]) for i in range(4)}}


def apply_gamma(df, gamma):
    df = df.copy()
    gh = df["hc"].map(lambda c: gamma.get(c,0.0)).fillna(0.0).values
    ga = df["ac"].map(lambda c: gamma.get(c,0.0)).fillna(0.0).values
    df["home_elo_pre"] = df["home_elo_pre"] + gh
    df["away_elo_pre"] = df["away_elo_pre"] + ga
    df["elo_diff"] = df["home_elo_pre"] - df["away_elo_pre"]
    adv = np.where(df["neutral"].fillna(0).astype(bool), 0.0, HOME_ADV)
    df["elo_home_winprob"] = 1.0/(1.0+10.0**(-(df["elo_diff"].values+adv)/400.0))
    return df


def fit_eval(tr, te, label):
    dc = DixonColesNBRegressor(max_goals=12)
    dc.fit(tr[BASE], tr["home_score"].values, tr["away_score"].values)
    pm = dc.predict_proba_markets(te[BASE]); classes=["A","D","H"]
    P = pm["result"]; y = te["result"].values
    e_pts = P[:,2]*1.0 + P[:,1]*0.5    # esperado de pontos do mandante
    hpts = pd.Series(y).map({"H":1.0,"D":0.5,"A":0.0}).values
    res = pd.DataFrame({"hc":te["hc"].values,"ac":te["ac"].values,"resid":hpts-e_pts})
    inter = res[res.hc!=res.ac]; intra=res[res.hc==res.ac]
    infl = inter[inter.hc.isin(["CONCACAF","AFC","OFC"]) | inter.ac.isin(["CONCACAF","AFC","OFC"])]
    out = {
        "ll": float(log_loss(y,P,labels=classes)), "ece": float(mce(y,P,classes)),
        "resid_inter": float(inter.resid.mean()), "resid_infl": float(infl.resid.mean()),
        "n_inter": len(inter),
    }
    # log-loss intra (nao-regressao)
    intra_mask = (te["hc"].values==te["ac"].values)
    out["ll_intra"] = float(log_loss(y[intra_mask], P[intra_mask], labels=classes))
    print(f"[{label}] result_ll {out['ll']:.4f} | ECE {out['ece']:.2%} | ll_intra {out['ll_intra']:.4f} | "
          f"resid_inter {out['resid_inter']:+.3f} | resid_INFLADOS {out['resid_infl']:+.3f} (n_inter {out['n_inter']})")
    return out


def main():
    df = pd.read_csv(ROOT/"international_features_enriched_apifootball.csv", parse_dates=["date"])
    df = df.dropna(subset=["home_score","away_score","elo_home_winprob"]).copy()
    df["hc"]=df["home_team"].map(CM); df["ac"]=df["away_team"].map(CM)
    df = df.sort_values("date").reset_index(drop=True)
    cut = df.iloc[int(len(df)*0.8)]["date"]
    tr, te = df[df.date<=cut].copy(), df[df.date>cut].copy()
    print(f"treino {len(tr)} | teste {len(te)} | corte {cut.date()}")

    gamma = estimate_gamma(tr)
    print("gamma_C (pontos de Elo; <0 = inflado, encolhe):",
          {k: round(v) for k,v in gamma.items()})

    base = fit_eval(tr, te, "BASE (Elo bruto)")
    tr_adj, te_adj = apply_gamma(tr, gamma), apply_gamma(te, gamma)
    adj = fit_eval(tr_adj, te_adj, "AJUSTADO (Elo+gamma)")

    print("\n=== VEREDITO (#1) ===")
    print(f"  residuo INFLADOS (CONCACAF/AFC/OFC) inter-confed: {base['resid_infl']:+.3f} -> {adj['resid_infl']:+.3f} "
          f"({'melhora p/ 0' if abs(adj['resid_infl'])<abs(base['resid_infl']) else 'NAO melhora'})")
    print(f"  log-loss intra-confed (nao-regressao): {base['ll_intra']:.4f} -> {adj['ll_intra']:.4f} "
          f"({'ok' if adj['ll_intra']<=base['ll_intra']+2e-3 else 'REGREDIU'})")
    print(f"  log-loss global: {base['ll']:.4f} -> {adj['ll']:.4f} | ECE {base['ece']:.2%} -> {adj['ece']:.2%}")
    ok = abs(adj['resid_infl'])<abs(base['resid_infl'])-0.01 and adj['ll_intra']<=base['ll_intra']+2e-3 and adj['ll']<=base['ll']+2e-3
    print("  PROMOVER?", "SIM (cauda calibra sem regredir intra)" if ok else "NAO")


if __name__ == "__main__":
    main()
