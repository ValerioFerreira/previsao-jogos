#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_cartoes_amarelos_market.py
==========================================
Formaliza o candidato H4b da investigação PLANO 8 (Fase 1, ver
`data/reports/investigacao_multiagente/cartoes_amarelos.md`) como script de
produção, no mesmo padrão de `train_yellowcards_market.py` (CornersNB sobre
`base_feats`, `.save()` em `model_artifacts_clubes/`), mas com:

1. Duas features extras sobre as 170 de produção (mesma receita da Fase 1):
   - GAP rating incremental de ataque/defesa (Wheatcroft 2020/21) do PRÓPRIO
     alvo (cartão amarelo), via `research_clubs.ratings.compute_gap_ratings`
     — a MESMA função já usada em produção para chutes/escanteios
     (`gap_shots_*`/`gap_corners_*`), só aplicada em
     `home_cur_sb_yellow`/`away_cur_sb_yellow`. Bateu a média móvel simples
     (`sb_yellow_l5`) testada em H1 em todas as métricas (delta_ll, tail_ece).
   - Target-encoding shrinkage de identidade de competição (heterogeneidade
     de liga, R²≈9% só com a média por torneio).
2. Correção de dispersão (NOVO nesta rodada, autorizado pelo dono após a
   Fase 1): em TODOS os 8 variantes testados na Fase 1, o único critério do
   gate que nunca passou foi `coverage80` (fica 0,86-0,88, teto é 0,85) —
   PIORANDO conforme os outros 3 critérios melhoravam. Diagnóstico do
   Auditor de Métricas (Fase 1 §2): não é artefato de discretização (alvo
   tem baixa zero-inflação, var/média modesta) — é dispersão real demais
   pro tanto que a média (mu) já ficou precisa. Correção: escala o parâmetro
   `r` (por lado, mantendo a MESMA razão H/A do MLE original) por um fator
   único ajustado numa fatia de CALIBRAÇÃO (80% fit / 20% calib,
   cronológico, DENTRO do treino de cada fold — sem vazamento), minimizando
   |coverage80_calib - 0,80|. Reaproveita `nb_pmf_grid` do
   `scripts.gate_count_market` (mesma função usada pelos baselines B0/B1/B2
   do gate oficial) para reconstruir a PMF com `r` escalado sem re-treinar
   os regressores de média (só o r muda; a etapa cara — GBR de mu — roda
   uma vez só por fold/sub-split).

Uso:
  python -m scripts.train_cartoes_amarelos_market --scope clube --mode gate
      -- só roda os 4 experimentos oficiais (H4b sem escala / H4b + escala /
         controle: escala isolada no candidato original / controle: H4b com
         colunas extras embaralhadas + escala) e imprime/salva os números.
  python -m scripts.train_cartoes_amarelos_market --scope clube --mode train
      -- treina o artefato de PRODUÇÃO final (fit em 100% dos dados, escala
         = mediana das escalas ajustadas por fold no modo gate) e salva em
         model_artifacts_clubes/cartoes_amarelos_nb.joblib + atualiza
         meta.json (gap_ratings_state["yellow"], tournament_yellow_enc,
         full_feats) — NÃO edita predictor.py (fora do escopo autorizado
         nesta rodada; ver relatório final para o que falta pra servir de
         verdade em produção).
  python -m scripts.train_cartoes_amarelos_market --scope clube --mode all
      -- roda os dois (default).

Só suporta --scope clube: a pipeline de GAP rating usa
`scripts.battery_dataset.load_clubs_df` (desambiguação de colisão de nome +
GAP de chutes/escanteios já embutidos), específica de clube; não existe
equivalente pronto pra seleção.
"""
from __future__ import annotations

import argparse
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

from corners_nb_model import CornersNB  # noqa: E402
from research_clubs import protocol  # noqa: E402
from research_clubs.ratings import compute_gap_ratings  # noqa: E402
from scripts.gate_count_market import (  # noqa: E402
    _load_market_data, baseline_b0, baseline_b1, baseline_b2, nb_pmf_grid,
    MIN_N, DELTA_THRESHOLD, FOLDS_REQUIRED_FRAC, TAIL_ECE_MAX, COVERAGE80_RANGE,
)

MARKET = "cartoes_amarelos"
SCOPE = "clube"
ART_DIR = ROOT / "model_artifacts_clubes"
OUT_DIR = ROOT / "data" / "reports" / "gate_mercados"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GAP_PREFIX = "gap_yellow"
GAP_COLS = [f"{GAP_PREFIX}_home_att", f"{GAP_PREFIX}_home_def",
            f"{GAP_PREFIX}_away_att", f"{GAP_PREFIX}_away_def",
            f"{GAP_PREFIX}_exp_home", f"{GAP_PREFIX}_exp_away"]
TOURN_COL = "tournament_enc_yellow"
SCALE_GRID = np.geomspace(0.5, 4.0, 36)  # multiplicador de r (>1 = PMF mais estreita)


# ─── features extras (mesma receita da Fase 1) ────────────────────────────────
def shrinkage_tournament_encoding(train: pd.DataFrame, test: pd.DataFrame,
                                   target_col: str, k: float = 50):
    """Target-encoding bayesiano de `tournament`, computado SÓ do treino (sem
    vazamento). Retorna (enc_train, enc_test, tabela_dict, media_global) — a
    tabela/média global são o que vira o lookup de produção quando `train`
    é o dataset inteiro."""
    global_mean = float(train[target_col].mean())
    grp = train.groupby("tournament")[target_col].agg(["mean", "count"])
    shrunk = (grp["count"] * grp["mean"] + k * global_mean) / (grp["count"] + k)
    enc_train = train["tournament"].map(shrunk).fillna(global_mean).values.astype(float)
    enc_test = test["tournament"].map(shrunk).fillna(global_mean).values.astype(float)
    return enc_train, enc_test, shrunk.to_dict(), global_mean


def add_extra_features(train: pd.DataFrame, test: pd.DataFrame, th: str, ta: str,
                        base_feats: list[str], use_gap: bool, use_tournament: bool,
                        permute: bool = False, seed: int = 42):
    """Retorna (train, test, feats_ext) com as colunas extras já preenchidas
    (mediana do TREINO em NaN) e adicionadas a `feats_ext`. `permute=True`
    embaralha as colunas extras DEPOIS de calculadas (controle negativo)."""
    rng = np.random.RandomState(seed)
    train, test = train.copy(), test.copy()
    feats_ext = list(base_feats)
    extra_cols = []

    if use_gap:
        for c in GAP_COLS:
            med = train[c].median()
            train[c] = train[c].fillna(med)
            test[c] = test[c].fillna(med)
        extra_cols += GAP_COLS

    if use_tournament:
        y_tr_total = train[th].astype(float) + train[ta].astype(float)
        train_tmp = train.assign(_y=y_tr_total)
        enc_tr, enc_te, _, _ = shrinkage_tournament_encoding(train_tmp, test, "_y", k=50)
        train[TOURN_COL] = enc_tr
        test[TOURN_COL] = enc_te
        extra_cols += [TOURN_COL]

    if permute:
        for c in extra_cols:
            train[c] = rng.permutation(train[c].values)
            test[c] = rng.permutation(test[c].values)

    feats_ext += extra_cols
    return train, test, feats_ext


# ─── PMF com r escalado (sem re-treinar os regressores de média) ─────────────
def pmf_total_with_scale(m: CornersNB, X: pd.DataFrame, max_k: int, scale: float) -> np.ndarray:
    Xf = X[m.feats]
    lambdas = np.maximum(m.model_home_.predict(Xf), 0.1)
    mus = np.maximum(m.model_away_.predict(Xf), 0.1)
    r_h = max(m.r_H_ * scale, 1e-3)
    r_a = max(m.r_A_ * scale, 1e-3)
    prob_h = nb_pmf_grid(lambdas, r_h, max_k)
    prob_a = nb_pmf_grid(mus, r_a, max_k)
    n = len(prob_h)
    total = np.zeros((n, 2 * max_k + 1))
    for i in range(n):
        total[i] = np.convolve(prob_h[i], prob_a[i])
    return total


def tune_scale(fit_part: pd.DataFrame, cal_part: pd.DataFrame, feats_ext: list[str],
               th: str, ta: str, max_k: int):
    """Ajusta o multiplicador de r numa fatia de CALIBRAÇÃO (nunca no teste
    final). Retorna (scale, cov80_calib_no_scale, cov80_calib_no_best_scale,
    modelo_fit_part) -- o modelo é reaproveitado pra não treinar de novo."""
    if len(cal_part) < 200:
        return 1.0, None, None, None
    yh_fit = fit_part[th].astype(int).clip(0, max_k).values
    ya_fit = fit_part[ta].astype(int).clip(0, max_k).values
    Xfit = fit_part[feats_ext].fillna(fit_part[feats_ext].median(numeric_only=True))
    Xcal = cal_part[feats_ext].fillna(fit_part[feats_ext].median(numeric_only=True))
    m_fit = CornersNB(feats=feats_ext, max_corners=max_k)
    m_fit.fit(Xfit, yh_fit, ya_fit)

    y_cal_total = (cal_part[th].astype(int).clip(0, max_k).values +
                   cal_part[ta].astype(int).clip(0, max_k).values)
    cov_no_scale = protocol.coverage80(y_cal_total, pmf_total_with_scale(m_fit, Xcal, max_k, 1.0))

    best_scale, best_score, best_cov = 1.0, abs(cov_no_scale - 0.80), cov_no_scale
    for s in SCALE_GRID:
        pmf_cal = pmf_total_with_scale(m_fit, Xcal, max_k, s)
        cov = protocol.coverage80(y_cal_total, pmf_cal)
        score = abs(cov - 0.80)
        if score < best_score:
            best_score, best_scale, best_cov = score, s, cov
    return best_scale, cov_no_scale, best_cov, m_fit


# ─── avaliação oficial (mesmos folds/limiares do gate §6-C) ──────────────────
def evaluate_variant(name: str, d: pd.DataFrame, base_feats: list[str], th: str, ta: str,
                      max_k: int, y_total: np.ndarray, use_gap: bool, use_tournament: bool,
                      tune_dispersion: bool, permute_extra: bool = False, seed: int = 42):
    rows = []
    for fold, tr_idx, te_idx in protocol.temporal_folds(d):
        train, test = d.loc[tr_idx].copy(), d.loc[te_idx].copy()
        y_te = y_total[te_idx]

        train, test, feats_ext = add_extra_features(
            train, test, th, ta, base_feats, use_gap, use_tournament,
            permute=permute_extra, seed=seed)

        yh_tr = train[th].astype(int).clip(0, max_k).values
        ya_tr = train[ta].astype(int).clip(0, max_k).values
        Xtr = train[feats_ext].fillna(train[feats_ext].median(numeric_only=True))
        Xte = test[feats_ext].fillna(train[feats_ext].median(numeric_only=True))

        m = CornersNB(feats=feats_ext, max_corners=max_k)
        m.fit(Xtr, yh_tr, ya_tr)

        scale = 1.0
        cov_calib_raw = cov_calib_scaled = None
        if tune_dispersion:
            cut = int(len(train) * 0.8)
            fit_part, cal_part = train.iloc[:cut], train.iloc[cut:]
            scale, cov_calib_raw, cov_calib_scaled, _ = tune_scale(
                fit_part, cal_part, feats_ext, th, ta, max_k)

        pmf_cand = pmf_total_with_scale(m, Xte, max_k, scale)
        pmf_b0 = baseline_b0(y_total[tr_idx], len(test), max_k)
        pmf_b1 = baseline_b1(train, test, th, ta, max_k)
        pmf_b2 = baseline_b2(train, test, th, ta, max_k)
        cands_base = {"B0": pmf_b0, "B2": pmf_b2}
        if pmf_b1 is not None:
            cands_base["B1"] = pmf_b1

        ll_base = {nm: protocol.pmf_logloss(y_te, pmf) for nm, pmf in cands_base.items()}
        melhor_baseline = min(ll_base, key=ll_base.get)
        pmf_melhor = cands_base[melhor_baseline]

        ll_cand = protocol.pmf_logloss(y_te, pmf_cand)
        ll_melhor = ll_base[melhor_baseline]
        line_central = float(np.median(y_te))
        tece_cand = protocol.tail_ece(y_te, pmf_cand, [line_central])[f"over_{line_central}"]
        tece_base = protocol.tail_ece(y_te, pmf_melhor, [line_central])[f"over_{line_central}"]
        cov = protocol.coverage80(y_te, pmf_cand)

        # diagnostico "quao perto do teto por mu": cobertura por quartil de mu previsto
        mu_total = m.model_home_.predict(Xte[m.feats]) + m.model_away_.predict(Xte[m.feats])
        try:
            qs = pd.qcut(mu_total, 4, labels=False, duplicates="drop")
        except ValueError:
            qs = np.zeros(len(mu_total), dtype=int)
        cov_por_mu = {}
        for qi in sorted(set(qs)):
            mask = qs == qi
            if mask.sum() > 0:
                cov_por_mu[f"q{int(qi)}_n{int(mask.sum())}"] = round(
                    protocol.coverage80(y_te[mask], pmf_cand[mask]), 4)

        rows.append({
            "fold": fold, "n_test": len(test), "scale": scale,
            "cov_calib_raw": cov_calib_raw, "cov_calib_scaled": cov_calib_scaled,
            "ll_candidato": ll_cand, "ll_melhor_baseline": ll_melhor,
            "melhor_baseline": melhor_baseline, "delta_ll": ll_cand - ll_melhor,
            "melhora": ll_cand < ll_melhor,
            "tail_ece_candidato": tece_cand, "tail_ece_baseline": tece_base,
            "coverage80": cov, "coverage80_por_mu": json.dumps(cov_por_mu),
        })

    res = pd.DataFrame(rows)
    n_folds = len(res)
    n_melhora = int(res["melhora"].sum())
    delta_medio = float(res["delta_ll"].mean())
    tece_media = float(res["tail_ece_candidato"].mean())
    tece_base_media = float(res["tail_ece_baseline"].mean())
    cov_media = float(res["coverage80"].mean())

    aprova = (
        n_melhora / n_folds >= FOLDS_REQUIRED_FRAC
        and delta_medio < DELTA_THRESHOLD
        and tece_media <= TAIL_ECE_MAX
        and tece_media <= tece_base_media + 1e-9
        and COVERAGE80_RANGE[0] <= cov_media <= COVERAGE80_RANGE[1]
    )
    veredito = {
        "experimento": name, "market": MARKET, "scope": SCOPE,
        "status": "APROVADO" if aprova else "REPROVADO",
        "n_folds": n_folds, "folds_que_melhoram": f"{n_melhora}/{n_folds}",
        "delta_ll_medio": round(delta_medio, 5),
        "tail_ece_candidato": round(tece_media, 4), "tail_ece_baseline": round(tece_base_media, 4),
        "coverage80_medio": round(cov_media, 4),
        "coverage80_folga_do_teto": round(COVERAGE80_RANGE[1] - cov_media, 4),
        "scales_por_fold": res["scale"].round(3).tolist(),
        "criterio": {
            "folds_ok": n_melhora / n_folds >= FOLDS_REQUIRED_FRAC,
            "delta_ok": delta_medio < DELTA_THRESHOLD,
            "tail_ece_ok": tece_media <= TAIL_ECE_MAX and tece_media <= tece_base_media + 1e-9,
            "coverage_ok": COVERAGE80_RANGE[0] <= cov_media <= COVERAGE80_RANGE[1],
        },
    }
    out_csv = OUT_DIR / f"prod_{name}.csv"
    res.to_csv(out_csv, index=False)
    veredito["csv"] = str(out_csv)
    out_json = OUT_DIR / f"prod_{name}.json"
    out_json.write_text(json.dumps(veredito, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(veredito, indent=2, ensure_ascii=False), flush=True)
    return veredito


def run_gate_suite(d, base_feats, th, ta, max_k, y_total):
    results = {}
    print("\n>>> A) H4b sem escala (reproduz Fase 1, via script oficial)", flush=True)
    results["A_h4b_no_scale"] = evaluate_variant(
        "A_h4b_no_scale", d, base_feats, th, ta, max_k, y_total,
        use_gap=True, use_tournament=True, tune_dispersion=False)

    print("\n>>> B) H4b + correcao de dispersao (candidato final proposto)", flush=True)
    results["B_h4b_scaled"] = evaluate_variant(
        "B_h4b_scaled", d, base_feats, th, ta, max_k, y_total,
        use_gap=True, use_tournament=True, tune_dispersion=True)

    print("\n>>> C) controle negativo: escala isolada no candidato ORIGINAL (sem gap/tournament)", flush=True)
    results["C_ctrl_scale_only_original"] = evaluate_variant(
        "C_ctrl_scale_only_original", d, base_feats, th, ta, max_k, y_total,
        use_gap=False, use_tournament=False, tune_dispersion=True)

    print("\n>>> D) controle negativo: H4b com colunas extras embaralhadas + escala", flush=True)
    results["D_ctrl_h4b_permuted_scaled"] = evaluate_variant(
        "D_ctrl_h4b_permuted_scaled", d, base_feats, th, ta, max_k, y_total,
        use_gap=True, use_tournament=True, tune_dispersion=True, permute_extra=True)

    summary_path = OUT_DIR / "RESUMO_producao_cartoes_amarelos.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n\n=== RESUMO OFICIAL ===", flush=True)
    for name, v in results.items():
        print(f"{name}: status={v['status']} folds={v['folds_que_melhoram']} "
              f"delta_ll={v['delta_ll_medio']} tail_ece={v['tail_ece_candidato']} "
              f"vs base={v['tail_ece_baseline']} cov={v['coverage80_medio']} "
              f"folga_teto={v['coverage80_folga_do_teto']} scales={v['scales_por_fold']}", flush=True)
    print("Resumo salvo em:", summary_path, flush=True)
    return results


def train_production_artifact(d, base_feats, th, ta, max_k, gate_results):
    """Fit final em 100% dos dados (mesma convencao de train_yellowcards_market.py
    -- in-sample, sem holdout, como os demais mercados de contagem ja em
    producao). Escala de producao = mediana das escalas por fold do
    experimento B (H4b + dispersao) -- hiperparametro escolhido por CV,
    aplicado no refit final, pratica padrao."""
    d = d.copy()
    gap_df, gap_state = compute_gap_ratings(d, th, ta, prefix=GAP_PREFIX, return_state=True)
    d = pd.concat([d.reset_index(drop=True), gap_df.reset_index(drop=True)], axis=1)
    for c in GAP_COLS:
        d[c] = d[c].fillna(d[c].median())

    y_all_total = d[th].astype(float) + d[ta].astype(float)
    enc_all, _, tourn_table, tourn_global_mean = shrinkage_tournament_encoding(
        d.assign(_y=y_all_total), d, "_y", k=50)
    d[TOURN_COL] = enc_all

    feats_ext = base_feats + GAP_COLS + [TOURN_COL]
    yh = d[th].astype(int).clip(0, max_k).values
    ya = d[ta].astype(int).clip(0, max_k).values
    X = d[feats_ext].fillna(d[feats_ext].median(numeric_only=True))
    print(f"[producao] N={len(d)} | media real mand {yh.mean():.3f} vis {ya.mean():.3f} "
          f"total {(yh+ya).mean():.3f} | feats={len(feats_ext)} ({len(GAP_COLS)+1} extras)", flush=True)

    m = CornersNB(feats=feats_ext, max_corners=max_k)
    m.fit(X, yh, ya)

    scales_b = [s for s in gate_results["B_h4b_scaled"]["scales_por_fold"] if s]
    prod_scale = float(np.median(scales_b)) if scales_b else 1.0
    m.r_H_ = float(m.r_H_ * prod_scale)
    m.r_A_ = float(m.r_A_ * prod_scale)
    print(f"[producao] escala de producao (mediana dos {len(scales_b)} folds) = {prod_scale:.3f} "
          f"-> r_H={m.r_H_:.3f} r_A={m.r_A_:.3f}", flush=True)

    dist = m.predict_distributions(X)
    ks = np.arange(m.max_corners + 1)
    kt = np.arange(2 * m.max_corners + 1)
    print(f"  E[PMF] mand {(dist['home']@ks).mean():.3f} vis {(dist['away']@ks).mean():.3f} "
          f"total {(dist['total']@kt).mean():.3f} (sanidade in-sample)", flush=True)

    out = ART_DIR / "cartoes_amarelos_nb.joblib"
    m.save(str(out))
    print(f"  salvo: {out}", flush=True)

    # meta.json: soh ADICIONA chaves novas (gap_ratings_state["yellow"],
    # tournament_yellow_enc, full_feats) -- nao mexe nas existentes. NAO edita
    # predictor.py (fora do escopo desta rodada); ver relatorio final.
    meta_path = ART_DIR / "meta.json"
    meta = json.load(open(meta_path, encoding="utf-8"))
    meta.setdefault("gap_ratings_state", {})
    meta["gap_ratings_state"]["yellow"] = {
        "Ha": gap_state["Ha"], "Hd": gap_state["Hd"],
        "Aa": gap_state["Aa"], "Ad": gap_state["Ad"],
        "running_mean": gap_state["running_mean"],
    }
    meta["tournament_yellow_enc"] = {"table": tourn_table, "global_mean": tourn_global_mean, "k": 50}
    meta["cartoes_amarelos_prod_scale"] = prod_scale
    existing_full = set(meta.get("full_feats", []))
    new_cols = [c for c in (GAP_COLS + [TOURN_COL]) if c not in existing_full]
    meta.setdefault("full_feats", [])
    meta["full_feats"] += new_cols
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  meta.json atualizado ({len(new_cols)} colunas novas em full_feats, "
          f"gap_ratings_state['yellow'] e tournament_yellow_enc gravados): {meta_path}", flush=True)
    print("  ATENCAO: predictor.py NAO foi editado -- build_row() ainda nao povoa essas "
          "colunas em tempo real (ficam NaN -> imputadas pela mediana de treino via "
          "SimpleImputer, sem crash, mas sem o ganho real ate a extensao de build_row()).",
          flush=True)
    return out, meta_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["clube"], default="clube")
    ap.add_argument("--mode", choices=["gate", "train", "all"], default="all")
    a = ap.parse_args()

    loaded = _load_market_data(MARKET, SCOPE)
    d, base_feats, th, ta, max_k, y_total, n = loaded
    print(f"n={n}, base_feats={len(base_feats)}, max_k={max_k}", flush=True)

    # GAP yellow global (causal, 1x sobre o dataset inteiro ordenado por data
    # -- mesmo padrao ja usado em producao pra gap_shots/gap_corners).
    gap_df, _ = compute_gap_ratings(d, th, ta, prefix=GAP_PREFIX, return_state=True)
    d = pd.concat([d.reset_index(drop=True), gap_df.reset_index(drop=True)], axis=1)

    results = None
    if a.mode in ("gate", "all"):
        results = run_gate_suite(d, base_feats, th, ta, max_k, y_total)

    if a.mode in ("train", "all"):
        if results is None:
            # modo "train" isolado: precisa da escala de producao -- reusa o
            # summary ja salvo pelo modo "gate" se existir.
            summary_path = OUT_DIR / "RESUMO_producao_cartoes_amarelos.json"
            if not summary_path.exists():
                raise SystemExit("rode --mode gate primeiro (precisa da escala tunada por fold)")
            results = json.loads(summary_path.read_text(encoding="utf-8"))
        train_production_artifact(d, base_feats, th, ta, max_k, results)


if __name__ == "__main__":
    main()
