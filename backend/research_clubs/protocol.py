#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/protocol.py
==========================
Protocolo ÚNICO de avaliação da pesquisa de clubes (Linhas A e B) — ver
docs/PESQUISA_CLUBES.md §3. Reproduz o gate §6 do doc-central e adiciona RPS
(métrica-padrão dos Soccer Prediction Challenges).

Tudo aqui é agnóstico de modelo: os candidatos entregam probabilidades ou PMFs
e o protocolo mede. Splits SEMPRE temporais (expanding), seed 42.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SEED = 42
CUTS = [0.50, 0.60, 0.70, 0.80, 0.85]  # mesma malha do gate §6


# ─── Splits temporais ────────────────────────────────────────────────────────
def temporal_folds(df: pd.DataFrame, cuts=None, date_col="date"):
    """Gera (nome, idx_train, idx_test) com treino estritamente anterior ao teste.
    Teste = bloco entre cortes consecutivos (último bloco vai até o fim)."""
    cuts = cuts or CUTS
    df = df.sort_values(date_col)
    idx = df.index.to_numpy()
    n = len(idx)
    bounds = [int(c * n) for c in cuts] + [n]
    for i, b in enumerate(bounds[:-1]):
        tr = idx[:b]
        te = idx[b:bounds[i + 1]]
        if len(te) == 0:
            continue
        yield f"fold_{cuts[i]:.2f}", tr, te


# ─── Métricas: resultado (H/D/A) ─────────────────────────────────────────────
def multiclass_logloss(y_true_idx: np.ndarray, probs: np.ndarray, eps=1e-12) -> float:
    p = np.clip(probs[np.arange(len(y_true_idx)), y_true_idx], eps, 1.0)
    return float(-np.mean(np.log(p)))


def rps_hda(y_true_idx: np.ndarray, probs: np.ndarray) -> float:
    """Ranked Probability Score para resultado ordenado [H, D, A].
    probs colunas na ordem H, D, A; y_true_idx 0=H,1=D,2=A."""
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true_idx)), y_true_idx] = 1.0
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.cumsum(onehot, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1) / (probs.shape[1] - 1)))


def brier_multiclass(y_true_idx: np.ndarray, probs: np.ndarray) -> float:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_true_idx)), y_true_idx] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def ece_binary(y_true: np.ndarray, p: np.ndarray, n_bins=10) -> float:
    """ECE de um binário (média ponderada de |freq - conf| por bin)."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    ece, n = 0.0, len(p)
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        ece += (m.sum() / n) * abs(y_true[m].mean() - p[m].mean())
    return float(ece)


def ece_multiclass(y_true_idx: np.ndarray, probs: np.ndarray, n_bins=10) -> float:
    """ECE médio das classes (um-contra-todos)."""
    vals = []
    for k in range(probs.shape[1]):
        vals.append(ece_binary((y_true_idx == k).astype(float), probs[:, k], n_bins))
    return float(np.mean(vals))


def accuracy(y_true_idx: np.ndarray, probs: np.ndarray) -> float:
    return float((probs.argmax(axis=1) == y_true_idx).mean())


# ─── Métricas: contagem (PMF) ────────────────────────────────────────────────
def pmf_logloss(y_true: np.ndarray, pmfs: np.ndarray, eps=1e-12) -> float:
    """pmfs: matriz (n, K) com P(X=k); y_true inteiro (clipado em K-1)."""
    k = np.clip(y_true.astype(int), 0, pmfs.shape[1] - 1)
    p = np.clip(pmfs[np.arange(len(k)), k], eps, 1.0)
    return float(-np.mean(np.log(p)))


def pmf_mae(y_true: np.ndarray, pmfs: np.ndarray) -> float:
    ks = np.arange(pmfs.shape[1])
    mean = (pmfs * ks).sum(axis=1)
    return float(np.abs(mean - y_true).mean())


def coverage80(y_true: np.ndarray, pmfs: np.ndarray) -> float:
    """Fração dos reais dentro do intervalo central de 80% da PMF."""
    cdf = np.cumsum(pmfs, axis=1)
    lo = (cdf < 0.10).sum(axis=1)          # primeiro k com cdf >= .10
    hi = (cdf <= 0.90).sum(axis=1)          # último k com cdf <= .90
    return float(((y_true >= lo) & (y_true <= hi)).mean())


def ou_probs_from_pmf(pmfs: np.ndarray, line: float) -> np.ndarray:
    """P(total > line) a partir da PMF (linha .5)."""
    k_over = int(np.floor(line)) + 1
    return pmfs[:, k_over:].sum(axis=1)


def tail_ece(y_true: np.ndarray, pmfs: np.ndarray, lines: list[float], n_bins=10) -> dict:
    """ECE das linhas O/U extremas (valida a cauda — o que reprovou o DynamicCornersNB)."""
    out = {}
    for line in lines:
        p_over = ou_probs_from_pmf(pmfs, line)
        y_over = (y_true > line).astype(float)
        out[f"over_{line}"] = ece_binary(y_over, p_over, n_bins)
    return out


# ─── Runner: avaliação de um candidato de RESULTADO ──────────────────────────
RESULT_ORDER = ["H", "D", "A"]


@dataclass
class FoldResult:
    fold: str
    n_test: int
    metrics: dict
    segments: dict = field(default_factory=dict)


def _result_metrics(y_idx, probs):
    return {
        "logloss": multiclass_logloss(y_idx, probs),
        "rps": rps_hda(y_idx, probs),
        "brier": brier_multiclass(y_idx, probs),
        "ece": ece_multiclass(y_idx, probs),
        "accuracy": accuracy(y_idx, probs),
    }


def evaluate_result_model(df: pd.DataFrame, fit_predict, cuts=None,
                          segment_cols=("tournament", "is_continental"),
                          elo_bands=(80, 150)) -> list[FoldResult]:
    """
    Avalia um candidato de resultado sob o protocolo.
    `fit_predict(train_df, test_df) -> probs (n_test, 3)` na ordem H/D/A.
    Segmenta por competição, continental e equilíbrio de Elo.
    """
    df = df.sort_values("date").reset_index(drop=True)
    y_map = {c: i for i, c in enumerate(RESULT_ORDER)}
    results = []
    for fold, tr_idx, te_idx in temporal_folds(df, cuts):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        probs = np.asarray(fit_predict(tr, te))
        y_idx = te["result"].map(y_map).to_numpy()
        fr = FoldResult(fold=fold, n_test=len(te), metrics=_result_metrics(y_idx, probs))
        # segmentos
        segs = {}
        if "elo_diff" in te.columns:
            a = te["elo_diff"].abs().to_numpy()
            for name, m in [("equil", a <= elo_bands[0]),
                            (f"medio", (a > elo_bands[0]) & (a <= elo_bands[1])),
                            ("desequil", a > elo_bands[1])]:
                if m.sum() >= 50:
                    segs[f"elo_{name}"] = _result_metrics(y_idx[m], probs[m])
        for col in segment_cols:
            if col not in te.columns:
                continue
            for val, grp_idx in te.groupby(col).groups.items():
                m = te.index.isin(grp_idx)
                if m.sum() >= 100:
                    segs[f"{col}={val}"] = _result_metrics(y_idx[m], probs[m])
        fr.segments = segs
        results.append(fr)
    return results


def summarize(results: list[FoldResult], label="") -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({"modelo": label, "fold": r.fold, "n": r.n_test, **r.metrics})
    df = pd.DataFrame(rows)
    mean = df.drop(columns=["fold"]).groupby("modelo").mean(numeric_only=True)
    mean["fold"] = "MEDIA"
    return pd.concat([df, mean.reset_index()], ignore_index=True)


def compare(base: list[FoldResult], cand: list[FoldResult],
            metric="logloss") -> pd.DataFrame:
    """Comparação fold-a-fold candidato vs baseline (gate: consistência)."""
    rows = []
    for b, c in zip(base, cand):
        assert b.fold == c.fold
        rows.append({"fold": b.fold, "n": b.n_test,
                     "baseline": b.metrics[metric], "candidato": c.metrics[metric],
                     "delta": c.metrics[metric] - b.metrics[metric],
                     "melhora": c.metrics[metric] < b.metrics[metric]})
    df = pd.DataFrame(rows)
    df.loc[len(df)] = {"fold": "MEDIA", "n": df["n"].sum(),
                       "baseline": df["baseline"].mean(), "candidato": df["candidato"].mean(),
                       "delta": df["delta"].mean(), "melhora": bool(df["melhora"].all())}
    return df
