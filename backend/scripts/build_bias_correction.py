#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_bias_correction.py
===================================
PLANO 4 / Fase B — aprende a CORRECAO DE VIES por mercado (odd justa do modelo
-> odd justa REAL do mercado) para os 3 mercados com odds reais: 1x2, O/U 2,5 e
handicap asiatico. Salva `model_artifacts_clubes/bias_correction.joblib`.

Metodo: calibracao logit-linear (Platt) por mercado, ajustada sobre TODAS as
saidas (nao so o lado recomendado) — `logit(p_mercado) ~ a*logit(p_model)+b`.
p_corr = sigmoid(a*logit(p_model)+b). Mercado sem entrada => identidade (a=1,b=0)
no predictor. Verdade = odd de-vigada real do mercado (o mesmo alvo do
adhoc_metrics_fair_odds). Viés é pequeno (modelo ja bem calibrado), então a
correção é suave — recalibra os números exibidos sem inventar edge.

Uso: python scripts/build_bias_correction.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "data" / "built"
ART = ROOT / "model_artifacts_clubes"

EPS = 1e-6


def _logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _fit_platt(p_model: np.ndarray, p_market: np.ndarray) -> dict:
    """Ajusta logit(p_market) = a*logit(p_model)+b por minimos quadrados."""
    x = _logit(p_model)
    y = _logit(p_market)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    A = np.vstack([x, np.ones_like(x)]).T
    (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
    # Guarda contra fit degenerado: se o slope sair de [0.5,1.5] (ex.: dados
    # aglomerados perto de 0.5, como handicap .5 -> logit quase constante ->
    # slope colapsa), cai pra IDENTIDADE (a=1,b=0). O modelo ja e bem calibrado;
    # correcao degenerada colapsaria tudo pra 0.5 e seria pior que nao corrigir.
    degenerate = not (0.5 <= a <= 1.5) or float(np.std(x)) < 0.3
    if degenerate:
        a, b = 1.0, 0.0
    p_corr = 1 / (1 + np.exp(-(a * x + b)))
    mae_before = float(np.abs(p_model[m] - p_market[m]).mean())
    mae_after = float(np.abs(p_corr - p_market[m]).mean())
    return {"a": float(a), "b": float(b), "n": int(m.sum()),
            "identidade": bool(degenerate),
            "mae_before_pp": round(mae_before * 100, 3),
            "mae_after_pp": round(mae_after * 100, 3)}


def _pairs_1x2(v):
    p_model = np.concatenate([v["p_model_H"], v["p_model_D"], v["p_model_A"]])
    p_mkt = np.concatenate([v["p_fair_close_H"], v["p_fair_close_D"], v["p_fair_close_A"]])
    return p_model.astype(float), p_mkt.astype(float)


def _pairs_ou(v):
    p_model = np.concatenate([v["p_model_over"], v["p_model_under"]])
    p_mkt = np.concatenate([v["p_fair_close_over"], v["p_fair_close_under"]])
    return p_model.astype(float), p_mkt.astype(float)


def _pairs_handicap():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fo", ROOT / "scripts" / "adhoc_metrics_fair_odds.py")
    fo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fo)
    hj = fo._handicap_frame()
    # todas as saidas: home e away
    p_model = np.concatenate([hj["p_model_home"].values, (1 - hj["p_model_home"].values)])
    p_mkt = np.concatenate([hj["p_fair_home"].values, (1 - hj["p_fair_home"].values)])
    return p_model.astype(float), p_mkt.astype(float)


def main() -> None:
    v = pd.read_parquet(BUILT / "backtest_valuebet_dataset.parquet")
    corr = {}
    pm, pk = _pairs_1x2(v); corr["1x2"] = _fit_platt(pm, pk)
    m = v[["p_model_over", "p_model_under", "p_fair_close_over", "p_fair_close_under"]].notna().all(axis=1)
    pm, pk = _pairs_ou(v[m]); corr["ou25"] = _fit_platt(pm, pk)
    pm, pk = _pairs_handicap(); corr["handicap"] = _fit_platt(pm, pk)

    corr["_meta"] = {
        "metodo": "Platt logit-linear p_corr=sigmoid(a*logit(p)+b) por mercado, ajustado vs odd "
        "de-vigada real (backtest 2025). Mercado ausente => identidade. Vies pequeno; recalibra "
        "a odd justa exibida sem inventar edge.",
        "faixa_pct": 0.05,  # banda +/-5% exibida ao redor da odd justa corrigida
        "escopo": "clube (odds reais de clube 2025); selecao usa identidade (sem odds de teste).",
    }

    ART.mkdir(parents=True, exist_ok=True)
    out = ART / "bias_correction.joblib"
    joblib.dump(corr, out)
    print(f"Salvo: {out}\n")
    print(json.dumps(corr, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
