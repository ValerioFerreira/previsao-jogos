#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tier2_goalkeeper_saves_test.py
=======================================
Testa se "Goalkeeper Saves" (box-score bruto, coletado no espelho local mas
NUNCA usado como feature -- nao esta em STAT_MAP de build_clubs_dataset.py)
melhora o log-loss do 1x2 quando adicionado como feature de FORCA DEFENSIVA
(media rolling l5/l10 por time, home/away, point-in-time) ao DC-NB de producao.

Diferente da hipotese ja REPROVADA de "goalkeeper momentum" para BTTS/clean-sheet
(DOCUMENTACAO_CENTRAL.md secao sobre goleiro) -- aqui e nivel/forma (media movel),
nao sequencia de momentum, e o alvo e 1x2 (nao BTTS/clean-sheet).

NAO toca build_clubs_dataset.py nem data/built/club_features_enriched.parquet
(outro processo em background esta reconstruindo esse arquivo agora) -- extrai
"Goalkeeper Saves" diretamente do espelho local data/club_raw_cache.sqlite
(somente leitura) e usa scripts/battery_dataset.py::load_clubs_df() como base.

Passos:
  0. Cobertura de "Goalkeeper Saves" no cache (overall + por ano-temporada).
  1. Constroi feature rolling l5/l10 por time (goleiro do proprio time),
     point-in-time (shift(1) antes do rolling), mesclada por fixture_id.
  2. Avalia sob o gate (research_clubs/protocol.py): 5 folds temporais,
     candidato = base_feats_170() + colunas novas vs baseline = base_feats_170().
  3. Controle negativo: embaralha a feature no treino do ultimo fold, confirma
     que o ganho aparente desaparece.

Saida em data/reports/tier2_goalkeeper_saves/:
  cobertura_por_ano.csv, fold_comparison.csv, controle_negativo.json, veredito.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (
    temporal_folds, multiclass_logloss, ece_multiclass, accuracy, compare,
    FoldResult,
)
from scripts.battery_dataset import load_clubs_df, base_feats_170, DC_PARAMS

MIRROR = ROOT / "data" / "club_raw_cache.sqlite"
OUT = ROOT / "data" / "reports" / "tier2_goalkeeper_saves"
FINISHED = {"FT", "AET", "PEN"}
Y_MAP = {"H": 0, "D": 1, "A": 2}
NEW_COLS = ["home_gk_saves_l5", "home_gk_saves_l10",
            "away_gk_saves_l5", "away_gk_saves_l10",
            "diff_gk_saves_l5", "diff_gk_saves_l10"]


def _norm_value(v):
    if v is None:
        return None
    if isinstance(v, str) and v.endswith("%"):
        try:
            return float(v[:-1])
        except ValueError:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─── Passo 0: cobertura ──────────────────────────────────────────────────────
def extract_gk_saves() -> pd.DataFrame:
    """1 linha por fixture finalizada: fixture_id, date, season(ano), league_id,
    home_team_id, away_team_id, gk_home, gk_away (None se ausente/nao numerico)."""
    conn = sqlite3.connect(f"file:{MIRROR}?mode=ro", uri=True, timeout=60)
    n_total = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
    print(f"[gk_saves] {n_total} linhas no espelho local")
    rows = []
    cur = conn.execute("SELECT league_id, season, raw FROM raw")
    i = 0
    for league_id, season, raw in cur:
        i += 1
        if i % 20000 == 0:
            print(f"  {i}/{n_total}...", flush=True)
        d = json.loads(raw)
        fx = d.get("fixture") or {}
        status = ((fx.get("status") or {}).get("short")) or ""
        if status not in FINISHED:
            continue
        teams = d.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        hid, aid = home.get("id"), away.get("id")
        if not hid or not aid:
            continue
        date_str = (fx.get("date") or "")[:10]
        if not date_str:
            continue
        gk = {}
        for entry in d.get("statistics") or []:
            tid = (entry.get("team") or {}).get("id")
            for s in entry.get("statistics") or []:
                if s.get("type") == "Goalkeeper Saves":
                    gk[tid] = _norm_value(s.get("value"))
        rows.append({
            "fixture_id": fx.get("id"), "date": date_str, "league_id": int(league_id),
            "season": int(season), "home_team_id": hid, "away_team_id": aid,
            "gk_home": gk.get(hid), "gk_away": gk.get(aid),
        })
    conn.close()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    print(f"[gk_saves] {len(df)} fixtures finalizadas extraidas")
    return df


def report_coverage(gk: pd.DataFrame):
    OUT.mkdir(parents=True, exist_ok=True)
    both = gk["gk_home"].notna() & gk["gk_away"].notna()
    overall = float(both.mean())
    print(f"[cobertura] overall (ambos os times, valor numerico) = {overall:.1%} "
          f"({both.sum()}/{len(gk)})")

    by_year = gk.groupby("year").apply(
        lambda g: pd.Series({
            "n": len(g),
            "cobertura_ambos": (g["gk_home"].notna() & g["gk_away"].notna()).mean(),
        }), include_groups=False
    ).reset_index()
    by_year.to_csv(OUT / "cobertura_por_ano.csv", index=False)
    print(by_year.to_string(index=False))
    return overall, by_year


# ─── Passo 1: feature rolling point-in-time ─────────────────────────────────
def build_gk_rolling(gk: pd.DataFrame) -> pd.DataFrame:
    """Long (team_id, date, fixture_id, gk_saves_do_proprio_goleiro) -> rolling
    l5/l10 (shift(1) antes do rolling -- nunca usa o valor do proprio jogo),
    mesmo padrao de scripts/build_clubs_dataset.py (bloco 'xG rolling', linha
    ~362-382): grp.sort_values('date'); shift(1); rolling(5,min_periods=2) e
    rolling(10,min_periods=3); depois lookup por jogo/time."""
    long_rows = []
    for _, r in gk.iterrows():
        long_rows.append({"team_id": r["home_team_id"], "date": r["date"],
                           "fixture_id": r["fixture_id"], "gk_saves": r["gk_home"]})
        long_rows.append({"team_id": r["away_team_id"], "date": r["date"],
                           "fixture_id": r["fixture_id"], "gk_saves": r["gk_away"]})
    t = pd.DataFrame(long_rows)
    t = t.sort_values(["team_id", "date", "fixture_id"]).reset_index(drop=True)

    l5_all, l10_all = np.full(len(t), np.nan), np.full(len(t), np.nan)
    for team, grp in t.groupby("team_id", sort=False):
        idx = grp.index
        s = grp["gk_saves"].shift(1)
        d5 = s.rolling(5, min_periods=2).mean()
        d10 = s.rolling(10, min_periods=3).mean()
        l5_all[idx] = d5.to_numpy()
        l10_all[idx] = d10.to_numpy()
    t["gk_saves_l5"] = l5_all
    t["gk_saves_l10"] = l10_all

    lookup = t.set_index(["team_id", "fixture_id"])[["gk_saves_l5", "gk_saves_l10"]]
    # dedupe defensivo: fixture_id deveria ser unico por team_id, mas o raw
    # cache pode ter registros reprocessados/duplicados -- mantem o primeiro
    # (mesmo valor point-in-time de qualquer forma, so a chave se repete).
    lookup = lookup[~lookup.index.duplicated(keep="first")]
    return lookup


def attach_features(df: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for side, col in [("home", "home_team_id"), ("away", "away_team_id")]:
        idx = pd.MultiIndex.from_arrays([df[col], df["fixture_id"]])
        vals = lookup.reindex(idx)
        df[f"{side}_gk_saves_l5"] = vals["gk_saves_l5"].to_numpy()
        df[f"{side}_gk_saves_l10"] = vals["gk_saves_l10"].to_numpy()
    df["diff_gk_saves_l5"] = df["home_gk_saves_l5"] - df["away_gk_saves_l5"]
    df["diff_gk_saves_l10"] = df["home_gk_saves_l10"] - df["away_gk_saves_l10"]
    cov = df[NEW_COLS].notna().all(axis=1).mean()
    print(f"[merge] cobertura das 6 colunas novas no dataset de load_clubs_df(): {cov:.1%}")
    return df


# ─── Passo 2: avaliacao sob o gate ───────────────────────────────────────────
def fit_and_predict(df, tr_idx, te_idx, feats, random_state=42):
    tr, te = df.loc[tr_idx], df.loc[te_idx]
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": random_state})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    probs = m.predict_proba_markets(te[feats])
    return probs["result"][:, ::-1]  # [A,D,H] -> [H,D,A]


def run_folds(df, feats, label, seed=42):
    results = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        t0 = time.time()
        te = df.loc[te_idx]
        p = fit_and_predict(df, tr_idx, te_idx, feats, seed)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        metrics = {
            "logloss": multiclass_logloss(y_idx, p),
            "ece": ece_multiclass(y_idx, p),
            "accuracy": accuracy(y_idx, p),
        }
        results.append(FoldResult(fold=fold, n_test=len(te), metrics=metrics))
        print(f"  [{label}] {fold} n={len(te)} logloss={metrics['logloss']:.4f} "
              f"ece={metrics['ece']:.4f} ({time.time()-t0:.1f}s)", flush=True)
    return results


def negative_control(df, feats_cand, new_cols, seed=42):
    """Embaralha as colunas novas no TREINO do ultimo fold, refit, confirma que
    o ganho aparente desaparece (>= baseline em logloss, dentro de tolerancia)."""
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    te = df.loc[te_idx]
    y_idx = te["result"].map(Y_MAP).to_numpy()

    # baseline (sem as novas colunas) no ultimo fold, p/ referencia
    from scripts.battery_dataset import base_feats_170 as _b170
    p_base = fit_and_predict(df, tr_idx, te_idx, _b170(), seed)
    ll_base = multiclass_logloss(y_idx, p_base)

    # candidato normal (nao embaralhado) no ultimo fold
    p_cand = fit_and_predict(df, tr_idx, te_idx, feats_cand, seed)
    ll_cand = multiclass_logloss(y_idx, p_cand)

    # candidato com as colunas novas EMBARALHADAS no treino
    rng = np.random.RandomState(seed)
    tr = df.loc[tr_idx].copy()
    perm = rng.permutation(len(tr))
    for c in new_cols:
        tr[c] = tr[c].to_numpy()[perm]
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": seed})
    m.fit(tr[feats_cand], tr["home_score"], tr["away_score"])
    probs = m.predict_proba_markets(te[feats_cand])
    p_shuf = probs["result"][:, ::-1]
    ll_shuf = multiclass_logloss(y_idx, p_shuf)

    ok = ll_shuf >= ll_cand - 1e-4  # embaralhado nao deve bater o candidato real
    out = {
        "fold": fold_name,
        "logloss_baseline_170": ll_base,
        "logloss_candidato_real": ll_cand,
        "logloss_candidato_colunas_embaralhadas": ll_shuf,
        "delta_real_vs_baseline": ll_cand - ll_base,
        "delta_embaralhado_vs_baseline": ll_shuf - ll_base,
        "veredito": "OK (ganho aparente desaparece com embaralhamento)" if ok
                    else "SUSPEITO -- embaralhado bate o candidato real, investigar vazamento",
    }
    print(f">> controle negativo: real={ll_cand:.4f} embaralhado={ll_shuf:.4f} "
          f"baseline={ll_base:.4f} -> {out['veredito']}")
    return out


def write_veredito(overall_cov, by_year, fold_cmp, gate_pass, mean_delta, n_improve, control):
    concentrado = by_year.iloc[-3:]["cobertura_ambos"].mean() if len(by_year) >= 3 else float("nan")
    concentrado_geral = by_year["cobertura_ambos"].mean()
    texto = f"""# Tier 2 — Goalkeeper Saves (rolling, forca defensiva) — veredito

## Cobertura
Overall (ambos os times, valor numerico de "Goalkeeper Saves"): **{overall_cov:.1%}**.
Ver `cobertura_por_ano.csv` para o detalhe por ano. Cobertura media dos ultimos 3 anos
do cache: {concentrado:.1%} vs media geral {concentrado_geral:.1%}.
{"**RISCO DE 'MURO DE DADOS'** -- cobertura concentrada nos anos recentes (mesmo padrao que reprovou xG 3x, DOCUMENTACAO_CENTRAL.md secao correspondente)." if not np.isnan(concentrado) and concentrado - concentrado_geral > 0.15 else "Cobertura razoavelmente distribuida ao longo dos anos (nao concentrada so em anos recentes)."}

## Resultado do gate (5 folds temporais, base_feats_170 + 6 colunas novas vs base_feats_170)
{fold_cmp.to_string(index=False)}

Folds que melhoraram: **{n_improve}/5**. Delta medio de log-loss: **{mean_delta:.5f}**.

**Criterio do gate:** PASS somente se >=4/5 folds melhoram E delta medio < -0.001 E ECE nao piora
de forma relevante.

## Controle negativo (embaralhamento no ultimo fold)
{json.dumps(control, indent=2, ensure_ascii=False)}

## Veredito final
**{"PASSA" if gate_pass else "NAO PASSA"} o gate.**
{"" if gate_pass else "Delta nao atinge o limiar exigido (< -0.001) e/ou nao houve consistencia em >=4/5 folds -- REJEITAR, mesmo que o sinal direcional exista."}
"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "veredito.md").write_text(texto, encoding="utf-8")
    print(">> veredito.md escrito")


def main():
    print("=" * 80)
    print("TIER 2 — Goalkeeper Saves (rolling, forca defensiva) no 1x2")
    print("=" * 80)

    print("\n>> Passo 0: cobertura de Goalkeeper Saves no cache local...")
    gk = extract_gk_saves()
    overall_cov, by_year = report_coverage(gk)

    print("\n>> Passo 1: construindo feature rolling point-in-time...")
    lookup = build_gk_rolling(gk)
    df = load_clubs_df()
    df = attach_features(df, lookup)

    feats_base = base_feats_170()
    feats_cand = feats_base + NEW_COLS
    # NaN (times sem historico suficiente na janela) e tratado pelo proprio
    # DixonColesNBRegressor -- seu Pipeline interno usa SimpleImputer(median)
    # ajustado a cada .fit(), portanto a mediana usada e sempre a do TREINO de
    # cada fold (nunca vaza teste->treino). Nao precisa de imputacao manual.

    print("\n>> Passo 2: avaliando sob o gate (5 folds temporais)...")

    base_results, cand_results = [], []
    for fold, tr_idx, te_idx in temporal_folds(df):
        t0 = time.time()
        te = df.loc[te_idx]
        y_idx = te["result"].map(Y_MAP).to_numpy()

        p_base = fit_and_predict(df, tr_idx, te_idx, feats_base)
        p_cand = fit_and_predict(df, tr_idx, te_idx, feats_cand)

        base_results.append(FoldResult(fold=fold, n_test=len(te), metrics={
            "logloss": multiclass_logloss(y_idx, p_base),
            "ece": ece_multiclass(y_idx, p_base),
            "accuracy": accuracy(y_idx, p_base),
        }))
        cand_results.append(FoldResult(fold=fold, n_test=len(te), metrics={
            "logloss": multiclass_logloss(y_idx, p_cand),
            "ece": ece_multiclass(y_idx, p_cand),
            "accuracy": accuracy(y_idx, p_cand),
        }))
        print(f"  [{fold}] n={len(te)} baseline_ll={base_results[-1].metrics['logloss']:.4f} "
              f"candidato_ll={cand_results[-1].metrics['logloss']:.4f} "
              f"({time.time()-t0:.1f}s)", flush=True)

    fold_cmp = compare(base_results, cand_results, metric="logloss")
    OUT.mkdir(parents=True, exist_ok=True)
    fold_cmp.to_csv(OUT / "fold_comparison.csv", index=False)
    print(fold_cmp.to_string(index=False))

    ece_cmp = compare(base_results, cand_results, metric="ece")
    ece_cmp.to_csv(OUT / "fold_comparison_ece.csv", index=False)

    n_improve = int(fold_cmp.iloc[:-1]["melhora"].sum())
    mean_delta = float(fold_cmp.iloc[-1]["delta"])
    mean_delta_ece = float(ece_cmp.iloc[-1]["delta"])
    gate_pass = (n_improve >= 4) and (mean_delta < -0.001) and (mean_delta_ece < 0.01)

    print(f"\n>> folds que melhoraram: {n_improve}/5 | delta medio logloss: {mean_delta:.5f} "
          f"| delta medio ece: {mean_delta_ece:.5f}")
    print(f">> GATE: {'PASSOU' if gate_pass else 'NAO PASSOU'}")

    print("\n>> Passo 3: controle negativo (embaralhamento no ultimo fold)...")
    control = negative_control(df, feats_cand, NEW_COLS)
    with open(OUT / "controle_negativo.json", "w", encoding="utf-8") as f:
        json.dump(control, f, ensure_ascii=False, indent=2)

    write_veredito(overall_cov, by_year, fold_cmp, gate_pass, mean_delta, n_improve, control)
    print("\n>> TIER 2 GOALKEEPER SAVES TEST CONCLUIDO.")


if __name__ == "__main__":
    main()
