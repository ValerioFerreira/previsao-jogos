#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_shots_nb.py
=========================
Treina o modelo de producao ShotsNB (NB independente) com TIME DECAY, sobre a base
inteira (jogos com chutes validos), com as 243 features de meta["full_feats"].

H (meia-vida do decay) e SELECIONADO num split de validacao interno (nao no teste da
Fase A), entao o modelo final e treinado em TODA a base com o H escolhido.

Persiste api/model_artifacts/shots_nb.joblib. Nao toca nenhum outro artefato.
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("api").resolve()))
from shots_nb_model import ShotsNB

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV = Path("international_features_enriched_apifootball.csv")
META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
FEATS = META["full_feats"]
OUT = Path("api/model_artifacts/shots_nb.joblib")
H_GRID = [None, 3, 2, 1]


def decay_w(dates, anchor, H):
    if H is None:
        return None
    return 0.5 ** ((anchor - dates).dt.days.values.astype(float) / (H * 365.0))


def _ece(y_over, p, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1); e = 0.0
    for i in range(n_bins):
        m = (p >= bins[i]) & (p < bins[i + 1])
        if m.mean() > 0:
            e += m.mean() * abs(y_over[m].mean() - p[m].mean())
    return e


def val_ece_total(model, Xv, ytv, line=22.5):
    """ECE da linha O/U do total na validacao — calibracao e o criterio do projeto."""
    pt = model.predict_distributions(Xv)["total"]
    return _ece((ytv > line).astype(int), pt[:, int(line) + 1:].sum(axis=1))


def main():
    print("=" * 78)
    print(" TREINO DE PRODUCAO — ShotsNB (NB + time decay) base inteira")
    print("=" * 78)
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_shots", "away_cur_sb_shots"]).sort_values("date").reset_index(drop=True)
    print(f"Jogos com chutes validos: {len(adv)}")

    yh = adv["home_cur_sb_shots"].astype(int).values
    ya = adv["away_cur_sb_shots"].astype(int).values

    # ---- selecao de H em split de validacao interno (80/20 temporal) ----
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tri, val = adv[adv["date"] <= cut], adv[adv["date"] > cut]
    anchor_tri = tri["date"].max()
    print(f"\n>> Selecao de H por ECE (treino<= {cut:%Y-%m-%d}, validacao depois)")
    ytv = (val["home_cur_sb_shots"].astype(int).values + val["away_cur_sb_shots"].astype(int).values)
    scores = []
    for H in H_GRID:
        w = decay_w(tri["date"], anchor_tri, H)
        m = ShotsNB(feats=FEATS)
        m.fit(tri[FEATS], tri["home_cur_sb_shots"].astype(int).values,
              tri["away_cur_sb_shots"].astype(int).values, sample_weight=w)
        ece = val_ece_total(m, val[FEATS], ytv)
        scores.append((H, ece))
        print(f"   {'sem decay' if H is None else f'H={H}':10s} -> val ECE(total) {ece:.2%}")
    # melhor ECE; desempate (dentro de 0,3pp) prefere H MAIOR (menos agressivo/mais robusto)
    best_ece = min(s[1] for s in scores)
    cand = [H for H, e in scores if e <= best_ece + 0.003]
    best_H = max([H for H in cand if H is not None], default=None)
    print(f">> H escolhido: {best_H if best_H else 'sem decay'} "
          f"(ECE {dict(scores).get(best_H):.2%}; desempate por robustez = H maior)")

    # ---- modelo final na base inteira com H escolhido ----
    anchor_full = adv["date"].max()
    w_full = decay_w(adv["date"], anchor_full, best_H)
    model = ShotsNB(feats=FEATS)
    model.fit(adv[FEATS], yh, ya, sample_weight=w_full)
    model.decay_H_ = best_H  # registra o H usado
    print(f"  r_H={model.r_H_:.2f} r_A={model.r_A_:.2f}")

    # vies global in-sample (sanidade)
    d = model.predict_distributions(adv[FEATS])
    ks = np.arange(model.max_corners + 1); kt = np.arange(2 * model.max_corners + 1)
    print("\n>> Vies global (in-sample):")
    print(f"  Mandante  real {yh.mean():.2f}  E[PMF] {(d['home']@ks).mean():.2f}")
    print(f"  Visitante real {ya.mean():.2f}  E[PMF] {(d['away']@ks).mean():.2f}")
    print(f"  Total     real {(yh+ya).mean():.2f}  E[PMF] {(d['total']@kt).mean():.2f}")

    model.save(str(OUT))
    print(f"\nOK. Artefato salvo: {OUT} (decay_H={best_H}). Nada mais foi tocado.")


if __name__ == "__main__":
    main()
