#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_mando_competicao.py
======================================
Fase A do passo (3). Duas medicoes (nao toca producao):

3a) DIAGNOSTICO DE RESIDUOS por contexto de mando e competicao. Treina o regressor
    de lambda (uniforme), e mede o residuo medio (real - previsto) no test-fold
    agrupado por neutral (0/1) e por is_friendly (0/1). Se o modelo ja captura
    `neutral`/competicao (que sao features), os residuos devem ser ~0 nos grupos.
    Um residuo sistematico por grupo = sinal nao capturado.

3b) PESO DE COMPETICAO. Treina lambda com sample_weight=tournament_weight (rebaixa
    amistosos) vs uniforme, e avalia num test-fold SO de jogos competitivos
    (is_friendly==0). Hipotese do guia: amistosos corrompem stats.
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from experiment_timedecay import gbr, opt_r, nb_pmf, ece_over, BASE_FEATS, FULL_FEATS

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def prep(df, target, feats, adv):
    d = df.copy()
    if adv:
        d = d[d["has_advanced_stats"] == 1]
    if isinstance(target, tuple):
        d = d.dropna(subset=list(target))
        d["_y"] = d[target[0]].astype(int) + d[target[1]].astype(int)
    else:
        d = d.dropna(subset=[target])
        d["_y"] = d[target].astype(int)
    return d.sort_values("date").reset_index(drop=True)


TARGETS = [
    ("Gols total", "total_goals", "BASE", False, 24),
    ("Esc. mandante", "home_cur_sb_corners", "FULL", True, 25),
    ("Esc. visitante", "away_cur_sb_corners", "FULL", True, 25),
    ("Cartoes total", ("home_cur_sb_cards", "away_cur_sb_cards"), "FULL", True, 30),
    ("Chutes total", ("home_cur_sb_shots", "away_cur_sb_shots"), "FULL", True, 60),
]


def feats_of(tag):
    return BASE_FEATS if tag == "BASE" else FULL_FEATS


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"], low_memory=False)
    out = ["# Experimento (3) — Mando triplo + Peso de competicao — Fase A", ""]

    # ---------------- 3a: residuos por contexto ----------------
    out.append("## 3a) Residuo medio (real - previsto) por contexto no test-fold")
    out.append("Se ~0 nos grupos, o modelo ja captura o contexto (nada a ganhar).")
    out.append("")
    out.append("| Alvo | Neutro (n) | Nao-neutro (n) | Amistoso (n) | Competitivo (n) |")
    out.append("|---|---|---|---|---|")
    for nm, tgt, ftag, adv, mc in TARGETS:
        d = prep(df, tgt, feats_of(ftag), adv)
        feats = feats_of(ftag)
        cut = d.iloc[int(len(d) * 0.8)]["date"]
        tr, te = d[d["date"] <= cut], d[d["date"] > cut]
        m = gbr(); m.fit(tr[feats], tr["_y"].values)
        te = te.copy(); te["_res"] = te["_y"].values - np.maximum(m.predict(te[feats]), 0.05)

        def grp(mask):
            s = te[mask]
            return f"{s['_res'].mean():+.3f} ({len(s)})" if len(s) else "– (0)"
        out.append(f"| {nm} | {grp(te['neutral']==1)} | {grp(te['neutral']==0)} | "
                   f"{grp(te['is_friendly']==1)} | {grp(te['is_friendly']==0)} |")

    # ---------------- 3b: peso de competicao ----------------
    out.append("")
    out.append("## 3b) Peso de competicao (sample_weight=tournament_weight) — avaliado SO em competitivos")
    out.append("")
    out.append("| Alvo | Vies unif | Vies pond | LogLoss unif | LogLoss pond | ECE unif | ECE pond |")
    out.append("|---|---|---|---|---|---|---|")
    for nm, tgt, ftag, adv, mc in TARGETS:
        d = prep(df, tgt, feats_of(ftag), adv)
        feats = feats_of(ftag)
        cut = d.iloc[int(len(d) * 0.8)]["date"]
        tr, te = d[d["date"] <= cut], d[d["date"] > cut]
        te = te[te["is_friendly"] == 0]                # so competitivos no teste
        if len(te) < 30:
            out.append(f"| {nm} | (poucos competitivos no teste: {len(te)}) |||||"); continue
        yt = te["_y"].values; real = float(yt.mean()); line = max(0.5, np.floor(d["_y"].mean()) + 0.5)
        res = {}
        for tag, w in [("unif", None), ("pond", tr["tournament_weight"].values)]:
            mm = gbr(); mm.fit(tr[feats], tr["_y"].values, reg__sample_weight=w)
            lam_tr = np.maximum(mm.predict(tr[feats]), 0.05)
            lam_te = np.maximum(mm.predict(te[feats]), 0.05)
            r = opt_r(tr["_y"].values, lam_tr)
            prob = nb_pmf(lam_te, r, mc)
            ll = float(-np.mean(np.log(prob[np.arange(len(te)), np.clip(yt, 0, mc)] + 1e-15)))
            res[tag] = (float(lam_te.mean() - real), ll, float(ece_over(prob, yt, line)))
        bu, lu, eu = res["unif"]; bp, lp, ep = res["pond"]
        out.append(f"| {nm} | {bu:+.3f} | {bp:+.3f} | {lu:.4f} | {lp:.4f} | {eu:.2%} | {ep:.2%} |")

    Path("scratch/experimento_historico/mando_competicao_faseA.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print("\nRelatorio: scratch/experimento_historico/mando_competicao_faseA.md")


if __name__ == "__main__":
    main()
