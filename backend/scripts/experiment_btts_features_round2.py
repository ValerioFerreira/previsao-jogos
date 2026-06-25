#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 2: refina as features promissoras (P=pace, E=ewma, M=momentum) com mais
janelas de walk-forward e verifica multi-mercado (BTTS + gols totais + resultado)
para garantir que o vencedor não regride os outros mercados."""
import sys, warnings, contextlib, io, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
from sklearn.metrics import log_loss
from joblib import Parallel, delayed
from dixon_coles_model import DixonColesNBRegressor
from experiment_btts_features import build_features, base_feats, M

warnings.filterwarnings("ignore")
RS = 42


def fit_dc(tr, feats):
    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=M, random_state=RS)
    with contextlib.redirect_stdout(io.StringIO()):
        dc.fit(tr[feats], tr["home_score"], tr["away_score"])
    return dc


def markets(dc, te, feats):
    pr = dc.predict_proba_markets(te[feats])
    btts = pr["btts"]
    P = pr["joint"]; N = len(te)
    pg = np.zeros((N, M + 1))
    for x in range(M + 1):
        for y in range(M + 1):
            if x + y <= M:
                pg[:, x + y] += P[:, x, y]
    pg /= pg.sum(axis=1, keepdims=True)
    return btts, pr["result"], pg


def ll(y, p): return float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]))


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df, groups = build_features(df)
    BASE = base_feats(df)
    new_all = [c for g in groups.values() for c in g]
    BASE = [c for c in BASE if c not in new_all]
    P, E, Mg = groups["P_pace"], groups["E_ewma"], groups["M_momentum"]

    sets = {
        "BASE": BASE,
        "+P": BASE + P,
        "+E": BASE + E,
        "+P+E": BASE + P + E,
        "+P+M": BASE + P + Mg,
        "+P+E+M": BASE + P + E + Mg,
    }

    # walk-forward com 9 janelas (mais fino)
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
        return (name, str(lo.date()),
                ll(yb, b),
                float(-np.mean(np.log(pg[np.arange(len(te)), yg] + 1e-15))),
                float(log_loss(yr, r, labels=[0, 1, 2])), int(len(te)))

    jobs = [(n, lo, hi) for n in sets for (lo, hi) in wins]
    print(f"Round2: {len(jobs)} fits (walk-forward {len(wins)} janelas x {len(sets)} conjuntos)...")
    res = [x for x in Parallel(n_jobs=12)(delayed(run)(n, lo, hi) for n, lo, hi in jobs) if x]

    # agrega por conjunto vs BASE na mesma janela
    by = {}
    for name, win, b, g, r, n in res:
        by.setdefault(name, {})[win] = (b, g, r)
    base = by["BASE"]
    print("\n" + "=" * 92)
    print(f"{'conjunto':<10} | {'BTTS dll':>9} {'wins':>6} | {'GOLS dnll':>10} {'wins':>6} | {'RESULT dll':>10} {'wins':>6}")
    print("-" * 92)
    rows = []
    for name in sets:
        if name == "BASE":
            print(f"{name:<10} |  (referência: BTTS / GOLS / RESULT por janela)")
            continue
        db = [by[name][w][0] - base[w][0] for w in base if w in by[name]]
        dg = [by[name][w][1] - base[w][1] for w in base if w in by[name]]
        dr = [by[name][w][2] - base[w][2] for w in base if w in by[name]]
        rb, rg, rr = sum(x < 0 for x in db), sum(x < 0 for x in dg), sum(x < 0 for x in dr)
        n = len(db)
        print(f"{name:<10} | {np.mean(db):>+9.5f} {rb:>3}/{n:<2} | {np.mean(dg):>+10.5f} {rg:>3}/{n:<2} | {np.mean(dr):>+10.5f} {rr:>3}/{n:<2}")
        rows.append({"set": name, "btts_dmean": float(np.mean(db)), "btts_wins": f"{rb}/{n}",
                     "gols_dmean": float(np.mean(dg)), "gols_wins": f"{rg}/{n}",
                     "result_dmean": float(np.mean(dr)), "result_wins": f"{rr}/{n}",
                     "btts_deltas": [round(x, 5) for x in db]})
    print("=" * 92)
    print("dll/dnll negativos = melhora vs BASE. 'wins' = janelas em que melhora (de N).")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/btts_features_round2.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
