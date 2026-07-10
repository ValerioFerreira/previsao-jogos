#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp15_referee_cards.py — EXPERIMENTO 15: Fator Árbitro no modelo de CARTÕES
==================================================================================
Hipótese (nova, destravada pela agregação de árbitros desta sessão): o rigor do
árbitro (`ref_strictness`, já computado por jogo em data/built/referee_features.csv)
prevê o total de cartões ALÉM das taxas rolantes das equipes. Cartões são o mercado
mais idiossincrático — parte da variância é do árbitro, não das equipes.

Modelo: GradientBoostingRegressor -> λ (Poisson) do TOTAL de cartões. Base = taxas
rolantes de cartões (l3/l5, feitos/sofridos, diffs) + contexto. Candidato = base +
ref_strictness.

Gate (§6): CV temporal expanding, reduzir a Log-loss (O/U cartões) e o NLL de Poisson
sem piorar o ECE, consistente nos folds. Só os jogos COM ref_strictness conhecido.
Saída: console + docs/EXP15_FATOR_ARBITRO_CARTOES.md (resumo manual).
"""
import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import log_loss

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "international_features_enriched_apifootball.csv"
REF = ROOT / "data" / "built" / "referee_features.csv"

BASE_FEATS = [
    "home_sb_cards_l3", "home_sb_cards_against_l3", "home_sb_cards_l5", "home_sb_cards_against_l5",
    "away_sb_cards_l3", "away_sb_cards_against_l3", "away_sb_cards_l5", "away_sb_cards_against_l5",
    "diff_sb_cards_l3", "diff_sb_cards_l5", "diff_sb_cards_against_l3", "diff_sb_cards_against_l5",
]
LINES = [3.5, 4.5, 5.5]


def ece_binary(y, p, nb=10):
    y = np.asarray(y); p = np.asarray(p)
    edges = np.linspace(0, 1, nb + 1)
    e = 0.0
    for i in range(nb):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < nb - 1 else p <= edges[i + 1])
        if m.sum() > 0:
            e += (m.sum() / len(y)) * abs(y[m].mean() - p[m].mean())
    return e


def fit_lambda(Xtr, ytr, Xte):
    m = HistGradientBoostingRegressor(loss="poisson", max_depth=3, learning_rate=0.05,
                                      max_iter=300, random_state=42)
    m.fit(Xtr, ytr)
    lam = np.clip(m.predict(Xte), 0.05, 20)
    return lam


def _supports_poisson():
    return True


def metrics(lam, ytrue):
    nll = float(-poisson.logpmf(ytrue, lam).mean())
    out = {"nll": nll}
    for L in LINES:
        k = int(np.floor(L))
        p_over = np.clip(1 - poisson.cdf(k, lam), 1e-6, 1 - 1e-6)
        yb = (ytrue > L).astype(int)
        if 0 < yb.sum() < len(yb):
            out[f"ll{L}"] = log_loss(yb, p_over, labels=[0, 1])
            out[f"ece{L}"] = ece_binary(yb, p_over)
    return out


def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    ref = pd.read_csv(REF, parse_dates=["date"])
    m = df.merge(ref[["date", "home_team", "away_team", "ref_strictness"]],
                 on=["date", "home_team", "away_team"], how="left")
    adv = m[(m.get("has_advanced_stats", 0) == 1)
            & m["home_cur_sb_cards"].notna() & m["away_cur_sb_cards"].notna()
            & m["ref_strictness"].notna()].copy()
    adv = adv.dropna(subset=BASE_FEATS)
    adv["total_cards"] = (adv["home_cur_sb_cards"] + adv["away_cur_sb_cards"]).astype(int)
    adv = adv.sort_values("date").reset_index(drop=True)
    adv["year"] = adv["date"].dt.year
    print(f"Jogos (com ref_strictness + cartões válidos): {len(adv)} | anos {adv.year.min()}-{adv.year.max()}")
    print(f"Poisson loss disponível: {_supports_poisson()}")

    years = sorted(adv["year"].unique())
    folds = [y for y in years if (adv["year"] < y).sum() >= 400 and (adv["year"] == y).sum() >= 60]
    rows = []
    for y in folds:
        tr = adv[adv["year"] < y]
        te = adv[adv["year"] == y]
        yte = te["total_cards"].values
        lam_b = fit_lambda(tr[BASE_FEATS], tr["total_cards"].values, te[BASE_FEATS])
        lam_x = fit_lambda(tr[BASE_FEATS + ["ref_strictness"]], tr["total_cards"].values,
                           te[BASE_FEATS + ["ref_strictness"]])
        mb, mx = metrics(lam_b, yte), metrics(lam_x, yte)
        rows.append({"fold": y, "n": len(te),
                     "base_nll": mb["nll"], "ref_nll": mx["nll"],
                     "base_ll45": mb.get("ll4.5", np.nan), "ref_ll45": mx.get("ll4.5", np.nan),
                     "base_ece45": mb.get("ece4.5", np.nan), "ref_ece45": mx.get("ece4.5", np.nan)})
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 140)
    print(R.round(4).to_string(index=False))

    dnll = (R.ref_nll - R.base_nll).mean()
    dll = (R.ref_ll45 - R.base_ll45).mean()
    dece = (R.ref_ece45 - R.base_ece45).mean()
    win_nll = int((R.ref_nll < R.base_nll).sum())
    win_ll = int((R.ref_ll45 < R.base_ll45).sum())
    n = len(R)
    print(f"\n>> dNLL {dnll:+.4f} (melhora {win_nll}/{n}) | dLL(O/U4.5) {dll:+.4f} (melhora {win_ll}/{n}) | dECE(4.5) {dece*100:+.2f}pp")
    aprovado = (dnll < 0 and win_nll >= n - 1) and (dll < 0 and win_ll >= n - 1) and (dece <= 0.002)
    print(f">> VEREDITO Fator Árbitro nos cartões: {'APROVADO' if aprovado else 'REPROVADO'}")


if __name__ == "__main__":
    main()
