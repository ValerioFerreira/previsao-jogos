#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_deep_tabular.py
===============================
Fase 6.7 (opcional, baixa prioridade — a literatura diz que DL tabular não bate
GBM em futebol; ver docs/PESQUISA_CLUBES.md §2.1). MLP compacto (não um TabNet/
FT-Transformer completo — desproporcional para o ganho esperado) com early
stopping, sobre as 158 base_feats, mesmo protocolo dos demais candidatos.

Uso: python scripts/clubs_deep_tabular.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, compare, FoldResult)
from dixon_coles_model import DixonColesNBRegressor

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_advanced"
Y_MAP = {"H": 0, "D": 1, "A": 2}
torch.manual_seed(42)


class TabularMLP(nn.Module):
    def __init__(self, n_in, n_hidden=128, n_classes=3, p_drop=0.3):
        super().__init__()
        self.net = nn.Sequential(
            nn.BatchNorm1d(n_in),
            nn.Linear(n_in, n_hidden), nn.ReLU(), nn.Dropout(p_drop),
            nn.Linear(n_hidden, n_hidden // 2), nn.ReLU(), nn.Dropout(p_drop),
            nn.Linear(n_hidden // 2, n_classes),
        )

    def forward(self, x):
        return self.net(x)


def fit_mlp(X_tr, y_tr, X_val, y_val, n_in, epochs=60, patience=8, lr=1e-3, wd=1e-4):
    model = TabularMLP(n_in)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    lossf = nn.CrossEntropyLoss()
    Xt = torch.tensor(X_tr, dtype=torch.float32)
    yt = torch.tensor(y_tr, dtype=torch.long)
    Xv = torch.tensor(X_val, dtype=torch.float32)
    yv = torch.tensor(y_val, dtype=torch.long)
    best_val, best_state, bad = np.inf, None, 0
    n = len(Xt)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            out = model(Xt[idx])
            loss = lossf(out, yt[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            val_loss = lossf(model(Xv), yv).item()
        if val_loss < best_val - 1e-4:
            best_val, best_state, bad = val_loss, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model


def main():
    bf = json.load(open(META, encoding="utf-8"))["base_feats"]
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    df = df.sort_values("date").reset_index(drop=True)
    print(f"dataset: {len(df)} jogos | torch {torch.__version__} (CPU)")

    baseline, candidate = [], []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        med = tr[bf].median(numeric_only=True)
        X_tr_full = tr[bf].fillna(med).to_numpy(dtype=np.float32)
        X_te = te[bf].fillna(med).to_numpy(dtype=np.float32)
        mu, sd = X_tr_full.mean(axis=0), X_tr_full.std(axis=0) + 1e-6
        X_tr_full = (X_tr_full - mu) / sd
        X_te = (X_te - mu) / sd
        y_tr_full = tr["result"].map(Y_MAP).to_numpy()
        y_te = te["result"].map(Y_MAP).to_numpy()

        cut = int(len(X_tr_full) * 0.85)
        X_tr, X_val = X_tr_full[:cut], X_tr_full[cut:]
        y_tr, y_val = y_tr_full[:cut], y_tr_full[cut:]

        m = fit_mlp(X_tr, y_tr, X_val, y_val, n_in=len(bf))
        with torch.no_grad():
            logits = m(torch.tensor(X_te, dtype=torch.float32))
            probs = torch.softmax(logits, dim=1).numpy()
        met_mlp = {"logloss": multiclass_logloss(y_te, probs), "rps": rps_hda(y_te, probs),
                  "ece": ece_multiclass(y_te, probs), "accuracy": accuracy(y_te, probs)}
        candidate.append(FoldResult(fold, len(te), met_mlp))

        Xb_tr = pd.DataFrame(tr[bf].fillna(med))
        Xb_te = pd.DataFrame(te[bf].fillna(med))
        dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                   max_goals=12, random_state=42)
        dc.fit(Xb_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        p_dc = dc.predict_proba_markets(Xb_te)["result"][:, ::-1]
        met_dc = {"logloss": multiclass_logloss(y_te, p_dc), "rps": rps_hda(y_te, p_dc),
                 "ece": ece_multiclass(y_te, p_dc), "accuracy": accuracy(y_te, p_dc)}
        baseline.append(FoldResult(fold, len(te), met_dc))
        print(f"  {fold}: MLP ll={met_mlp['logloss']:.4f} | DC-NB ll={met_dc['logloss']:.4f}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    comp = compare(baseline, candidate, metric="logloss")
    comp.to_csv(OUT_DIR / "deep_tabular.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    print(f"\n[deep_tabular MLP] {wins}/5 folds melhoram vs DC-NB | "
          f"delta {comp.iloc[-1]['delta']:+.4f}")
    print("Confirma/refuta a literatura (DL tabular não bate GBM em futebol)?",
         "SIM bate" if wins >= 4 else "NÃO bate (confirma literatura)")


if __name__ == "__main__":
    main()
