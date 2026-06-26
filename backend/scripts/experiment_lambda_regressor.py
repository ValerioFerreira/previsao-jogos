#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimento EXAUSTIVO: classe do regressor de lambda/mu do Dixon-Coles.
Hoje o DC estima os gols esperados (lambda_home, mu_away) com sklearn
GradientBoostingRegressor. Testa trocar por HistGBM / XGBoost / LightGBM em várias
configurações, avaliando no walk-forward em 4 mercados:
  BTTS (log-loss), Gols totais (NLL), Resultado 1X2 (log-loss), Placar exato (NLL).
Feature set = produção (base + pace, 158). Gate = estabilidade no tempo.
"""
import sys, warnings, contextlib, io, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.metrics import log_loss
from joblib import Parallel, delayed
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
RS, M = 42, 12
LEAK = {"match_id","date","home_team","away_team","city","country","tournament","home_score",
        "away_score","goal_diff","total_goals","result","home_win","away_win","draw","btts",
        "over_2_5","has_advanced_stats","year","month","decade"}


def base_feats(df):
    return [c for c in df.columns if c not in LEAK and not c.startswith(("home_cur_","away_cur_"))
            and "sb_" not in c and pd.api.types.is_numeric_dtype(df[c])]


def make_reg(spec):
    t, p = spec["type"], spec.get("params", {})
    imp = SimpleImputer(strategy="median")
    if t == "gbm":
        reg = GradientBoostingRegressor(random_state=RS, **p)
    elif t == "hist":
        reg = HistGradientBoostingRegressor(random_state=RS, **p)
    elif t == "xgb":
        from xgboost import XGBRegressor; reg = XGBRegressor(random_state=RS, n_jobs=2, **p)
    elif t == "lgbm":
        from lightgbm import LGBMRegressor; reg = LGBMRegressor(random_state=RS, n_jobs=2, verbose=-1, **p)
    return Pipeline([("imp", imp), ("reg", reg)])


class DCReg(DixonColesNBRegressor):
    def with_spec(self, spec): self._spec = spec; return self
    def _create_base_regressor(self): return make_reg(self._spec)


CONFIGS = {
    "GBM (produção)":      {"type": "gbm",  "params": {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.05}},
    "GBM n300":            {"type": "gbm",  "params": {"n_estimators": 300, "max_depth": 3, "learning_rate": 0.05}},
    "HistGBM":             {"type": "hist", "params": {"max_depth": 3, "learning_rate": 0.05, "max_iter": 400, "l2_regularization": 1.0}},
    "XGB d3 n300":         {"type": "xgb",  "params": {"max_depth": 3, "n_estimators": 300, "learning_rate": 0.05, "subsample": 0.9, "colsample_bytree": 0.8, "reg_lambda": 1.0}},
    "XGB d4 n500 lr.03":   {"type": "xgb",  "params": {"max_depth": 4, "n_estimators": 500, "learning_rate": 0.03, "subsample": 0.9, "colsample_bytree": 0.8, "reg_lambda": 1.5}},
    "XGB d6 n300":         {"type": "xgb",  "params": {"max_depth": 6, "n_estimators": 300, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.7, "reg_lambda": 2.0, "min_child_weight": 5}},
    "LGBM l31 n300":       {"type": "lgbm", "params": {"num_leaves": 31, "n_estimators": 300, "learning_rate": 0.05, "subsample": 0.9, "colsample_bytree": 0.8, "reg_lambda": 1.0}},
    "LGBM l15 n500 lr.03": {"type": "lgbm", "params": {"num_leaves": 15, "n_estimators": 500, "learning_rate": 0.03, "subsample": 0.9, "colsample_bytree": 0.8, "reg_lambda": 1.0, "min_child_samples": 40}},
    "LGBM l63 n400":       {"type": "lgbm", "params": {"num_leaves": 63, "n_estimators": 400, "learning_rate": 0.04, "subsample": 0.8, "colsample_bytree": 0.7, "reg_lambda": 2.0, "min_child_samples": 50}},
}


def evaluate(dc, te, feats):
    pr = dc.predict_proba_markets(te[feats])
    btts, res, J = pr["btts"], pr["result"], pr["joint"]
    N = len(te)
    pg = np.zeros((N, M + 1))
    for x in range(M + 1):
        for y in range(M + 1):
            if x + y <= M:
                pg[:, x + y] += J[:, x, y]
    pg /= pg.sum(axis=1, keepdims=True)
    yb = te["btts"].astype(int).values
    yg = np.clip((te["home_score"] + te["away_score"]).values, 0, M).astype(int)
    cls = ["A", "D", "H"]; yr = np.array([cls.index(v) for v in te["result"].values])
    yh = np.clip(te["home_score"].values, 0, M).astype(int)
    ya = np.clip(te["away_score"].values, 0, M).astype(int)
    return {
        "btts": float(log_loss(yb, np.clip(btts, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "gols": float(-np.mean(np.log(pg[np.arange(N), yg] + 1e-15))),
        "result": float(log_loss(yr, res, labels=[0, 1, 2])),
        "exact": float(-np.mean(np.log(J[np.arange(N), yh, ya] + 1e-15))),
    }


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    feats = base_feats(df)
    print(f"features (produção, base+pace): {len(feats)} | configs: {len(CONFIGS)}")
    adv = df[df["has_advanced_stats"] == 1].reset_index(drop=True)
    qs = np.linspace(0.50, 0.92, 9)
    cuts = [adv.iloc[int(len(adv) * q)]["date"] for q in qs]
    wins = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]

    def run(name, lo, hi):
        tr = df[df["date"] <= lo]; te = df[(df["date"] > lo) & (df["date"] <= hi) & (df["has_advanced_stats"] == 1)]
        if len(te) < 60:
            return None
        dc = DCReg(max_goals=M, random_state=RS).with_spec(CONFIGS[name])
        with contextlib.redirect_stdout(io.StringIO()):
            dc.fit(tr[feats], tr["home_score"], tr["away_score"])
        return (name, str(lo.date()), evaluate(dc, te, feats))

    jobs = [(n, lo, hi) for n in CONFIGS for (lo, hi) in wins]
    print(f"Rodando {len(jobs)} fits de DC (paralelo)...")
    res = [x for x in Parallel(n_jobs=10)(delayed(run)(n, lo, hi) for n, lo, hi in jobs) if x]

    by = {}
    for name, win, m in res:
        by.setdefault(name, {})[win] = m
    base = by["GBM (produção)"]
    mkts = [("btts", "BTTS"), ("gols", "GOLS"), ("result", "RESULT"), ("exact", "PLACAR")]
    rows = []
    print("\n" + "=" * 104)
    print(f"{'config':<22}" + "".join(f"| {lbl:>7} dmean wins " for _, lbl in mkts))
    print("-" * 104)
    for name in CONFIGS:
        line = f"{name:<22}"
        rec = {"config": name}
        for key, _ in mkts:
            d = [by[name][w][key] - base[w][key] for w in base if w in by[name]]
            n = len(d); w_ = sum(x < 0 for x in d); dm = float(np.mean(d)) if d else 0.0
            line += f"| {dm:>+9.5f} {w_}/{n} "
            rec[key] = {"dmean": dm, "wins": f"{w_}/{n}"}
        print(line)
        rows.append(rec)
    print("=" * 104)
    print("dmean<0 = melhora vs GBM produção; wins = janelas em que melhora.")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/lambda_regressor.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
