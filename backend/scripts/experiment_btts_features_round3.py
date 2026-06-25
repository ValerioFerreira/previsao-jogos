#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rodada #1 do doc: SoS ajustado por gols (grupo S2) testado POR CIMA do modelo
de produção (base + PACE). Gate = walk-forward 9 janelas + multi-mercado."""
import sys, warnings, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
from sklearn.metrics import log_loss
from joblib import Parallel, delayed
from experiment_btts_features import build_features, base_feats, M
from experiment_btts_features_round2 import fit_dc, markets, ll

warnings.filterwarnings("ignore")


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df, groups = build_features(df)
    BASE = base_feats(df)
    new_all = [c for g in groups.values() for c in g]
    BASE = [c for c in BASE if c not in new_all]
    P = groups["P_pace"]; S2 = groups["S2_sosadj"]
    S2_adj = ["home_att_adj","away_att_adj","home_def_adj","away_def_adj"]
    S2_sched = [c for c in S2 if c not in S2_adj]
    PROD = BASE + P
    print(f"base={len(BASE)} | PROD(base+pace)={len(PROD)} | S2={len(S2)}")

    sets = {
        "PROD (base+pace)": PROD,
        "PROD+S2 (full)": PROD + S2,
        "PROD+S2_adj": PROD + S2_adj,
        "PROD+S2_sched": PROD + S2_sched,
    }

    adv = df[df["has_advanced_stats"] == 1].reset_index(drop=True)
    qs = np.linspace(0.50, 0.92, 10)
    cuts = [adv.iloc[int(len(adv) * q)]["date"] for q in qs]
    wins = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]

    def run(name, lo, hi):
        feats = sets[name]
        tr = df[df["date"] <= lo]; te = df[(df["date"] > lo) & (df["date"] <= hi) & (df["has_advanced_stats"] == 1)]
        if len(te) < 60: return None
        dc = fit_dc(tr, feats); b, r, pg = markets(dc, te, feats)
        yb = te["btts"].astype(int).values
        yg = np.clip((te["home_score"] + te["away_score"]).values, 0, M).astype(int)
        cls = ["A", "D", "H"]; yr = np.array([cls.index(v) for v in te["result"].values])
        return (name, str(lo.date()), ll(yb, b),
                float(-np.mean(np.log(pg[np.arange(len(te)), yg] + 1e-15))),
                float(log_loss(yr, r, labels=[0, 1, 2])))

    jobs = [(n, lo, hi) for n in sets for (lo, hi) in wins]
    print(f"Rodando {len(jobs)} fits...")
    res = [x for x in Parallel(n_jobs=12)(delayed(run)(n, lo, hi) for n, lo, hi in jobs) if x]
    by = {}
    for name, win, b, g, r in res:
        by.setdefault(name, {})[win] = (b, g, r)
    base = by["PROD (base+pace)"]
    print("\n" + "=" * 92)
    print(f"{'conjunto':<18} | {'BTTS dll':>9} {'wins':>6} | {'GOLS dnll':>10} {'wins':>6} | {'RESULT dll':>10} {'wins':>6}")
    print("-" * 92)
    rows = []
    for name in sets:
        if name == "PROD (base+pace)":
            print(f"{name:<18} |  (referência)")
            continue
        db = [by[name][w][0] - base[w][0] for w in base if w in by[name]]
        dg = [by[name][w][1] - base[w][1] for w in base if w in by[name]]
        dr = [by[name][w][2] - base[w][2] for w in base if w in by[name]]
        n = len(db); rb, rg, rr = sum(x < 0 for x in db), sum(x < 0 for x in dg), sum(x < 0 for x in dr)
        print(f"{name:<18} | {np.mean(db):>+9.5f} {rb:>3}/{n:<2} | {np.mean(dg):>+10.5f} {rg:>3}/{n:<2} | {np.mean(dr):>+10.5f} {rr:>3}/{n:<2}")
        rows.append({"set": name, "btts_dmean": float(np.mean(db)), "btts_wins": f"{rb}/{n}",
                     "gols_dmean": float(np.mean(dg)), "gols_wins": f"{rg}/{n}",
                     "result_dmean": float(np.mean(dr)), "result_wins": f"{rr}/{n}",
                     "btts_deltas": [round(x, 5) for x in db]})
    print("=" * 92)
    print("Gate de adoção: BTTS >=7/9 janelas E sem regressão em gols/resultado.")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/btts_features_round3_sos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
