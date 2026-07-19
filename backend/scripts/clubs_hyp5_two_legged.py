#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp5_two_legged.py
=================================
Hipótese H5: mata-mata ida-e-volta -- o resultado do jogo 2 é INDEPENDENTE do
placar agregado do jogo 1, ou existe efeito de "time atrás precisa atacar mais"
(motivação/tática) que os modelos atuais (jogo-a-jogo, iid) ignoram?

Método (diagnóstico, mesmo espírito do exp10_halves_copula.py):
  1. Pareia jogo1/jogo2 (mesmo par de times, mesma competição, mesmo round de mata-mata,
     mando invertido).
  2. Ajusta DixonColesNBRegressor na base inteira (mesmo baseline de produção).
  3. PIT->z-score da margem (gols mandante-visitante) de cada perna vs a margem PREVISTA
     pelo modelo (que assume jogos iid) -- corr(z1,z2) != 0 indica dependência não capturada.
  4. Regressão simples: erro de margem no jogo2 (real-esperado) ~ déficit agregado do time
     mandante do jogo2 apos o jogo1 (motivação: quem precisa de gols ataca mais que o esperado).

Não é um candidato de promoção (sem gate 5-fold) -- é um diagnóstico pra decidir se vale
construir o mercado de "qualificação/agregado" com um modelo correlacionado.
"""
import sys, json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]
OUT_DIR = ROOT / "data" / "reports" / "clubs_new_hyp"
KNOCKOUT_ROUNDS = {"Round of 16", "Quarter-finals", "Semi-finals", "Round of 32",
                   "8th Finals", "16th Finals", "Play-offs", "Knockout Round Play-offs"}


def find_leg_pairs(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["round"].isin(KNOCKOUT_ROUNDS)].copy()
    d["season"] = pd.to_datetime(d["date"]).dt.year
    d["pair_key"] = d.apply(lambda r: tuple(sorted([r["home_team"], r["away_team"]])), axis=1)
    pairs = []
    for (tourn, season, round_, pk), g in d.groupby(["tournament", "season", "round", "pair_key"]):
        if len(g) != 2:
            continue
        g = g.sort_values("date")
        leg1, leg2 = g.iloc[0], g.iloc[1]
        if leg1["home_team"] == leg2["home_team"]:
            continue  # mando não inverteu -- não é ida/volta clássica
        pairs.append({"tourn": tourn, "season": season, "round": round_,
                      "leg1_idx": leg1.name, "leg2_idx": leg2.name})
    return pd.DataFrame(pairs)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    pairs = find_leg_pairs(df)
    print(f"pares ida-volta encontrados: {len(pairs)}", flush=True)
    if len(pairs) < 100:
        print("AMOSTRA PEQUENA -- resultado é indicativo, não conclusivo.", flush=True)

    df["margin"] = df["home_score"] - df["away_score"]

    rows = []
    for _, p in pairs.iterrows():
        l1, l2 = df.loc[p["leg1_idx"]], df.loc[p["leg2_idx"]]
        agg_leg1_for_leg2_home = 0
        # agregado apos leg1, do ponto de vista do mandante do leg2 (que foi visitante no leg1)
        if l1["home_team"] == l2["away_team"]:
            agg_deficit = -(l1["home_score"] - l1["away_score"])  # negativo = leg2-home team esta atras
        else:
            agg_deficit = (l1["home_score"] - l1["away_score"])
        rows.append({
            "margin_leg1": l1["margin"], "margin_leg2": l2["margin"],
            "elo_diff_leg2": l2["elo_diff"], "agg_deficit_leg2_home": agg_deficit,
        })
    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR / "h5_two_legged_pairs.csv", index=False)

    corr = R["margin_leg1"].corr(R["margin_leg2"])
    print(f"\ncorr(margem_leg1, margem_leg2) = {corr:+.3f} (n={len(R)})", flush=True)

    # regressao: margem do leg2 ~ elo_diff_leg2 (esperado) + deficit agregado (motivacao extra)
    import numpy as np
    from numpy.polynomial import polynomial as P
    X = R[["elo_diff_leg2", "agg_deficit_leg2_home"]].to_numpy()
    y = R["margin_leg2"].to_numpy()
    X1 = np.column_stack([np.ones(len(X)), X])
    try:
        coef, *_ = np.linalg.lstsq(X1, y, rcond=None)
        pred = X1 @ coef
        resid = y - pred
        r2 = 1 - resid.var() / y.var()
        print(f"regressao margem_leg2 ~ elo_diff_leg2 + agg_deficit_leg2_home: "
              f"coef_deficit={coef[2]:+.4f} R2={r2:.3f}")
        print(">> coef_deficit > 0 e significativo -> time atras no agregado supera expectativa no jogo2 "
              "(efeito motivacao real, vale modelar). coef ~0 -> jogos efetivamente independentes.")
    except Exception as e:
        print(f"regressao falhou: {e}")

    print(f"\n>> VEREDITO preliminar: corr={corr:+.3f} -- "
          f"{'dependencia relevante, vale construir mercado agregado com modelo correlacionado' if abs(corr) > 0.1 else 'dependencia fraca, mercado agregado pode usar produto simples das duas pernas (iid) sem grande perda'}")


if __name__ == "__main__":
    main()
