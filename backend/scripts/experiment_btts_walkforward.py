#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Confirmação walk-forward do vencedor do estudo de BTTS: blend fixo
DC×0.75 + HistGBM×0.25 vs DC puro (produção), em várias janelas temporais
expansivas. Testa se o ganho do corte único se sustenta."""
import warnings, contextlib, io
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import nbinom
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from joblib import Parallel, delayed
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
RS, M = 42, 12
LEAK = {"match_id","date","home_team","away_team","city","country","tournament","home_score",
        "away_score","goal_diff","total_goals","result","home_win","away_win","draw","btts",
        "over_2_5","has_advanced_stats","year","month","decade"}
W = 0.75  # peso do DC no blend (escolhido por OOF no estudo principal)


def feats(df):
    return [c for c in df.columns if c not in LEAK and not c.startswith(("home_cur_","away_cur_"))
            and "sb_" not in c and pd.api.types.is_numeric_dtype(df[c])]


def btts_from(lam, mu, rH, rA, rho):
    lam=np.maximum(lam,1e-4); mu=np.maximum(mu,1e-4); k=np.arange(M+1)
    pH=rH/(rH+lam); pA=rA/(rA+mu)
    probH=nbinom.pmf(k[None,:],n=rH,p=pH[:,None]); probA=nbinom.pmf(k[None,:],n=rA,p=pA[:,None])
    Pj=probH[:,:,None]*probA[:,None,:]; N=len(lam)
    tau=np.ones((N,M+1,M+1)); tau[:,0,0]=1-lam*mu*rho; tau[:,0,1]=1+lam*rho; tau[:,1,0]=1+mu*rho; tau[:,1,1]=1-rho
    Pc=np.maximum(Pj*tau,0); s=Pc.sum(axis=(1,2),keepdims=True); s[s==0]=1e-15
    return (Pc/s)[:,1:,1:].sum(axis=(1,2))


def hgbm():
    return Pipeline([("imp",SimpleImputer(strategy="median")),
                     ("clf",HistGradientBoostingClassifier(max_depth=3,learning_rate=0.05,max_iter=400,
                                                           l2_regularization=1.0,random_state=RS))])


def one_window(df, fcols, c_lo, c_hi):
    tr=df[df["date"]<=c_lo]; te=df[(df["date"]>c_lo)&(df["date"]<=c_hi)&(df["has_advanced_stats"]==1)]
    if len(te)<60: return None
    dc=DixonColesNBRegressor(n_estimators=100,max_depth=3,learning_rate=0.05,max_goals=M,random_state=RS)
    with contextlib.redirect_stdout(io.StringIO()):
        dc.fit(tr[fcols],tr["home_score"],tr["away_score"])
    lam=np.maximum(dc.model_home_.predict(te[fcols]),1e-4); mu=np.maximum(dc.model_away_.predict(te[fcols]),1e-4)
    p_dc=btts_from(lam,mu,dc.r_H_,dc.r_A_,dc.rho_)
    clf=hgbm(); clf.fit(tr[fcols],tr["btts"].astype(int)); p_clf=clf.predict_proba(te[fcols])[:,1]
    p_blend=np.clip(W*p_dc+(1-W)*p_clf,1e-6,1-1e-6)
    y=te["btts"].astype(int).values
    return {"ini":str(c_lo.date()),"fim":str(c_hi.date()),"n":int(len(te)),
            "ll_dc":float(log_loss(y,np.clip(p_dc,1e-6,1-1e-6),labels=[0,1])),
            "ll_blend":float(log_loss(y,p_blend,labels=[0,1]))}


def main():
    df=pd.read_csv("international_features_enriched_apifootball.csv",parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    fcols=feats(df)
    adv=df[df["has_advanced_stats"]==1].reset_index(drop=True)
    # 6 cortes expansivos sobre a linha do tempo de jogos com stats avançadas
    qs=np.linspace(0.55,0.95,7)
    cuts=[adv.iloc[int(len(adv)*q)]["date"] for q in qs]
    jobs=[(cuts[i],cuts[i+1]) for i in range(len(cuts)-1)]
    res=Parallel(n_jobs=6)(delayed(one_window)(df,fcols,lo,hi) for lo,hi in jobs)
    res=[r for r in res if r]
    print(f"{'janela':<25} {'n':>5} {'ll_DC':>9} {'ll_blend':>9} {'delta':>9}")
    wins=0; tot_d=0
    for r in res:
        d=r["ll_blend"]-r["ll_dc"]; tot_d+=d; wins+= (d<0)
        print(f"{r['ini']}..{r['fim']:<13} {r['n']:>5} {r['ll_dc']:>9.5f} {r['ll_blend']:>9.5f} {d:>+9.5f}")
    print("-"*62)
    print(f"janelas com melhora do blend: {wins}/{len(res)} | delta medio: {tot_d/len(res):+.5f}")


if __name__=="__main__":
    main()
