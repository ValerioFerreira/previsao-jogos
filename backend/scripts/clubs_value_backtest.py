#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_value_backtest.py
=================================
Fase 8 do plano — backtest de valor (ROI/EV) em clubes.

VERIFICAÇÃO PRÉVIA (importante, honestidade do gate): `odds_registry` tem HOJE 64
linhas, TODAS de seleções (Copa do Mundo) — ZERO cobertura de clubes. O plano
previa "cobertura pequena"; na prática é NENHUMA. Portanto o backtest contra odds
REAIS de mercado não é possível para clubes nesta pesquisa.

O que este script faz em vez disso (deixado explícito no output, não maquiado
como equivalente a odds reais):
  1. Confirma e reporta a ausência de odds reais de clubes.
  2. Roda um backtest "de papel" com Kelly fracionário: aposta contra uma
     proxy de "mercado" = probabilidades de frequência histórica por liga
     (H/D/A não-condicional, um proxy do que um book preguiçoso/o consenso
     público cobriria), com overround realista (~6%). Isso testa se o MODELO
     tem edge sobre um baseline ingênuo — NÃO valida lucro contra bookmakers
     reais. Resultado rotulado "proxy", nunca "ROI real".

Uso: python scripts/clubs_value_backtest.py
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import temporal_folds, RESULT_ORDER

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_value"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def check_real_odds_coverage():
    from app.db.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT tournament, count(*) FROM odds_registry GROUP BY tournament")).fetchall()
    print("=== Cobertura real de odds_registry (por torneio) ===")
    total = 0
    club_rows = 0
    club_tournaments = {"Brasileirao Serie A", "Brasileirao Serie B", "Copa do Brasil",
                        "Premier League", "La Liga", "Serie A Italia", "Bundesliga",
                        "Ligue 1", "Champions League", "Europa League",
                        "Conference League", "Copa Libertadores", "Copa Sul-Americana"}
    for tournament, n in rows:
        print(f"  {tournament}: {n}")
        total += n
        if tournament in club_tournaments:
            club_rows += n
    print(f"  TOTAL: {total} | clubes: {club_rows}")
    return club_rows


def kelly_fraction(p, odds, kelly_frac=0.25):
    """Kelly fracionário: fração do bankroll, odds decimais."""
    b = odds - 1.0
    q = 1.0 - p
    f = (b * p - q) / b
    return np.clip(f, 0, None) * kelly_frac


def proxy_market_odds(df_train, df_test, overround=0.06):
    """Proxy de mercado: frequência histórica H/D/A por liga (TREINO), com overround
    distribuído proporcionalmente (não é uma odds real — é o baseline "ingênuo" que
    o modelo precisa bater para ter edge genuíno)."""
    freq = df_train.groupby("league_id")["result"].value_counts(normalize=True).unstack().fillna(1e-3)
    global_freq = df_train["result"].value_counts(normalize=True)
    out = np.zeros((len(df_test), 3))
    for i, (lid,) in enumerate(zip(df_test["league_id"])):
        f = freq.loc[lid] if lid in freq.index else global_freq
        p = np.array([f.get(c, 1e-3) for c in RESULT_ORDER])
        p = p / p.sum()
        out[i] = p
    # aplica overround (probabilidades implícitas somam 1+overround)
    odds = 1.0 / (out * (1 + overround))
    return odds, out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    club_rows = check_real_odds_coverage()
    if club_rows == 0:
        print("\n[CONCLUSÃO] Zero odds reais de clubes disponíveis. Backtest de ROI real "
              "de clubes NÃO é possível com os dados atuais — só será viável quando o "
              "CollectOdds (ou equivalente) passar a coletar snapshots de clubes.\n")

    bf = json.load(open(META, encoding="utf-8"))["base_feats"]
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    df = df.sort_values("date").reset_index(drop=True)

    print("=== Backtest de PAPEL (proxy de mercado, Kelly 1/4) — NÃO é ROI real ===")
    rows = []
    bankroll = 1.0
    history = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[bf].fillna(tr[bf].median(numeric_only=True))
        X_te = te[bf].fillna(tr[bf].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        p_model = m.predict_proba_markets(X_te)["result"][:, ::-1]  # H,D,A

        odds_proxy, p_market = proxy_market_odds(tr, te)
        y_idx = te["result"].map(Y_MAP).to_numpy()

        fold_pnl = 0.0
        n_bets = 0
        for i in range(len(te)):
            for k in range(3):
                edge = p_model[i, k] * odds_proxy[i, k] - 1.0
                if edge > 0.02:  # exige edge mínimo (evita ruído de MLE)
                    stake = kelly_fraction(p_model[i, k], odds_proxy[i, k])
                    if stake <= 0:
                        continue
                    n_bets += 1
                    won = (y_idx[i] == k)
                    pnl = stake * (odds_proxy[i, k] - 1.0) if won else -stake
                    fold_pnl += pnl
        rows.append({"fold": fold, "n_test": len(te), "n_bets": n_bets, "pnl": fold_pnl,
                    "yield_pct": 100 * fold_pnl / max(n_bets, 1)})
        bankroll += fold_pnl
        print(f"  {fold}: {n_bets} apostas | pnl={fold_pnl:+.3f} | "
              f"yield={100*fold_pnl/max(n_bets,1):+.2f}%", flush=True)

    res = pd.DataFrame(rows)
    res.to_csv(OUT_DIR / "paper_backtest.csv", index=False)
    total_bets = res["n_bets"].sum()
    total_pnl = res["pnl"].sum()
    print(f"\n===== RESUMO (proxy, NÃO é ROI de mercado real) =====")
    print(f"total apostas: {total_bets} | pnl total: {total_pnl:+.3f} | "
          f"yield médio: {100*total_pnl/max(total_bets,1):+.2f}%")
    print("\nAVISO: este número mede edge do modelo sobre um proxy de frequência "
         "histórica, não sobre odds de bookmaker reais. Não usar como validação "
         "de rentabilidade — só como diagnóstico de calibração relativa.")


if __name__ == "__main__":
    main()
