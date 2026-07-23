#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w3_reconstruct.py
================================
Bateria ad-hoc W3 (2026-07-22): reconstrucao FIEL da simulacao financeira
"5 estrategias ingenuas x 4 ligas" (Brasileirao/Premier League/La Liga/Serie A
Italiana) ja reportada em conversa anterior (favoritismo pooled ROI -4.14%
N=1408; Brasileirao/favoritismo +1.97% N=306; La Liga/placar_exato +0.52%
N=342), a partir de:

  - data/built/backtest_valuebet_dataset.parquet -- 8117 fixtures, todas as
    ligas, com odds book "Avg" (abertura E fechamento) + probabilidades do
    modelo congelado 2025 (ver scripts/adhoc_value_groundwork.py).
  - data/built/backtest_predictions.parquet -- prediction_json cru, usado
    aqui so pra extrair o pick de "placar_exato" (nao esta no dataset acima).

Regra de odd usada (documentada no pedido, reproduzida aqui):
  - Mercados 1x2 (favoritismo, placar_exato): odd_open_<side>; se NaN
    (Brasileirao nao tem abertura na fonte), cai pra odd_close_<side>.
  - Mercado O/U 2,5 (sempre_under, sempre_over, modelo_escolhe): mesmo
    padrao odd_open_<side> -> odd_close_<side>, mas o Brasileirao nao tem
    NENHUMA das duas (fonte nao cobre O/U pra essa liga) -> N=0 pras 3
    estrategias de O/U no Brasileirao (17 = 20 - 3 combinacoes validas).

Nao mexe em model_artifacts*/predictor.py/app real. So leitura de parquet
local + calculo estatistico. Nao roda coleta nem treina nada.

Uso: python scripts/adhoc_w3_reconstruct.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VALUEBET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
OUT_DIR = ROOT / "data" / "reports" / "adhoc_valuebet_w3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAKE = 5.0
CUTOFF = pd.Timestamp("2025-07-01")  # corte do modelo congelado (backtest_train_frozen_model.py)

LEAGUES = [
    ("Brazil", "Brasileirao Serie A", "Brasileirao"),
    ("England", "Premier League", "Premier League"),
    ("Spain", "La Liga", "La Liga"),
    ("Italy", "Serie A Italia", "Serie A Italia"),
]


def odd_with_fallback(row, side, prefix):
    o = row.get(f"odd_open_{prefix}{side}")
    if pd.isna(o):
        o = row.get(f"odd_close_{prefix}{side}")
    return o


def build_bets(vb: pd.DataFrame, pr: pd.DataFrame) -> pd.DataFrame:
    """Monta a tabela longa de apostas (uma linha por fixture x estrategia)."""
    pr = pr.copy()
    pr["prediction"] = pr["prediction_json"].map(json.loads)

    def placar_exato_side(pred, home, away):
        top1 = pred["placar_exato"]["top"][0]
        i, j = top1["mandante"], top1["visitante"]
        if i > j:
            return "H"
        if j > i:
            return "A"
        return "D"

    def favoritismo_side(pred, home, away):
        w = pred["vencedor"]["vencedor"]
        if w == home:
            return "H"
        if w == away:
            return "A"
        return "D"

    pr["side_favoritismo"] = [
        favoritismo_side(p, h, a) for p, h, a in zip(pr["prediction"], pr["home_team"], pr["away_team"])
    ]
    pr["side_placar_exato"] = [
        placar_exato_side(p, h, a) for p, h, a in zip(pr["prediction"], pr["home_team"], pr["away_team"])
    ]

    df = vb.merge(pr[["fixture_id", "side_favoritismo", "side_placar_exato"]], on="fixture_id", how="inner")
    assert len(df) == len(vb), "merge deveria ser 1:1 (fixture_id unico nos dois lados)"

    rows = []
    for r in df.itertuples(index=False):
        rd = r._asdict()
        actual = rd["actual_result"]
        actual_over = rd["actual_over"]

        # 1) favoritismo
        side = rd["side_favoritismo"]
        odd = odd_with_fallback(rd, side, "")
        if pd.notna(odd):
            rows.append(dict(country=rd["country"], tournament=rd["tournament"], strategy="favoritismo",
                              fixture_id=rd["fixture_id"], date=rd["date"], odd=odd, won=(side == actual)))

        # 2) placar_exato
        side = rd["side_placar_exato"]
        odd = odd_with_fallback(rd, side, "")
        if pd.notna(odd):
            rows.append(dict(country=rd["country"], tournament=rd["tournament"], strategy="placar_exato",
                              fixture_id=rd["fixture_id"], date=rd["date"], odd=odd, won=(side == actual)))

        # 3) sempre_under 2,5
        odd = odd_with_fallback(rd, "under", "")
        if pd.notna(odd):
            rows.append(dict(country=rd["country"], tournament=rd["tournament"], strategy="sempre_under",
                              fixture_id=rd["fixture_id"], date=rd["date"], odd=odd, won=(not actual_over)))

        # 4) sempre_over 2,5
        odd = odd_with_fallback(rd, "over", "")
        if pd.notna(odd):
            rows.append(dict(country=rd["country"], tournament=rd["tournament"], strategy="sempre_over",
                              fixture_id=rd["fixture_id"], date=rd["date"], odd=odd, won=actual_over))

        # 5) modelo_escolhe (O/U -- modelo decide over ou under pela prob>=0.5)
        side = "over" if rd["p_model_over"] >= 0.5 else "under"
        odd = odd_with_fallback(rd, side, "")
        if pd.notna(odd):
            won = actual_over if side == "over" else (not actual_over)
            rows.append(dict(country=rd["country"], tournament=rd["tournament"], strategy="modelo_escolhe",
                              fixture_id=rd["fixture_id"], date=rd["date"], odd=odd, won=won))

    out = pd.DataFrame(rows)
    out["stake"] = STAKE
    out["net_return"] = np.where(out["won"], out["odd"] * STAKE - STAKE, -STAKE)
    return out


def summarize(g: pd.DataFrame) -> dict:
    n = len(g)
    stake_total = n * STAKE
    lucro = g["net_return"].sum()
    return dict(n=n, lucro=round(float(lucro), 2), roi_pct=round(100 * lucro / stake_total, 4) if n else None,
                odd_media=round(float(g["odd"].mean()), 3) if n else None)


def main():
    vb = pd.read_parquet(VALUEBET)
    pr = pd.read_parquet(PREDICTIONS)

    league_filter = vb[["country", "tournament"]].drop_duplicates()
    keep = set((c, t) for c, t, _ in LEAGUES)
    vb4 = vb[vb.apply(lambda r: (r["country"], r["tournament"]) in keep, axis=1)].copy()
    pr4 = pr[pr["fixture_id"].isin(vb4["fixture_id"])].copy()

    print(f"Fixtures nas 4 ligas: {len(vb4)} (de {len(vb)} totais no dataset)")
    for c, t, label in LEAGUES:
        n = len(vb4[(vb4.country == c) & (vb4.tournament == t)])
        print(f"  {label}: {n}")

    bets = build_bets(vb4, pr4)
    bets.to_parquet(OUT_DIR / "bets_long.parquet", index=False)
    print(f"\n{len(bets)} apostas construidas (5 estrategias x 4 ligas, R${STAKE:.2f} cada) -> "
          f"{OUT_DIR / 'bets_long.parquet'}")

    label_map = {c: label for c, t, label in LEAGUES for c in [c]}
    tour_label = {(c, t): label for c, t, label in LEAGUES}
    bets["league"] = [tour_label[(c, t)] for c, t in zip(bets["country"], bets["tournament"])]

    print("\n=== Combinacoes liga x estrategia (reconstrucao) ===")
    combo_rows = []
    for (league, strategy), g in bets.groupby(["league", "strategy"]):
        s = summarize(g)
        combo_rows.append(dict(league=league, strategy=strategy, **s))
        print(f"  {league:14s} / {strategy:14s}: N={s['n']:4d}  ROI={s['roi_pct']:+7.2f}%  "
              f"lucro=R${s['lucro']:+8.2f}  odd_media={s['odd_media']}")
    combo_df = pd.DataFrame(combo_rows).sort_values(["strategy", "league"])
    combo_df.to_csv(OUT_DIR / "combo_summary.csv", index=False)
    print(f"\nN de combinacoes validas (N>0): {(combo_df['n'] > 0).sum()} "
          f"(esperado 17 -- 20 menos as 3 de O/U do Brasileirao sem cobertura)")

    print("\n=== Pooled por estrategia (4 ligas somadas) ===")
    pooled_rows = []
    for strategy, g in bets.groupby("strategy"):
        s = summarize(g)
        pooled_rows.append(dict(strategy=strategy, **s))
        print(f"  {strategy:14s}: N={s['n']:4d}  ROI={s['roi_pct']:+7.2f}%  lucro=R${s['lucro']:+8.2f}")
    pooled_df = pd.DataFrame(pooled_rows)
    pooled_df.to_csv(OUT_DIR / "pooled_by_strategy.csv", index=False)

    grand = summarize(bets)
    print(f"\n=== Grand pooled (tudo) === N={grand['n']} ROI={grand['roi_pct']}% lucro=R${grand['lucro']}")

    print("\n=== Checagem contra numeros ja reportados (conferir antes de bootstrapar) ===")
    fav = combo_df[(combo_df.strategy == "favoritismo")]
    fav_pooled = pooled_df[pooled_df.strategy == "favoritismo"].iloc[0]
    print(f"  favoritismo pooled: ROI={fav_pooled['roi_pct']}% N={fav_pooled['n']}  "
          f"(esperado: ROI=-4.14% N=1408)")
    bra_fav = combo_df[(combo_df.league == "Brasileirao") & (combo_df.strategy == "favoritismo")].iloc[0]
    print(f"  Brasileirao/favoritismo: ROI={bra_fav['roi_pct']}% N={bra_fav['n']}  "
          f"(esperado: ROI=+1.97% N=306)")
    ll_pe = combo_df[(combo_df.league == "La Liga") & (combo_df.strategy == "placar_exato")].iloc[0]
    print(f"  La Liga/placar_exato: ROI={ll_pe['roi_pct']}% N={ll_pe['n']}  "
          f"(esperado: ROI=+0.52% N=342)")

    # --- Achado extra: leakage potencial no Brasileirao (corte do modelo congelado é
    # 2025-07-01; a temporada brasileira 2025 comeca em marco, ANTES do corte -- parte
    # da amostra "OOS" do Brasileirao pode ter sido vista no treino) ---
    print("\n=== Checagem de vazamento temporal (corte do modelo congelado: 2025-07-01) ===")
    bra_bets = bets[bets.league == "Brasileirao"]
    bra_dates = vb4[(vb4.country == "Brazil") & (vb4.tournament == "Brasileirao Serie A")][["fixture_id", "date"]]
    bra_bets = bra_bets.merge(bra_dates, on="fixture_id", suffixes=("", "_y"))
    pre = bra_bets[bra_bets["date"] < CUTOFF]
    post = bra_bets[bra_bets["date"] >= CUTOFF]
    print(f"  Apostas Brasileirao com data < corte (potencial in-sample): {pre.fixture_id.nunique()} fixtures unicos")
    print(f"  Apostas Brasileirao com data >= corte (OOS genuina): {post.fixture_id.nunique()} fixtures unicos")
    for strategy in ("favoritismo", "placar_exato"):
        g_all = bra_bets[bra_bets.strategy == strategy]
        g_pre = pre[pre.strategy == strategy]
        g_post = post[post.strategy == strategy]
        print(f"  Brasileirao/{strategy}: TODOS N={len(g_all)} ROI={summarize(g_all)['roi_pct']}%  |  "
              f"PRE-corte(suspeito) N={len(g_pre)} ROI={summarize(g_pre)['roi_pct']}%  |  "
              f"POS-corte(limpo) N={len(g_post)} ROI={summarize(g_post)['roi_pct']}%")

    bra_bets.to_parquet(OUT_DIR / "brasileirao_bets_with_cutoff_flag.parquet", index=False)

    print(f"\nArquivos salvos em {OUT_DIR}")


if __name__ == "__main__":
    main()
