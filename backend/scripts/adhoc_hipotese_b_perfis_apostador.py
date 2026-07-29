#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_hipotese_b_perfis_apostador.py
==============================================
Hipotese B (v2, honesta) -- compara o MODELO DE PRODUCAO (via
Predictor.predict_from_row, artefato congelado 2025frozen) contra 3 perfis de
apostador "de feeling" pedidos originalmente pelo dono:

  1. Favoritista       -- sempre aposta no favorito do 1x2 (menor odd de mercado)
  2. Emocional por gols -- sempre aposta em Over 2.5 (BTTS nao esta disponivel
                           em data-test -- football-data.co.uk nao publica esse
                           mercado; registrado como limitacao, nao omitido)
  3. Faixa de odd       -- aposta no lado do 1x2 cuja odd de mercado (Avg) cai
                           em [1.70, 2.20] (o mais proximo de 1.95 se >1 lado
                           qualificar); pula o jogo se nenhum lado qualificar

METODOLOGIA (evita repetir o que a bateria de valor §20 ja fez e ja reprovou
-- ver DOCUMENTACAO_CENTRAL.md §20): usa a MESMA fonte de preco (book="Avg",
abertura) pra TODAS as estrategias, isolando habilidade de SELECAO (nao de
comparacao de casas, que e a Hipotese A). Bootstrap (20k reamostragens, IC95%
percentil) + correcao de multiplas comparacoes (Bonferroni e BH/FDR), mesmo
padrao de scripts/adhoc_w3_bootstrap.py. Resultado "sem edge robusto" e
aceito e reportado como valido -- a conclusao nao e decidida antes de rodar.

Uso: python scripts/adhoc_hipotese_b_perfis_apostador.py
Saida: data/reports/hipotese_b_perfis_apostador.csv
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

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT_DIR = ROOT / "data" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REF_BOOK = "Avg"  # mesma fonte de preco pra TODAS as estrategias (isola selecao, nao preco)
N_BOOT = 20000
SEED = 20260728
ALPHA = 0.05
FAIXA_LO, FAIXA_HI = 1.70, 2.20


def bootstrap_roi(net_returns: np.ndarray, n_boot: int, rng: np.random.Generator):
    n = len(net_returns)
    idx = rng.integers(0, n, size=(n_boot, n))
    roi_boot = 100.0 * net_returns[idx].sum(axis=1) / n
    return roi_boot


def analyze_group(label: str, net_returns: np.ndarray, rng: np.random.Generator) -> dict:
    n = len(net_returns)
    if n == 0:
        return dict(label=label, n=0, roi_pct=None, ci_lo=None, ci_hi=None,
                    excludes_zero=False, p_bootstrap=None)
    point_roi = 100.0 * net_returns.sum() / n
    boot = bootstrap_roi(net_returns, N_BOOT, rng)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    p_le0 = float((boot <= 0).mean())
    p_ge0 = float((boot >= 0).mean())
    p_boot = min(1.0, 2 * min(p_le0, p_ge0))
    return dict(label=label, n=n, roi_pct=round(point_roi, 3),
                ci_lo=round(float(lo), 3), ci_hi=round(float(hi), 3),
                excludes_zero=(lo > 0) or (hi < 0), p_bootstrap=round(p_boot, 4))


def main():
    print("=" * 90)
    print(" HIPOTESE B (v2) -- MODELO vs 3 PERFIS DE APOSTADOR (odds reais, mesma fonte de preco)")
    print("=" * 90)

    if not PREDICTIONS.exists():
        raise SystemExit(f"{PREDICTIONS} nao existe -- rode backtest_generate_predictions.py primeiro.")

    preds = pd.read_parquet(PREDICTIONS)
    matched = pd.read_parquet(MATCHED)
    odds = pd.read_parquet(ODDS)
    odds = odds[odds["book"] == REF_BOOK].copy()
    odds["_key5"] = list(zip(odds["source"], odds["div"], odds["date"],
                              odds["home_team_raw"], odds["away_team_raw"]))
    # Preferir fechamento, cai pra abertura se faltar (mesmo padrao de
    # adhoc_metrics_model_vs_naive.py::_pick_odds) -- BRA (xlsx) so publica a coluna
    # "closing", filtrar so abertura zerava Brasileirao inteiro (achado real desta sessao).
    odds = odds.sort_values("closing").drop_duplicates(
        subset=["_key5", "market", "side"], keep="last")
    # dict simples (nao DataFrame.loc) -- indexar por tupla via .loc confunde o pandas
    # com indexacao multi-eixo ("Too many indexers"), entao evitamos pivot_table+.loc.
    def _side_dict(sub_market):
        d = {}
        for k5, side, value in zip(sub_market["_key5"], sub_market["side"], sub_market["value"]):
            d.setdefault(k5, {})[side] = value
        return d

    odds_1x2 = _side_dict(odds[odds["market"] == "1x2"])
    odds_ou = _side_dict(odds[odds["market"] == "ou25"])

    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    matched_ok["_key5"] = list(zip(matched_ok["source"], matched_ok["div"], matched_ok["date"],
                                    matched_ok["home_team_raw"], matched_ok["away_team_raw"]))
    fx_to_key5 = dict(zip(matched_ok["fixture_id"], matched_ok["_key5"]))

    preds["prediction"] = preds["prediction_json"].map(json.loads)

    rows_1x2, rows_ou = [], []
    for r in preds.itertuples(index=False):
        key5 = fx_to_key5.get(r.fixture_id)
        if key5 is None:
            continue
        pred = r.prediction
        home, away = r.home_team, r.away_team
        hg, ag = r.home_score, r.away_score
        actual = "H" if hg > ag else ("A" if ag > hg else "D")
        total = hg + ag

        row = odds_1x2.get(key5)
        if row is not None:
            oh, od, oa = row.get("H"), row.get("D"), row.get("A")
            if oh is not None and od is not None and oa is not None:
                probs = pred.get("vencedor", {}).get("probabilidades", {})
                p_home, p_draw, p_away = probs.get(home), probs.get("Empate"), probs.get(away)
                model_pick = (["H", "D", "A"][int(np.argmax([p_home, p_draw, p_away]))]
                              if None not in (p_home, p_draw, p_away) else None)
                fav_pick = ["H", "D", "A"][int(np.argmin([oh, od, oa]))]
                odd_map = {"H": oh, "D": od, "A": oa}
                in_range = [s for s in ("H", "D", "A") if FAIXA_LO <= odd_map[s] <= FAIXA_HI]
                faixa_pick = min(in_range, key=lambda s: abs(odd_map[s] - 1.95)) if in_range else None
                rows_1x2.append(dict(
                    fixture_id=r.fixture_id, tournament=r.tournament, actual=actual,
                    odd_H=oh, odd_D=od, odd_A=oa,
                    model_pick=model_pick, fav_pick=fav_pick, faixa_pick=faixa_pick,
                ))

        row_ou = odds_ou.get(key5)
        if row_ou is not None:
            oo, ou = row_ou.get("over"), row_ou.get("under")
            if oo is not None and ou is not None:
                p_over = pred.get("over_2_5", {}).get("prob_sim")
                model_pick_ou = ("over" if p_over >= 50.0 else "under") if p_over is not None else None
                rows_ou.append(dict(
                    fixture_id=r.fixture_id, tournament=r.tournament,
                    over_won=total > 2.5, odd_over=oo, odd_under=ou, model_pick=model_pick_ou,
                ))

    df1x2 = pd.DataFrame(rows_1x2)
    dfou = pd.DataFrame(rows_ou)
    print(f"\nJogos 1x2 com odd Avg completa (H/D/A): {len(df1x2)}")
    print(f"Jogos O/U 2.5 com odd Avg completa: {len(dfou)}")

    def net_return(pick_col, odd_map_cols, df):
        picks = df[pick_col]
        mask = picks.notna()
        sub = df[mask]
        odds_taken = np.array([sub[f"odd_{p}"].iloc[i] for i, p in enumerate(sub[pick_col])])
        won = (sub[pick_col].to_numpy() == sub["actual"].to_numpy())
        return np.where(won, odds_taken - 1.0, -1.0), sub["tournament"].to_numpy()

    strategies_1x2 = {}
    if len(df1x2):
        for col, name in [("model_pick", "modelo_1x2"), ("fav_pick", "favoritista"),
                           ("faixa_pick", "faixa_odd_1.70_2.20")]:
            net, tourn = net_return(col, None, df1x2)
            strategies_1x2[name] = (net, tourn)

    strategies_ou = {}
    if len(dfou):
        mask_model = dfou["model_pick"].notna()
        sub = dfou[mask_model]
        odd_taken = np.where(sub["model_pick"] == "over", sub["odd_over"], sub["odd_under"])
        won = np.where(sub["model_pick"] == "over", sub["over_won"], ~sub["over_won"])
        strategies_ou["modelo_ou"] = (np.where(won, odd_taken - 1.0, -1.0), sub["tournament"].to_numpy())
        won_over = dfou["over_won"].to_numpy()
        strategies_ou["emocional_sempre_over"] = (
            np.where(won_over, dfou["odd_over"].to_numpy() - 1.0, -1.0), dfou["tournament"].to_numpy())

    rng = np.random.default_rng(SEED)
    combo_results = []
    print("\n--- 1x2: por liga x estrategia ---")
    for name, (net, tourn) in strategies_1x2.items():
        for lg in sorted(set(tourn)):
            m = tourn == lg
            if m.sum() < 5:
                continue
            r = analyze_group(f"{lg} / {name}", net[m], rng)
            r.update(strategy=name, tournament=lg, family="1x2")
            combo_results.append(r)
    print("\n--- O/U 2.5: por liga x estrategia ---")
    for name, (net, tourn) in strategies_ou.items():
        for lg in sorted(set(tourn)):
            m = tourn == lg
            if m.sum() < 5:
                continue
            r = analyze_group(f"{lg} / {name}", net[m], rng)
            r.update(strategy=name, tournament=lg, family="ou25")
            combo_results.append(r)

    combo_df = pd.DataFrame(combo_results)
    for r in combo_df.itertuples(index=False):
        flag = "EXCLUI 0" if r.excludes_zero else "inclui 0"
        print(f"  [{r.family}] {r.label:45s} N={r.n:4d}  ROI={r.roi_pct:+7.2f}%  "
              f"IC95%=[{r.ci_lo:+7.2f}%,{r.ci_hi:+7.2f}%]  ({flag})  p={r.p_bootstrap:.4f}")

    print("\n--- Pooled por estrategia (todas as ligas disponiveis juntas) ---")
    pooled_rows = []
    for fam, strategies in (("1x2", strategies_1x2), ("ou25", strategies_ou)):
        for name, (net, tourn) in strategies.items():
            r = analyze_group(name, net, rng)
            r.update(strategy=name, family=fam)
            pooled_rows.append(r)
            flag = "EXCLUI 0" if r["excludes_zero"] else "inclui 0"
            print(f"  [{fam}] {name:25s} N={r['n']:4d}  ROI={r['roi_pct']:+7.2f}%  "
                  f"IC95%=[{r['ci_lo']:+7.2f}%,{r['ci_hi']:+7.2f}%]  ({flag})  p={r['p_bootstrap']:.4f}")
    pooled_df = pd.DataFrame(pooled_rows)

    # --- correcao de multiplas comparacoes nos combos liga x estrategia ---
    m = len(combo_df)
    if m > 0:
        pvals = combo_df["p_bootstrap"].to_numpy()
        bonf_sig = pvals < (ALPHA / m)
        order = np.argsort(pvals)
        ranked = pvals[order]
        bh_thresh = (np.arange(1, m + 1) / m) * ALPHA
        bh_pass = ranked <= bh_thresh
        bh_sig = np.zeros(m, dtype=bool)
        if bh_pass.any():
            k_max = np.max(np.where(bh_pass)[0])
            sorted_sig = np.zeros(m, dtype=bool)
            sorted_sig[: k_max + 1] = True
            bh_sig[order] = sorted_sig
        combo_df["bonferroni_sig_0.05"] = bonf_sig
        combo_df["bh_fdr_sig_0.05"] = bh_sig
        n_sig_raw = int((pvals < ALPHA).sum())
        print(f"\nCorrecao de multiplas comparacoes ({m} combos liga x estrategia): "
              f"p<0.05 bruto={n_sig_raw} | Bonferroni sig={int(bonf_sig.sum())} | BH/FDR sig={int(bh_sig.sum())}")

    combo_df.to_csv(OUT_DIR / "hipotese_b_perfis_apostador_combos.csv", index=False)
    pooled_df.to_csv(OUT_DIR / "hipotese_b_perfis_apostador_pooled.csv", index=False)
    print(f"\nSalvo: {OUT_DIR / 'hipotese_b_perfis_apostador_combos.csv'}")
    print(f"Salvo: {OUT_DIR / 'hipotese_b_perfis_apostador_pooled.csv'}")
    print("\nNOTA: BTTS/Ambas Marcam nao esta disponivel em data-test (football-data.co.uk nao "
          "publica esse mercado) -- perfil 'emocional por gols' usa somente Over 2.5.")
    print("NOTA: 'sem edge robusto' (IC95% incluindo 0 / nao sobrevive a correcao) e um resultado "
          "valido -- corrobora DOCUMENTACAO_CENTRAL.md secao 20 se for o que sair, nao a contradiz.")


if __name__ == "__main__":
    main()
