#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/gate_count_market.py
=============================
Gate §6-C (docs/PLANO_EXPANSAO_MERCADOS.md §3) -- protocolo de validacao para
mercados de CONTAGEM (escanteios/cartoes/impedimentos/faltas/gols-por-tempo/...)
onde nao ha modelo incumbente na producao para comparar (diferente do gate §6
original, que compara contra o DC-NB/NB/GP ja em producao).

Reaproveita INTEGRALMENTE `research_clubs/protocol.py` (temporal_folds,
pmf_logloss, tail_ece, coverage80) -- nao reimplementa metrica nova. O
CANDIDATO e a MESMA arquitetura de producao (CornersNB sobre base_feats),
refeita sob CV temporal (nunca o artefato ja salvo em disco, que foi ajustado
in-sample sem holdout -- e exatamente o que este gate audita).

Tres baselines obrigatorios (o gate compara contra o MELHOR deles):
  B0 -- NB de intercepto (media global do treino, sem feature nenhuma)
  B1 -- NB sobre a media rolante do time (*_l5), so roda se a coluna existir
  B2 -- NB por media de competicao (tournament), fallback pra media global
        quando a competicao nao aparece no treino

Criterio de aprovacao (docs/PLANO_EXPANSAO_MERCADOS.md §3):
  1. pmf_logloss melhor que o melhor baseline em >=4/5 folds
  2. delta pmf_logloss medio < -0.001
  3. tail_ece da linha central <= 0.05 e nao pior que o baseline
  4. coverage80 perto do TETO ALCANCAVEL por auto-consistencia (nao mais um
     range fixo [0.75, 0.85] -- ver EMENDA 2026-07-31 abaixo)
  5. >=5000 jogos com alvo nao-nulo
  6. sem inversao de sinal por segmento (competicao, faixa de |elo_diff|)

EMENDA 2026-07-31 (DOCUMENTACAO_CENTRAL.md §29.5, decisao do dono apos a
investigacao multiagente do PLANO 8): o criterio 4 original (coverage80 fixo
em [0.75, 0.85]) provou-se estruturalmente inalcancavel para distribuicoes
discretas de baixa contagem (mu_total baixo) -- confirmado por simulacao de
auto-consistencia em 7 mercados (cartoes 1T/2T/amarelos/vermelhos, gols
1T/2T, impedimentos): mesmo um modelo PERFEITAMENTE especificado (dados
gerados pela propria PMF ajustada) nao entra em [0.75, 0.85] quando mu_total
e baixo, porque o suporte discreto pula em blocos grandes de probabilidade.
`achievable_coverage80()` reproduz essa simulacao dentro do proprio gate:
gera dados sinteticos a partir da PMF do candidato e mede o coverage80 de um
modelo "que sabe a verdade" contra sua propria verdade. O criterio 4 agora e
"coverage80 observado fica a ate COVERAGE_TOLERANCE do teto alcancavel",
nao mais um range absoluto -- isso deixa o gate justo tanto pra mercados de
alta contagem (faltas, mu~25: teto alcancavel ~0.80, equivalente ao range
antigo) quanto de baixa contagem (impedimentos, mu~3.7: teto ~0.90, onde o
range antigo reprovava qualquer modelo por construcao).

Reprovar e resultado valido -- sempre registrar em DOCUMENTACAO_CENTRAL.md,
nunca esconder.

Uso:
  python -m scripts.gate_count_market --market cartoes_amarelos --scope clube
  python -m scripts.gate_count_market --market impedimentos --scope clube --candidate-max-k 10
  python -m scripts.gate_count_market --all --scope clube
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from corners_nb_model import CornersNB  # noqa: E402
from research_clubs import protocol  # noqa: E402
from scripts.battery_dataset import load_clubs_df  # noqa: E402

OUT_DIR = ROOT / "data" / "reports" / "gate_mercados"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = {
    "selecao": {
        "features": ROOT / "international_features_enriched_apifootball.csv",
        "art": ROOT / "model_artifacts",
        "halftime": ROOT / "data" / "built" / "halftime_targets.parquet",
    },
    "clube": {
        "features": ROOT / "data" / "built" / "club_features_enriched.parquet",
        "art": ROOT / "model_artifacts_clubes",
        "halftime": ROOT / "data" / "built" / "club_halftime_targets.parquet",
    },
}

# th/ta = colunas de alvo (mandante/visitante); max_k = teto da grade da PMF
# (cauda absorvida no ultimo bin, nao truncada -- ver nb_pmf_grid/CornersNB).
MARKETS = {
    "cartoes_amarelos": dict(source="features", th="home_cur_sb_yellow", ta="away_cur_sb_yellow", max_k=15),
    "cartoes_vermelhos": dict(source="features", th="home_cur_sb_red", ta="away_cur_sb_red", max_k=4),
    "impedimentos": dict(source="features", th="home_cur_sb_offsides", ta="away_cur_sb_offsides", max_k=10),
    "faltas": dict(source="features", th="home_cur_sb_fouls", ta="away_cur_sb_fouls", max_k=22),
    "gols_1t": dict(source="halftime", th="home_goals_1t", ta="away_goals_1t", max_k=12, need_cards=False),
    "gols_2t": dict(source="halftime", th="home_goals_2t", ta="away_goals_2t", max_k=12, need_cards=False),
    "cartoes_1t": dict(source="halftime", th="home_cards_1t", ta="away_cards_1t", max_k=15, need_cards=True),
    "cartoes_2t": dict(source="halftime", th="home_cards_2t", ta="away_cards_2t", max_k=15, need_cards=True),
}

MIN_N = 5000
DELTA_THRESHOLD = -0.001
FOLDS_REQUIRED_FRAC = 0.8  # >=4/5
TAIL_ECE_MAX = 0.05
COVERAGE80_RANGE = (0.75, 0.85)  # mantido so p/ referencia historica, nao usado desde a emenda
COVERAGE_TOLERANCE = 0.05  # distancia maxima aceitavel ao teto alcancavel (emenda 2026-07-31)
COVERAGE_SIM_SEED = 20260731
COVERAGE_SIM_REPS = 5


# ─── baselines (NB por metodo dos momentos, PMF por linha via mu variavel) ────
def _moment_r(mu_train: float, var_train: float) -> float:
    if var_train <= mu_train:
        return 1e6  # sem sobredispersao detectavel -> quase-Poisson
    return float(mu_train ** 2 / (var_train - mu_train))


def nb_pmf_grid(mu: np.ndarray, r: float, max_k: int) -> np.ndarray:
    """PMF NB por observacao (mu varia, r fixo -- moment-matched no treino).
    Cauda (> max_k) absorvida no ultimo bin, igual ao CornersNB de producao."""
    r = max(r, 1e-3)
    mu = np.clip(mu, 1e-6, None)
    p = r / (r + mu)
    ks = np.arange(max_k + 1)
    pmf = np.array([nbinom.pmf(ks, r, pi) for pi in p])
    pmf = np.clip(pmf, 0.0, None)
    tail = np.clip(1.0 - pmf.sum(axis=1), 0.0, None)
    pmf[:, -1] += tail
    pmf = np.clip(pmf, 1e-12, None)
    pmf /= pmf.sum(axis=1, keepdims=True)
    return pmf


def baseline_b0(y_train: np.ndarray, n_test: int, max_k: int) -> np.ndarray:
    # grade do TOTAL tem que casar com a do candidato: CornersNB convolve
    # home+away (cada 0..max_k) -> total tem 2*max_k+1 bins (0..2*max_k), nao
    # max_k+1. Passar max_k puro aqui fazia o baseline absorver toda massa
    # acima de max_k num unico bin -- com max_k << media do total (ex.:
    # faltas, max_k=22 vs total~25), isso inflava artificialmente a
    # probabilidade do baseline e derrubava o candidato por construcao, nao
    # por ajuste (bug real, achado 2026-07-31 comparando os resultados).
    mu, var = y_train.mean(), y_train.var()
    r = _moment_r(mu, var)
    return nb_pmf_grid(np.full(n_test, mu), r, 2 * max_k)


def _roll_cols(th: str, ta: str) -> tuple[str, str] | None:
    """home_cur_sb_yellow -> home_sb_yellow_l5 / away_sb_yellow_l5, se existir."""
    m = re.match(r"home_cur_sb_(\w+)", th)
    if not m:
        return None
    base = m.group(1)
    return f"home_sb_{base}_l5", f"away_sb_{base}_l5"


def baseline_b1(train: pd.DataFrame, test: pd.DataFrame, th: str, ta: str,
                 max_k: int) -> np.ndarray | None:
    cols = _roll_cols(th, ta)
    if cols is None or cols[0] not in train.columns or cols[1] not in train.columns:
        return None
    ytr = train[th].astype(float).values + train[ta].astype(float).values
    mu_tr_pred = train[cols[0]].fillna(train[cols[0]].median()).values + \
                 train[cols[1]].fillna(train[cols[1]].median()).values
    resid_var = float(np.var(ytr - np.clip(mu_tr_pred, 1e-6, None)))
    r = _moment_r(max(mu_tr_pred.mean(), 1e-6), max(resid_var + mu_tr_pred.mean(), mu_tr_pred.mean() + 1e-6))
    mu_te = test[cols[0]].fillna(train[cols[0]].median()).values + \
            test[cols[1]].fillna(train[cols[1]].median()).values
    return nb_pmf_grid(mu_te, r, 2 * max_k)  # grade do total, ver nota em baseline_b0


def baseline_b2(train: pd.DataFrame, test: pd.DataFrame, th: str, ta: str,
                 max_k: int) -> np.ndarray:
    ytr_total = train[th].astype(float).values + train[ta].astype(float).values
    global_mu, global_var = ytr_total.mean(), ytr_total.var()
    r = _moment_r(global_mu, global_var)
    tr = train.assign(_y=ytr_total)
    comp_mean = tr.groupby("tournament")["_y"].mean().to_dict()
    mu_te = test["tournament"].map(comp_mean).fillna(global_mu).values.astype(float)
    return nb_pmf_grid(mu_te, r, 2 * max_k)  # grade do total, ver nota em baseline_b0


def achievable_coverage80(pmf: np.ndarray, seed: int = COVERAGE_SIM_SEED,
                           n_rep: int = COVERAGE_SIM_REPS) -> float:
    """Teto de coverage80 alcancavel por um modelo PERFEITAMENTE especificado:
    gera dados sinteticos a partir da PROPRIA pmf do candidato (auto-
    consistencia -- o candidato "sabe a verdade" porque a verdade e ele
    mesmo) e mede o coverage80 resultante. Pra distribuicoes discretas de
    baixa contagem isso fica bem acima de 0.85 so pelo suporte discreto, nao
    por erro de ajuste -- ver EMENDA 2026-07-31 no topo do arquivo.
    Vetorizado via CDF (evita loop por linha com scipy)."""
    rng = np.random.default_rng(seed)
    cdf = pmf.cumsum(axis=1)
    k = pmf.shape[1]
    covs = []
    for _ in range(n_rep):
        u = rng.random(pmf.shape[0])
        y_sim = np.clip((cdf < u[:, None]).sum(axis=1), 0, k - 1)
        covs.append(protocol.coverage80(y_sim, pmf))
    return float(np.mean(covs))


# ─── candidato: MESMA arquitetura de producao, refeita sob CV temporal ───────
def candidate_pmf(train: pd.DataFrame, test: pd.DataFrame, base_feats: list[str],
                   th: str, ta: str, max_k: int) -> np.ndarray:
    yh = train[th].astype(int).clip(0, max_k).values
    ya = train[ta].astype(int).clip(0, max_k).values
    Xtr = train[base_feats].fillna(train[base_feats].median(numeric_only=True))
    Xte = test[base_feats].fillna(train[base_feats].median(numeric_only=True))
    m = CornersNB(feats=base_feats, max_corners=max_k)
    m.fit(Xtr, yh, ya)
    return m.predict_distributions(Xte)["total"]


def bernoulli_ll(y: np.ndarray, p: np.ndarray, eps=1e-12) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def candidate_calibrated_over_prob(train: pd.DataFrame, test: pd.DataFrame,
                                    base_feats: list[str], th: str, ta: str,
                                    max_k: int, line: float) -> tuple[np.ndarray, np.ndarray]:
    """PMF do candidato costuma sair larga demais (coverage80 >> 0.85 nos
    mercados sem calibrador isotonico -- ver ou_calibrators.joblib, so cobre
    escanteios/finalizacoes_gol/cartoes-total). Testa se ISSO, e nao o ajuste
    em si, explica a reprovacao: recorta o TREINO em fit (80%) + calibracao
    (20%, cronologico -- sem vazamento), fita o isotonico na fatia de
    calibracao e aplica no teste. Retorna (over_prob_bruto, over_prob_calibrado).
    """
    from sklearn.isotonic import IsotonicRegression
    cut = int(len(train) * 0.8)
    fit_part, cal_part = train.iloc[:cut], train.iloc[cut:]
    if len(cal_part) < 200:  # fatia de calibracao pequena demais -> pula
        return None, None

    pmf_fit_on_cal = candidate_pmf(fit_part, cal_part, base_feats, th, ta, max_k)
    pmf_test = candidate_pmf(fit_part, test, base_feats, th, ta, max_k)

    y_cal = cal_part[th].astype(int).clip(0, max_k).values + cal_part[ta].astype(int).clip(0, max_k).values
    over_cal = protocol.ou_probs_from_pmf(pmf_fit_on_cal, line)
    iso = IsotonicRegression(out_of_bounds="clip").fit(over_cal, (y_cal > line).astype(float))

    over_test_raw = protocol.ou_probs_from_pmf(pmf_test, line)
    over_test_cal = iso.predict(over_test_raw)
    return over_test_raw, over_test_cal


def _load_market_data(market: str, scope: str):
    """Prepara (d, base_feats, th, ta, max_k, y_total) ou None se N insuficiente
    -- compartilhado entre run_gate e run_calibration_check pra nao duplicar a
    logica de carga/GAP/merge de meia-partida."""
    cfg = CONFIG[scope]
    spec = MARKETS[market]
    art_dir = cfg["art"]
    meta = json.load(open(art_dir / "meta.json", encoding="utf-8"))
    base_feats = meta["base_feats"]

    if scope == "clube":
        # load_clubs_df ja desambigua colisao de nome de time e computa GAP
        # ratings (compute_gap_ratings e keyed por nome de time -- sem
        # desambiguar, dois times diferentes com o mesmo nome em ligas
        # distintas contaminariam o rating um do outro).
        df = load_clubs_df(min_matches=0)
    else:
        feats_path = cfg["features"]
        df = pd.read_csv(feats_path, low_memory=False) if feats_path.suffix == ".csv" else pd.read_parquet(feats_path)

    if spec["source"] == "halftime":
        tgt_path = cfg["halftime"]
        if not tgt_path.exists():
            return {"market": market, "scope": scope, "status": "SEM_DADO",
                    "motivo": f"{tgt_path} nao existe"}
        tgt = pd.read_parquet(tgt_path)
        df = df.merge(tgt, on="fixture_id", how="inner")
        if spec.get("need_cards") and "has_card_events" in df.columns:
            df = df[df["has_card_events"] == 1]

    th, ta, max_k = spec["th"], spec["ta"], spec["max_k"]
    d = df.dropna(subset=[th, ta, "date"]).copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)

    # GAP ratings (chutes/escanteios, §17 do doc-mestre) ja vem prontos de
    # load_clubs_df() pra scope=clube (com desambiguacao de colisao de nome de
    # time -- compute_gap_ratings e keyed por nome). Para selecao (sem GAP no
    # base_feats hoje) a coluna simplesmente nao existe e o filtro abaixo a
    # descarta sem quebrar.
    base_feats = [f for f in base_feats if f in d.columns]
    n = len(d)
    if n < MIN_N:
        return None
    y_total = d[th].astype(int).clip(0, max_k).values + d[ta].astype(int).clip(0, max_k).values
    return d, base_feats, th, ta, max_k, y_total, n


def run_gate(market: str, scope: str) -> dict:
    loaded = _load_market_data(market, scope)
    if loaded is None:
        return {"market": market, "scope": scope, "status": "N_INSUFICIENTE", "min_exigido": MIN_N}
    if isinstance(loaded, dict):
        return loaded  # SEM_DADO (halftime target ausente)
    d, base_feats, th, ta, max_k, y_total, n = loaded

    rows = []
    for fold, tr_idx, te_idx in protocol.temporal_folds(d):
        train, test = d.loc[tr_idx], d.loc[te_idx]
        y_te = y_total[te_idx]

        pmf_cand = candidate_pmf(train, test, base_feats, th, ta, max_k)
        pmf_b0 = baseline_b0(y_total[tr_idx], len(test), max_k)
        pmf_b1 = baseline_b1(train, test, th, ta, max_k)
        pmf_b2 = baseline_b2(train, test, th, ta, max_k)

        candidatos_baseline = {"B0": pmf_b0, "B2": pmf_b2}
        if pmf_b1 is not None:
            candidatos_baseline["B1"] = pmf_b1

        ll_base = {name: protocol.pmf_logloss(y_te, pmf) for name, pmf in candidatos_baseline.items()}
        melhor_baseline = min(ll_base, key=ll_base.get)
        pmf_melhor = candidatos_baseline[melhor_baseline]

        ll_cand = protocol.pmf_logloss(y_te, pmf_cand)
        ll_melhor = ll_base[melhor_baseline]
        line_central = float(np.median(y_te))
        tece_cand = protocol.tail_ece(y_te, pmf_cand, [line_central])[f"over_{line_central}"]
        tece_base = protocol.tail_ece(y_te, pmf_melhor, [line_central])[f"over_{line_central}"]
        cov = protocol.coverage80(y_te, pmf_cand)
        cov_teto = achievable_coverage80(pmf_cand)  # emenda 2026-07-31, ver topo do arquivo

        rows.append({
            "fold": fold, "n_test": len(test),
            "ll_candidato": ll_cand, "ll_melhor_baseline": ll_melhor,
            "melhor_baseline": melhor_baseline, "delta_ll": ll_cand - ll_melhor,
            "melhora": ll_cand < ll_melhor,
            "tail_ece_candidato": tece_cand, "tail_ece_baseline": tece_base,
            "coverage80": cov, "coverage80_teto_alcancavel": cov_teto,
            **{f"ll_{k}": v for k, v in ll_base.items()},
        })

    res = pd.DataFrame(rows)
    n_folds = len(res)
    n_melhora = int(res["melhora"].sum())
    delta_medio = float(res["delta_ll"].mean())
    tece_media = float(res["tail_ece_candidato"].mean())
    tece_base_media = float(res["tail_ece_baseline"].mean())
    cov_media = float(res["coverage80"].mean())
    cov_teto_medio = float(res["coverage80_teto_alcancavel"].mean())
    cov_dist_teto = abs(cov_media - cov_teto_medio)

    aprova = (
        n_melhora / n_folds >= FOLDS_REQUIRED_FRAC
        and delta_medio < DELTA_THRESHOLD
        and tece_media <= TAIL_ECE_MAX
        and tece_media <= tece_base_media + 1e-9
        and cov_dist_teto <= COVERAGE_TOLERANCE
    )

    out_csv = OUT_DIR / f"{market}_{scope}.csv"
    res.to_csv(out_csv, index=False)

    veredito = {
        "market": market, "scope": scope, "status": "APROVADO" if aprova else "REPROVADO",
        "n": int(n), "n_folds": n_folds, "folds_que_melhoram": f"{n_melhora}/{n_folds}",
        "delta_ll_medio": round(delta_medio, 5),
        "tail_ece_candidato": round(tece_media, 4), "tail_ece_baseline": round(tece_base_media, 4),
        "coverage80_medio": round(cov_media, 4),
        "coverage80_teto_alcancavel": round(cov_teto_medio, 4),
        "coverage80_distancia_teto": round(cov_dist_teto, 4),
        "criterio": {
            "folds_ok": n_melhora / n_folds >= FOLDS_REQUIRED_FRAC,
            "delta_ok": delta_medio < DELTA_THRESHOLD,
            "tail_ece_ok": tece_media <= TAIL_ECE_MAX and tece_media <= tece_base_media + 1e-9,
            "coverage_ok": cov_dist_teto <= COVERAGE_TOLERANCE,
        },
        "gate_versao": "emenda_2026-07-31_coverage80_por_mu",
        "csv": str(out_csv),
    }
    out_json = OUT_DIR / f"{market}_{scope}.json"
    out_json.write_text(json.dumps(veredito, indent=2, ensure_ascii=False), encoding="utf-8")
    return veredito


def run_calibration_check(market: str, scope: str) -> dict:
    """Segue um REPROVADO no gate cru: sera que falta so calibracao isotonica
    (a que ja existe pra escanteios/finalizacoes_gol/cartoes-total, ver
    ou_calibrators.joblib) e nao o ajuste em si? Fita isotonico dentro do
    TREINO de cada fold (80% fit / 20% calibracao, cronologico) e compara
    Bernoulli-LL do candidato CALIBRADO contra o candidato cru e contra o
    melhor baseline, na linha central O/U de cada fold."""
    loaded = _load_market_data(market, scope)
    if loaded is None or isinstance(loaded, dict):
        return {"market": market, "scope": scope, "status": "SEM_DADO_SUFICIENTE"}
    d, base_feats, th, ta, max_k, y_total, n = loaded

    rows = []
    for fold, tr_idx, te_idx in protocol.temporal_folds(d):
        train, test = d.loc[tr_idx], d.loc[te_idx]
        y_te = y_total[te_idx]
        line = float(np.median(y_total[tr_idx]))  # decidida do TREINO, nunca do teste

        over_raw, over_cal = candidate_calibrated_over_prob(train, test, base_feats, th, ta, max_k, line)
        if over_raw is None:
            continue
        y_over = (y_te > line).astype(float)

        pmf_b0 = baseline_b0(y_total[tr_idx], len(test), max_k)
        pmf_b1 = baseline_b1(train, test, th, ta, max_k)
        pmf_b2 = baseline_b2(train, test, th, ta, max_k)
        cands_base = {"B0": pmf_b0, "B2": pmf_b2}
        if pmf_b1 is not None:
            cands_base["B1"] = pmf_b1
        ll_base = {nm: bernoulli_ll(y_over, protocol.ou_probs_from_pmf(pmf, line)) for nm, pmf in cands_base.items()}
        melhor = min(ll_base, key=ll_base.get)

        rows.append({
            "fold": fold, "n_test": len(test), "line": line,
            "ll_cru": bernoulli_ll(y_over, over_raw),
            "ll_calibrado": bernoulli_ll(y_over, over_cal),
            "ll_melhor_baseline": ll_base[melhor], "melhor_baseline": melhor,
        })

    if not rows:
        return {"market": market, "scope": scope, "status": "SEM_FOLD_VALIDO"}

    res = pd.DataFrame(rows)
    res["calibrado_bate_cru"] = res["ll_calibrado"] < res["ll_cru"]
    res["calibrado_bate_baseline"] = res["ll_calibrado"] < res["ll_melhor_baseline"]
    out_csv = OUT_DIR / f"{market}_{scope}_calibracao.csv"
    res.to_csv(out_csv, index=False)

    veredito = {
        "market": market, "scope": scope, "check": "calibracao_isotonica",
        "n_folds": len(res),
        "ll_medio_cru": round(float(res["ll_cru"].mean()), 5),
        "ll_medio_calibrado": round(float(res["ll_calibrado"].mean()), 5),
        "ll_medio_baseline": round(float(res["ll_melhor_baseline"].mean()), 5),
        "folds_calibrado_bate_cru": f"{int(res['calibrado_bate_cru'].sum())}/{len(res)}",
        "folds_calibrado_bate_baseline": f"{int(res['calibrado_bate_baseline'].sum())}/{len(res)}",
        "conclusao": (
            "calibracao resolve -- reprovacao no gate cru era so falta de calibrador isotonico"
            if int(res["calibrado_bate_baseline"].sum()) >= max(4, int(0.8 * len(res)))
            else "calibracao ajuda mas nao resolve sozinha -- o candidato cru realmente perde em ajuste, nao so em calibracao"
        ),
        "csv": str(out_csv),
    }
    out_json = OUT_DIR / f"{market}_{scope}_calibracao.json"
    out_json.write_text(json.dumps(veredito, indent=2, ensure_ascii=False), encoding="utf-8")
    return veredito


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=list(MARKETS.keys()))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    ap.add_argument("--calibration-check", action="store_true",
                     help="segue um REPROVADO: testa se calibracao isotonica sozinha resolve")
    a = ap.parse_args()
    if not a.market and not a.all:
        ap.error("--market <nome> ou --all")

    markets = list(MARKETS.keys()) if a.all else [a.market]
    runner = run_calibration_check if a.calibration_check else run_gate
    label = "CHECK DE CALIBRACAO" if a.calibration_check else "GATE §6-C"
    print("=" * 100)
    print(f" {label} -- mercados de contagem -- escopo={a.scope}")
    print("=" * 100)
    resultados = []
    for mkt in markets:
        print(f"\n>>> {mkt}", flush=True)
        try:
            v = runner(mkt, a.scope)
        except Exception as e:
            v = {"market": mkt, "scope": a.scope, "status": "ERRO", "erro": str(e)}
        resultados.append(v)
        print(json.dumps(v, indent=2, ensure_ascii=False), flush=True)

    suffix = "_calibracao" if a.calibration_check else ""
    resumo = OUT_DIR / f"RESUMO_{a.scope}{suffix}.json"
    resumo.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResumo: {resumo}")


if __name__ == "__main__":
    main()
