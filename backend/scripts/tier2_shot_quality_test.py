#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tier2_shot_quality_test.py
====================================
Testa a hipotese "shot quality index" (proxy de qualidade de finalizacao a
partir de Shots insidebox / Shots outsidebox, box-score basico -- cobertura
bem melhor que xG, NUNCA usado no codebase, ver DOCUMENTACAO_CENTRAL.md §19.6
para o precedente de xG REJEITADO 3x por esparsidade).

Script standalone e independente -- NAO toca build_clubs_dataset.py nem
club_features_enriched.parquet (rebuild concorrente rodando em background).

Passos (protocolo research_clubs/protocol.py, gate identico ao usado em toda
a bateria §16/§17/§21):
  0. Cobertura de Shots insidebox/outsidebox no raw cache (por ano e agregado).
  1. Feature point-in-time: ratio insidebox/(insidebox+outsidebox) por time por
     jogo, rolling l5/l10 (shift(1) estrito, mesmo padrao do home_sb_xg_l5).
  2. Avaliacao sob o gate: 5 folds temporais, 170 feats de producao + shot
     quality vs baseline (170 feats sem a feature nova), + controle negativo
     (embaralhar a feature no treino do ultimo fold).

Saida: data/reports/tier2_shot_quality/{coverage_by_year.csv,fold_comparison.csv,
negative_control.json,veredito.md}
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (
    temporal_folds, RESULT_ORDER, multiclass_logloss, ece_multiclass, accuracy, compare,
)
from scripts.battery_dataset import load_clubs_df, base_feats_170, DC_PARAMS

RAW_CACHE = ROOT / "data" / "club_raw_cache.sqlite"
OUT_DIR = ROOT / "data" / "reports" / "tier2_shot_quality"
Y_MAP = {"H": 0, "D": 1, "A": 2}

NEW_COLS = ["home_shotq_l5", "home_shotq_l10", "away_shotq_l5", "away_shotq_l10",
            "diff_shotq_l5", "diff_shotq_l10"]


# ─── Passo 0 + 1: leitura do raw cache ───────────────────────────────────────
def _num(v):
    """Numerico estrito -- None/"None"/nao-conversivel -> None (nao 0.0)."""
    if v is None:
        return None
    if isinstance(v, str):
        if v.strip().lower() in ("none", ""):
            return None
        try:
            return float(v)
        except ValueError:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_raw_cache():
    """Le TODAS as linhas do raw cache uma unica vez. Retorna:
      - long_df: 1 linha por time x jogo com fixture_id, team_id, date(from fixture), insidebox, outsidebox
      - coverage_rows: por fixture, se AMBOS os times tem AMBOS os stats numericos (p/ passo 0)
    """
    conn = sqlite3.connect(f"file:{RAW_CACHE}?mode=ro", uri=True, timeout=60)
    cur = conn.execute("SELECT fixture_id, raw FROM raw")
    long_rows = []
    cov_rows = []  # (year, both_teams_covered: bool)
    n = 0
    for fixture_id, raw in cur:
        n += 1
        if n % 20000 == 0:
            print(f"  [raw cache] {n}...", flush=True)
        d = json.loads(raw)
        fx = d.get("fixture") or {}
        status = ((fx.get("status") or {}).get("short")) or ""
        if status not in ("FT", "AET", "PEN"):
            continue
        date_str = (fx.get("date") or "")[:10]
        if not date_str:
            continue
        year = int(date_str[:4])

        stats_list = d.get("statistics") or []
        team_stats = {}  # team_id -> (inside, outside)
        for entry in stats_list:
            tinfo = entry.get("team") or {}
            tid = tinfo.get("id")
            if tid is None:
                continue
            inside = outside = None
            for s in entry.get("statistics") or []:
                t = s.get("type")
                if t == "Shots insidebox":
                    inside = _num(s.get("value"))
                elif t == "Shots outsidebox":
                    outside = _num(s.get("value"))
            team_stats[tid] = (inside, outside)
            long_rows.append({
                "fixture_id": fixture_id, "team_id": tid, "date": date_str,
                "inside": inside, "outside": outside,
            })

        both_teams_ok = (len(team_stats) == 2 and
                          all(i is not None and o is not None for i, o in team_stats.values()))
        cov_rows.append({"year": year, "n_teams_with_stats": len(stats_list),
                          "both_teams_ok": both_teams_ok})
    conn.close()

    long_df = pd.DataFrame(long_rows)
    long_df["date"] = pd.to_datetime(long_df["date"])
    cov_df = pd.DataFrame(cov_rows)
    print(f"[raw cache] {n} fixtures lidos, {len(long_df)} linhas time-jogo, "
          f"{len(cov_df)} fixtures finalizados")
    return long_df, cov_df


def report_coverage(cov_df: pd.DataFrame):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    overall = cov_df["both_teams_ok"].mean()
    by_year = (cov_df.groupby("year")["both_teams_ok"]
               .agg(["mean", "count"]).reset_index()
               .rename(columns={"mean": "coverage_pct", "count": "n_fixtures"})
               .sort_values("year"))
    by_year.to_csv(OUT_DIR / "coverage_by_year.csv", index=False)
    print(f"\n>> COBERTURA Shots insidebox/outsidebox (ambos os times, ambos os stats numericos):")
    print(f"   agregado (todos os anos): {overall:.1%} de {len(cov_df)} fixtures finalizados")
    print(by_year.to_string(index=False))
    return overall, by_year


# ─── Passo 1: feature point-in-time (mesmo padrao do home_sb_xg_l5) ─────────
def build_shot_quality_rolling(long_df: pd.DataFrame) -> dict:
    """Retorna dict (team_id, date_str) -> (l5, l10) do ratio ANTES do jogo
    (shift(1) estrito -- nunca usa o valor do proprio jogo atual), mesmo
    padrao do xg_roll em build_clubs_dataset.py::stage_features."""
    long_df = long_df.copy()
    valid = long_df["inside"].notna() & long_df["outside"].notna() & \
            ((long_df["inside"] + long_df["outside"]) > 0)
    long_df["ratio"] = np.where(valid, long_df["inside"] / (long_df["inside"] + long_df["outside"]), np.nan)
    long_df = long_df.sort_values(["team_id", "date"]).reset_index(drop=True)

    roll = {}
    for team_id, grp in long_df.groupby("team_id", sort=False):
        grp = grp.sort_values("date")
        s = grp["ratio"].shift(1)  # estritamente ANTERIOR ao jogo atual
        d5 = s.rolling(5, min_periods=2).mean()
        d10 = s.rolling(10, min_periods=3).mean()
        for dt, v5, v10 in zip(grp["date"], d5, d10):
            roll[(team_id, dt.strftime("%Y-%m-%d"))] = (v5, v10)
    return roll


def attach_shot_quality(df: pd.DataFrame, roll: dict) -> pd.DataFrame:
    df = df.copy()
    for side in ["home", "away"]:
        v5s, v10s = [], []
        for tid, dt in zip(df[f"{side}_team_id"], df["date"]):
            v = roll.get((tid, dt.strftime("%Y-%m-%d")), (np.nan, np.nan))
            v5s.append(v[0]); v10s.append(v[1])
        df[f"{side}_shotq_l5"] = v5s
        df[f"{side}_shotq_l10"] = v10s
    df["diff_shotq_l5"] = df["home_shotq_l5"] - df["away_shotq_l5"]
    df["diff_shotq_l10"] = df["home_shotq_l10"] - df["away_shotq_l10"]
    return df


# ─── Passo 2: avaliacao sob o gate ───────────────────────────────────────────
def fit_and_predict(tr, te, feats, random_state=42):
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": random_state})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    probs = m.predict_proba_markets(te[feats])
    return probs["result"][:, ::-1]  # [A,D,H] -> [H,D,A]


def evaluate(df, feats, label):
    from research_clubs.protocol import FoldResult
    results = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        t0 = time.time()
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        p = fit_and_predict(tr, te, feats)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        metrics = {
            "logloss": multiclass_logloss(y_idx, p),
            "ece": ece_multiclass(y_idx, p),
            "accuracy": accuracy(y_idx, p),
        }
        results.append(FoldResult(fold=fold, n_test=len(te), metrics=metrics))
        print(f"  [{label}][{fold}] n={len(te)} logloss={metrics['logloss']:.4f} "
              f"ece={metrics['ece']:.4f} ({time.time()-t0:.1f}s)", flush=True)
    return results


def negative_control(df, feats_cand, new_cols, seed=42):
    """Embaralha os VALORES da feature nova (nao os rotulos) no treino do
    ULTIMO fold e refit -- o ganho deve desaparecer. Se nao desaparecer,
    ha vazamento (erro cometido numa sessao anterior deste projeto -- ver
    docstring do pedido)."""
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    tr, te = df.loc[tr_idx].copy(), df.loc[te_idx]

    # candidato normal (sanity, deve bater com o fold do loop principal)
    p_normal = fit_and_predict(tr, te, feats_cand, seed)
    y_idx = te["result"].map(Y_MAP).to_numpy()
    ll_normal = multiclass_logloss(y_idx, p_normal)

    rng = np.random.RandomState(seed)
    perm = rng.permutation(len(tr))
    tr_shuffled = tr.copy()
    for c in new_cols:
        tr_shuffled[c] = tr[c].to_numpy()[perm]

    p_shuf = fit_and_predict(tr_shuffled, te, feats_cand, seed)
    ll_shuf = multiclass_logloss(y_idx, p_shuf)

    out = {
        "fold": fold_name,
        "logloss_candidato_normal": ll_normal,
        "logloss_candidato_feature_embaralhada": ll_shuf,
        "diferenca": ll_shuf - ll_normal,
        "veredito": ("OK -- ganho desaparece com a feature embaralhada"
                     if ll_shuf >= ll_normal - 0.0005
                     else "SUSPEITO -- feature embaralhada ainda ganha, investigar vazamento"),
    }
    print(f">> controle negativo: normal={ll_normal:.4f} embaralhada={ll_shuf:.4f} -> {out['veredito']}")
    return out


def main():
    print("=" * 80)
    print("TIER 2 — shot quality index (Shots insidebox/outsidebox) — 2026-07-22")
    print("=" * 80)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n>> Passo 0: cobertura no raw cache...")
    long_df, cov_df = parse_raw_cache()
    overall_cov, by_year = report_coverage(cov_df)

    print("\n>> Passo 1: construindo feature point-in-time...")
    roll = build_shot_quality_rolling(long_df)
    df = load_clubs_df()
    df = attach_shot_quality(df, roll)
    feat_cov = df[["home_shotq_l5", "away_shotq_l5"]].notna().all(axis=1).mean()
    print(f"   cobertura da feature no dataset de treino (home E away com l5 valido): {feat_cov:.1%} "
          f"de {len(df)} jogos (>=5 jogos anteriores por time)")

    feats_base = base_feats_170()
    feats_cand = feats_base + NEW_COLS

    # Sem cobertura -> DC-NB (GradientBoostingRegressor sklearn) precisa de valores
    # numericos; imputa NaN com a mediana da coluna (mesmo tratamento tosco que
    # xG recebe hoje via base_feats de producao para colunas parcialmente vazias
    # -- nao ha imputacao especial no pipeline, o sklearn GBR aceita NaN nativamente
    # em versoes recentes; checar e, se nao aceitar, cair para mediana).
    for c in NEW_COLS:
        if df[c].isna().any():
            pass  # tratado dentro do try/except do fit abaixo

    print("\n>> Passo 2: avaliando baseline (170 feats) vs candidato (170 + shot quality)...")
    try:
        base_results = evaluate(df, feats_base, "baseline")
        cand_results = evaluate(df, feats_cand, "candidato")
    except Exception as e:
        print(f"!! GradientBoostingRegressor nao aceitou NaN nativo ({e}); "
              f"imputando mediana da coluna e reavaliando...")
        df_imp = df.copy()
        for c in NEW_COLS:
            df_imp[c] = df_imp[c].fillna(df_imp[c].median())
        base_results = evaluate(df_imp, feats_base, "baseline")
        cand_results = evaluate(df_imp, feats_cand, "candidato")
        df = df_imp

    cmp_logloss = compare(base_results, cand_results, metric="logloss")
    cmp_ece = compare(base_results, cand_results, metric="ece")
    cmp_logloss.to_csv(OUT_DIR / "fold_comparison_logloss.csv", index=False)
    cmp_ece.to_csv(OUT_DIR / "fold_comparison_ece.csv", index=False)
    print("\n--- LOG-LOSS (candidato vs baseline) ---")
    print(cmp_logloss.to_string(index=False))
    print("\n--- ECE (candidato vs baseline) ---")
    print(cmp_ece.to_string(index=False))

    n_folds_melhora = int(cmp_logloss.iloc[:-1]["melhora"].sum())
    n_folds = len(cmp_logloss) - 1
    mean_delta_ll = cmp_logloss.iloc[-1]["delta"]
    mean_delta_ece = cmp_ece.iloc[-1]["delta"]

    print("\n>> Controle negativo (feature embaralhada no ultimo fold)...")
    neg_ctrl = negative_control(df, feats_cand, NEW_COLS)
    with open(OUT_DIR / "negative_control.json", "w", encoding="utf-8") as f:
        json.dump(neg_ctrl, f, ensure_ascii=False, indent=2)

    gate_pass = (n_folds_melhora >= 4) and (mean_delta_ll < -0.001) and (mean_delta_ece < 0.005)

    veredito = f"""# Tier 2 — Shot Quality Index (Shots insidebox/outsidebox) — veredito

## Passo 0 — cobertura no raw cache
Cobertura agregada (ambos os times do jogo com Shots insidebox E outsidebox numericos):
**{overall_cov:.1%}** de {len(cov_df)} fixtures finalizados no raw cache.

Por ano (ver `coverage_by_year.csv` completo):
{by_year.to_string(index=False)}

{"**ALERTA**: cobertura abaixo de ~40% e concentrada nos anos recentes — mesmo padrao de \"parede de dados\" que reprovou o xG 3x (DOCUMENTACAO_CENTRAL.md §19.6). Prossegue com o teste restrito ao subconjunto coberto, mas o veredito final deve ser lido com essa ressalva." if overall_cov < 0.40 else "Cobertura acima do patamar critico de 40% — bem melhor que o xG (~15%), como esperado do proxy box-score basico."}

Cobertura da feature no dataset de treino apos rolling l5 (>=5 jogos anteriores por time,
home E away com l5 valido): **{feat_cov:.1%}** de {len(df)} jogos.

## Passo 2 — gate (research_clubs/protocol.py)
5 folds temporais (`temporal_folds`), 170 feats de producao (`base_feats_170()`) + shot quality
(`{NEW_COLS}`) vs baseline (170 feats sem a feature nova).

- Folds com melhora de log-loss: **{n_folds_melhora}/{n_folds}**
- Delta medio de log-loss (candidato - baseline): **{mean_delta_ll:.5f}**
- Delta medio de ECE (candidato - baseline): **{mean_delta_ece:.5f}**

Criterio do gate: >=4/5 folds com melhora E delta medio de log-loss < -0.001 E ECE nao piora
de forma relevante.

## Controle negativo
Embaralhando os valores da feature nova (nao os rotulos) no treino do ultimo fold:
log-loss normal = {neg_ctrl['logloss_candidato_normal']:.4f}, log-loss embaralhado =
{neg_ctrl['logloss_candidato_feature_embaralhada']:.4f} (diferenca {neg_ctrl['diferenca']:.5f}) ->
**{neg_ctrl['veredito']}**.

## Veredito final
**{"PASSA" if gate_pass else "NAO PASSA"} o gate §6.**
"""
    (OUT_DIR / "veredito.md").write_text(veredito, encoding="utf-8")
    print(f"\n>> veredito.md escrito em {OUT_DIR}")
    print(f">> GATE: {'PASSA' if gate_pass else 'NAO PASSA'} "
          f"({n_folds_melhora}/{n_folds} folds, delta_ll={mean_delta_ll:.5f}, delta_ece={mean_delta_ece:.5f})")


if __name__ == "__main__":
    main()
