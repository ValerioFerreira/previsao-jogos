#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_btts_features.py
===================================
Avenida de FEATURES NOVAS para os lambda/mu do Dixon-Coles (melhora BTTS e os
demais mercados de uma vez). Testa grupos de features point-in-time (leakage-safe,
shift(1)) que ainda NÃO estão no dataset:
  V  = forma por MANDO (home só em casa / away só fora)
  S  = força do adversário recente (SoS via Elo)
  I  = interações/estimadores explícitos (ataque×defesa, BTTS estimado)
  M  = momentum (l3 - l10)
  P  = pace / ambiente de gols
  E  = EWMA (forma com decaimento)
Gate: walk-forward (estabilidade no tempo é o critério) + bootstrap no corte único.
Métrica primária: log-loss do BTTS out-of-sample.
"""
import warnings, contextlib, io, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import nbinom
from sklearn.metrics import log_loss
from joblib import Parallel, delayed
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
RS, M = 42, 12
OUT = Path("reports"); OUT.mkdir(exist_ok=True)
LEAK = {"match_id","date","home_team","away_team","city","country","tournament","home_score",
        "away_score","goal_diff","total_goals","result","home_win","away_win","draw","btts",
        "over_2_5","has_advanced_stats","year","month","decade"}


def base_feats(df):
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


def fit_btts(tr, te, feats):
    dc=DixonColesNBRegressor(n_estimators=100,max_depth=3,learning_rate=0.05,max_goals=M,random_state=RS)
    with contextlib.redirect_stdout(io.StringIO()):
        dc.fit(tr[feats], tr["home_score"], tr["away_score"])
    lam=np.maximum(dc.model_home_.predict(te[feats]),1e-4)
    mu=np.maximum(dc.model_away_.predict(te[feats]),1e-4)
    return btts_from(lam,mu,dc.r_H_,dc.r_A_,dc.rho_)


def ll(y,p): return float(log_loss(y, np.clip(p,1e-6,1-1e-6), labels=[0,1]))


# ─── engenharia de features point-in-time ────────────────────────────────────
def build_features(df):
    df = df.copy()
    if "match_id" not in df.columns or df["match_id"].duplicated().any():
        df["match_id"] = (df["date"].astype(str)+"|"+df["home_team"].astype(str)+"|"+df["away_team"].astype(str))
    need = ["match_id","date","home_team","away_team","home_score","away_score","home_elo_pre","away_elo_pre"]
    h = df[need].rename(columns={"home_team":"team","away_team":"opp","home_score":"gf","away_score":"ga","away_elo_pre":"opp_elo"}); h["is_home"]=1
    a = df[need].rename(columns={"away_team":"team","home_team":"opp","away_score":"gf","home_score":"ga","home_elo_pre":"opp_elo"}); a["is_home"]=0
    h=h[["match_id","team","date","gf","ga","opp_elo","is_home"]]; a=a[["match_id","team","date","gf","ga","opp_elo","is_home"]]
    gl = pd.concat([h,a],ignore_index=True).sort_values(["team","date","match_id"]).reset_index(drop=True)
    gl["scored"]=(gl["gf"]>=1).astype(float); gl["cs"]=(gl["ga"]==0).astype(float)
    groups = {}

    def roll(g, col, w):
        return g.groupby("team",sort=False)[col].transform(lambda s: s.shift(1).rolling(w,min_periods=1).mean())

    # V — forma por mando
    vcols=[]
    for is_home, pre in [(1,"hv"),(0,"av")]:
        sub = gl[gl.is_home==is_home].copy()
        for col in ["gf","ga","scored","cs"]:
            for w in [5,10]:
                sub[f"{pre}_{col}_{w}"]=roll(sub,col,w)
        cols=[f"{pre}_{col}_{w}" for col in ["gf","ga","scored","cs"] for w in [5,10]]
        df = df.merge(sub[["match_id"]+cols], on="match_id", how="left"); vcols+=cols
    groups["V_mando"]=vcols

    # S — SoS via Elo do adversário recente
    for w in [5,10]: gl[f"oppelo_{w}"]=roll(gl,"opp_elo",w)
    scols=[]
    for is_home, pre in [(1,"home"),(0,"away")]:
        sub=gl[gl.is_home==is_home][["match_id","oppelo_5","oppelo_10"]].rename(
            columns={"oppelo_5":f"{pre}_oppelo_5","oppelo_10":f"{pre}_oppelo_10"})
        df=df.merge(sub,on="match_id",how="left"); scols+=[f"{pre}_oppelo_5",f"{pre}_oppelo_10"]
    groups["S_sos"]=scols

    # E — EWMA (span 5)
    gl["ewg"]=gl.groupby("team",sort=False)["gf"].transform(lambda s: s.shift(1).ewm(span=5,min_periods=1).mean())
    gl["ewa"]=gl.groupby("team",sort=False)["ga"].transform(lambda s: s.shift(1).ewm(span=5,min_periods=1).mean())
    ecols=[]
    for is_home, pre in [(1,"home"),(0,"away")]:
        sub=gl[gl.is_home==is_home][["match_id","ewg","ewa"]].rename(columns={"ewg":f"{pre}_ewg",f"ewa":f"{pre}_ewa"})
        df=df.merge(sub,on="match_id",how="left"); ecols+=[f"{pre}_ewg",f"{pre}_ewa"]
    groups["E_ewma"]=ecols

    # M — momentum (derivado das colunas existentes l3-l10)
    mcols=[]
    for side in ["home","away"]:
        for m in ["gf","ga","ppg","bttsrate","csrate","ftsrate"]:
            a3,a10=f"{side}_{m}_l3",f"{side}_{m}_l10"
            if a3 in df and a10 in df:
                df[f"{side}_{m}_mom"]=df[a3]-df[a10]; mcols.append(f"{side}_{m}_mom")
    groups["M_momentum"]=mcols

    # I — interações/estimadores explícitos (das colunas existentes)
    def g(c): return df[c] if c in df else np.nan
    df["est_home_sc"]=0.5*(1-g("home_ftsrate_l10"))+0.5*(1-g("away_csrate_l10"))
    df["est_away_sc"]=0.5*(1-g("away_ftsrate_l10"))+0.5*(1-g("home_csrate_l10"))
    df["est_btts"]=df["est_home_sc"]*df["est_away_sc"]
    df["xprod_home"]=g("home_gf_l10")*g("away_ga_l10")
    df["xprod_away"]=g("away_gf_l10")*g("home_ga_l10")
    df["btts_rate_prod"]=g("home_bttsrate_l10")*g("away_bttsrate_l10")
    groups["I_interacoes"]=["est_home_sc","est_away_sc","est_btts","xprod_home","xprod_away","btts_rate_prod"]

    # P — pace / ambiente
    df["pace_gf"]=g("home_gf_l10")+g("away_gf_l10")
    df["pace_ga"]=g("home_ga_l10")+g("away_ga_l10")
    df["pace_total"]=df["pace_gf"]+df["pace_ga"]
    df["btts_sum"]=g("home_bttsrate_l10")+g("away_bttsrate_l10")
    groups["P_pace"]=["pace_gf","pace_ga","pace_total","btts_sum"]

    return df, groups


def time_cuts(df):
    adv=df[df["has_advanced_stats"]==1].reset_index(drop=True)
    qs=np.linspace(0.55,0.95,7)
    return [adv.iloc[int(len(adv)*q)]["date"] for q in qs]


def main():
    df=pd.read_csv("international_features_enriched_apifootball.csv",parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df, groups = build_features(df)
    BASE = base_feats(df)
    # remove colunas de grupos do BASE caso colidam (não devem)
    new_all=[c for g in groups.values() for c in g]
    BASE=[c for c in BASE if c not in new_all]
    print(f"base feats={len(BASE)} | grupos: " + ", ".join(f"{k}({len(v)})" for k,v in groups.items()))

    # conjuntos a testar
    sets = {"BASE": BASE}
    for k,v in groups.items(): sets[f"+{k}"]=BASE+v
    sets["+ALL"]=BASE+new_all

    # corte único (mesmo do projeto)
    cut=time_cuts(df)[ int(len(time_cuts(df))*0)+ 0 ]  # placeholder
    adv=df[df["has_advanced_stats"]==1]; cut=adv.iloc[int(len(adv)*0.8)]["date"]
    tr=df[df["date"]<=cut].reset_index(drop=True); te=df[(df["date"]>cut)&(df["has_advanced_stats"]==1)].reset_index(drop=True)
    yte=te["btts"].astype(int).values

    # walk-forward windows
    cuts=time_cuts(df); wins=[(cuts[i],cuts[i+1]) for i in range(len(cuts)-1)]

    # roda tudo em paralelo: (set, 'single'|window) -> log-loss
    jobs=[]
    for name,feats in sets.items():
        jobs.append((name,"single",None))
        for i,(lo,hi) in enumerate(wins): jobs.append((name,f"wf{i}",(lo,hi)))

    def run(name, tag, win):
        feats=sets[name]
        if tag=="single":
            p=fit_btts(tr,te,feats); return (name,tag,ll(yte,p),len(te),None if name!="BASE" else p.tolist() if False else None, p.tolist())
        lo,hi=win
        tr2=df[df["date"]<=lo]; te2=df[(df["date"]>lo)&(df["date"]<=hi)&(df["has_advanced_stats"]==1)]
        if len(te2)<60: return (name,tag,None,0,None,None)
        p=fit_btts(tr2,te2,feats); return (name,tag,ll(te2["btts"].astype(int).values,p),int(len(te2)),None,None)

    print(f"Rodando {len(jobs)} fits de DC em paralelo...")
    res=Parallel(n_jobs=10)(delayed(run)(n,t,w) for n,t,w in jobs)

    # organiza
    single={}; single_p={}; wf={}
    for name,tag,val,n,_,p in res:
        if tag=="single": single[name]=val; single_p[name]=np.array(p) if p is not None else None
        else: wf.setdefault(name,[]).append((tag,val,n))

    base_single=single["BASE"]; base_p=single_p["BASE"]; yb=yte
    rng=np.random.default_rng(RS)
    def boot_win(pc):
        if pc is None: return None
        lb=-(yb*np.log(np.clip(base_p,1e-6,1-1e-6))+(1-yb)*np.log(1-np.clip(base_p,1e-6,1-1e-6)))
        lc=-(yb*np.log(np.clip(pc,1e-6,1-1e-6))+(1-yb)*np.log(1-np.clip(pc,1e-6,1-1e-6)))
        N=len(yb); w=0
        for _ in range(2000):
            idx=rng.integers(0,N,N); w+=(lc[idx].mean()<lb[idx].mean())
        return w/2000

    # baseline walk-forward por janela
    base_wf={tag:val for tag,val,n in wf["BASE"]}
    rows=[]
    for name in sets:
        ds=single[name]-base_single
        bw=boot_win(single_p[name]) if name!="BASE" else 0.5
        # walk-forward deltas vs baseline na mesma janela
        deltas=[]; nwin=0
        for tag,val,n in wf.get(name,[]):
            if val is not None and base_wf.get(tag) is not None:
                deltas.append(val-base_wf[tag]); nwin+=1
        wins_won=sum(d<0 for d in deltas); dmean=float(np.mean(deltas)) if deltas else 0.0
        rows.append({"set":name,"single_ll":single[name],"single_d":ds,"boot_win":bw,
                     "wf_dmean":dmean,"wf_wins":f"{wins_won}/{nwin}","wf_deltas":[round(d,5) for d in deltas]})

    rows.sort(key=lambda r:(r["wf_dmean"]))
    (OUT/"btts_features.json").write_text(json.dumps({"base_single":base_single,"rows":rows},ensure_ascii=False,indent=2),encoding="utf-8")

    print("\n"+"="*100)
    print(f"{'conjunto':<14} {'single_ll':>9} {'single_d':>9} {'boot%':>6} | {'wf_dmean':>9} {'wf_wins':>8}  deltas_por_janela")
    print("-"*100)
    for r in rows:
        stable = r["wf_dmean"]<0 and r["wf_wins"].split("/")[0]==r["wf_wins"].split("/")[1] and r["single_d"]<0
        good = r["wf_dmean"]<0 and int(r["wf_wins"].split("/")[0])>=5
        flag=" **" if stable else (" *" if good else "")
        bw = f"{r['boot_win']*100:>5.0f}%" if r["set"]!="BASE" else "   - "
        print(f"{r['set']:<14} {r['single_ll']:>9.5f} {r['single_d']:>+9.5f} {bw} | {r['wf_dmean']:>+9.5f} {r['wf_wins']:>8}  {r['wf_deltas']}")
    print("="*100)
    print(f"BASE single log-loss={base_single:.5f} | '**'=melhora em TODAS as janelas+corte | '*'=>=5/6 janelas")
    print(f"JSON: {OUT/'btts_features.json'}")


if __name__=="__main__":
    main()
