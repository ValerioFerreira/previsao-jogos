#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/corners_halftime/candidate_b_hazard_sim.py
===========================================================
Candidato B — escanteios por tempo (1T/2T) via "hazard/simulação de ritmo
pré-jogo".

Não existe alvo real de escanteio por tempo no nosso dataset (API-Football
não expõe evento "Corner" nem estatística por tempo — ver docstring do
runner em scripts/adhoc_corners_halftime_candidate_b_train.py). Em vez de
ajustar uma regressão contra um proxy de gols/cartões (candidatos A/C), esta
abordagem modela a FRAÇÃO de escanteios que ocorre no 2º tempo como uma
função de forma (shape function) de poucos parâmetros, fundamentada em
achados publicados de event-history/hazard de escanteios, e aplica essa
fração ao TOTAL já validado (produção: corners_cascade_rfixo.joblib).

Literatura usada para desenhar a curva
---------------------------------------
- Peng, Hu & Swartz (2025), "On the time of corner kicks in soccer: an
  analysis of event history data", Computational Statistics 40(4) —
  modelo de tempo-até-evento (hazard) sobre escanteios da Chinese Super
  League 2019. Analisa a associação do hazard de escanteio com: 1º vs 2º
  tempo, mando de campo, diferença de placar, probabilidade de vitória
  pré-jogo (odds), e diferença de cartões vermelhos. Não expõe os
  coeficientes publicamente (paywall), mas a lista de covariáveis confirma
  que "quão parelho está o jogo" (placar/odds) e mando de campo são os
  eixos centrais do timing de escanteio — é exatamente o que usamos aqui,
  substituindo placar IN-GAME (que não temos pré-jogo) por probabilidade de
  vitória pré-jogo (`elo_home_winprob`) como proxy.
- Achado geral replicado em várias fontes de stats públicas (footystats,
  thestatsdontlie, apwin): "geralmente mais escanteios ocorrem no 2º tempo,
  conforme o time que está atrás pressiona e o jogo se abre" — mas o split
  exato varia por liga (ex.: Bundesliga tende a ter 1º tempo mais
  concentrado). Isso motiva um baseline > 0.50 mas modesto (não copiamos
  cegamente o split de gols/cartões, que é mais extremo — ver calibração
  abaixo).
- "Score effects" / "chasing behaviour" (Lago-Peñas & Dellal 2010; Jones et
  al. 2004): o time que está (ou tende a estar) atrás no placar aumenta
  intensidade ofensiva/territorial no 2º tempo — usamos a probabilidade de
  vitória pré-jogo como proxy de "quem tende a estar atrás" (o underdog).
- Vantagem de mando mais forte tarde no jogo (torcida/pressão ambiental,
  achado replicado em vários estudos de home advantage, ex. Nevill &
  Holder 1999): damos um pequeno bônus ao mandante em jogos parelhos com
  mando real (não neutro), e uma pequena penalidade simétrica ao visitante.

Calibração leve (sanity check, não regressão completa)
--------------------------------------------------------
Usamos `club_halftime_targets.parquet` (gols/cartões por tempo, split real)
só para CONFIRMAR direção/ordem de grandeza, não para fitar os parâmetros
livres da curva:
  - fração média de gols no 2T (jogos com >=1 gol): ~0.565
  - fração média de cartões no 2T (jogos com >=1 cartão): ~0.650
  - ambos > 0.50, confirmando o padrão geral "mais ação no 2T".
  - a correlação ponto-a-ponto entre essas frações por partida e as
    proxies de competitividade pré-jogo (elo_home_winprob, |elo_diff|) é
    ~0 (ruído de poucos eventos por jogo — 2 a 3 gols/cartões no total não
    dá sinal estatístico ao nível de partida individual, mesmo que o efeito
    exista agregado; é exatamente por isso que a literatura usa modelagem
    de hazard/event-history em vez de regressão de fração terminal). Por
    isso mantemos os coeficientes MODESTOS (poucos pontos percentuais),
    ancorados na literatura, e não tentamos "encaixar" a curva no ruído.
  - escanteios são eventos ~5x mais frequentes que gols por jogo, então
    escolhemos uma base (`BASE_2T = 0.525`) mais conservadora que a de
    gols/cartões, coerente com o consenso público (split perto de
    52-55%, não 65%).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corners_nb_model import CornersNB  # noqa: E402
from shots_nb_model import ShotsNB  # noqa: E402
from ortho_sinais import apply_ortho_residuals  # noqa: E402
from corner_interactions import add_corner_interactions  # noqa: E402
from research_clubs.ratings import compute_gap_ratings  # noqa: E402

ART_DIR = ROOT / "model_artifacts_clubes"

TOURNAMENTS = [
    "La Liga", "Champions League", "Bundesliga", "Ligue 1",
    "Premier League", "Serie A Italia",
]

MAX_K = 15  # grade da PMF de saída: 0..15 escanteios por mercado/lado

# ─── parâmetros livres da curva de forma (poucos, documentados) ─────────────
BASE_2T = 0.525        # baseline levemente > 0.50 (achado geral "mais 2T")
SCALE_ELO_DIFF = 200.0  # normalização do gap de força pré-jogo (elo_diff std~130)
SCALE_CORNER_DIFF = 1.25  # normalização do gap de GAP-rating de escanteio (std observado)
K_CLOSE = 0.05          # jogo parelho -> mais disputa sustentada até o fim (2T)
K_BLOWOUT = 0.03        # goleada esperada -> jogo "decidido cedo", menos 2T
K_STAKES = 0.02         # peso do torneio (competições grandes -> mais intensidade)
K_FINAL = 0.015         # final/mata-mata decisivo -> intensidade extra até o fim
K_PRESS = 0.07          # "chasing behaviour": underdog empurra mais no seu próprio 2T
K_CROWD = 0.02          # mando real em jogo parelho -> torcida empurra o mandante tarde
K_CROWD_AWAY = 0.01     # e um pouco o inverso pro visitante (hostilidade ambiental)
FRAC_MIN, FRAC_MAX = 0.42, 0.66  # limites de sanidade da fração


# ─── 1. GAP ratings (Wheatcroft) ponto-no-tempo p/ escanteios ───────────────
def add_gap_corner_ratings(df_full: pd.DataFrame) -> pd.DataFrame:
    """Computa gap_corners_* ponto-no-tempo sobre o dataset INTEIRO (todas as
    competições, para não perder continuidade de rating de um time que joga
    em múltiplas ligas), ordenado por data — mesma função usada na produção
    (research_clubs/ratings.py::compute_gap_ratings). Usadas aqui só como
    proxy de "quão parelha é a disputa territorial de escanteios" (item 3 do
    prompt), não como feature do modelo de total (esse já é validado e
    ignora GAP ratings, ver corners_cascade_rfixo.joblib/meta.json).
    """
    df_sorted = (df_full.sort_values("date")
                 .reset_index(drop=False).rename(columns={"index": "_orig_idx"})
                 .set_index("_orig_idx"))
    g = compute_gap_ratings(df_sorted, "home_cur_sb_corners", "away_cur_sb_corners",
                             prefix="gap_corners")
    g = g.reindex(df_full.index)
    out = df_full.copy()
    for c in g.columns:
        out[c] = g[c].to_numpy()
    return out


# ─── 2. função de forma: fração de escanteios no 2º tempo ───────────────────
def hazard_frac_2t(df: pd.DataFrame) -> pd.DataFrame:
    """Retorna DataFrame com `frac_2t_home`/`frac_2t_away` (uma fração por
    lado, permitindo assimetria mandante/visitante via "chasing behaviour").
    Todas as entradas são proxies PRÉ-jogo (nunca placar/cartão real do
    próprio jogo)."""
    p = df["elo_home_winprob"].to_numpy(dtype=float)
    elo_diff = df["elo_diff"].to_numpy(dtype=float)
    gap_diff = (df["gap_corners_exp_home"] - df["gap_corners_exp_away"]).to_numpy(dtype=float)
    tw = df["tournament_weight"].to_numpy(dtype=float)
    is_final = df["is_major_final"].to_numpy(dtype=float)
    home_crowd = df["real_home_advantage"].to_numpy(dtype=float)  # 1 - neutral

    # competitividade: combina "força geral" (Elo) e "força específica de
    # escanteio" (GAP rating) — jogos parelhos nos dois eixos tendem a manter
    # disputa territorial sustentada até o fim (achado central de Swartz et
    # al.: diferença de placar/probabilidade de vitória move o hazard).
    mismatch_elo = np.tanh(np.abs(elo_diff) / SCALE_ELO_DIFF)
    mismatch_corner = np.tanh(np.abs(gap_diff) / SCALE_CORNER_DIFF)
    mismatch = 0.5 * mismatch_elo + 0.5 * mismatch_corner
    closeness = 1.0 - mismatch  # 1 = parelho, 0 = goleada esperada

    # "chasing behaviour": lado com MENOR prob. de vitória pré-jogo tende a
    # estar atrás com mais frequência -> empurra mais no seu próprio 2T.
    underdog_home = np.clip(0.5 - p, 0.0, 0.5) * 2.0  # 0..1
    underdog_away = np.clip(p - 0.5, 0.0, 0.5) * 2.0  # 0..1

    stakes = np.clip((tw - 0.85) / (1.0 - 0.85), 0.0, 1.0)

    common = (BASE_2T
              + K_CLOSE * (closeness - 0.5)
              - K_BLOWOUT * mismatch_elo
              + K_STAKES * stakes
              + K_FINAL * is_final)

    frac_home = (common
                 + K_PRESS * underdog_home
                 + K_CROWD * home_crowd * closeness)
    frac_away = (common
                 + K_PRESS * underdog_away
                 - K_CROWD_AWAY * home_crowd * closeness)

    frac_home = np.clip(frac_home, FRAC_MIN, FRAC_MAX)
    frac_away = np.clip(frac_away, FRAC_MIN, FRAC_MAX)

    return pd.DataFrame({"frac_2t_home": frac_home, "frac_2t_away": frac_away}, index=df.index)


# ─── 3. cascata do modelo de produção (TOTAL de escanteios, já validado) ───
def load_cascade_artifacts(art_dir: Path = ART_DIR):
    corners_model = CornersNB.load(str(art_dir / "corners_cascade_rfixo.joblib"))
    shots_model = ShotsNB.load(str(art_dir / "shots_nb.joblib"))
    import joblib
    ortho_weights = joblib.load(str(art_dir / "style_ortho_weights.joblib"))
    return corners_model, shots_model, ortho_weights


def predict_total_corners(df: pd.DataFrame, corners_model, shots_model, ortho_weights):
    """Reproduz EXATAMENTE a cascata de inferência de predictor.py (Predictor.predict):
    1) ortogonalização de estilo, 2) cascata de chutes injetada como feature,
    3) interações de mando, 4) NB de escanteios. Retorna lambdas (mandante)
    e mus (visitante) — a esperança de escanteios TOTAL (90min) já validada
    sob o gate §6 (não é tocada/retreinada aqui)."""
    X_resid = apply_ortho_residuals(df, ortho_weights)
    cs = shots_model.predict_distributions(X_resid)
    X_resid = X_resid.copy()
    X_resid["pred_home_shots"] = cs["lambdas"]
    X_resid["pred_away_shots"] = cs["mus"]
    X_corners = add_corner_interactions(X_resid)
    cd = corners_model.predict_distributions(X_corners)
    return cd["lambdas"], cd["mus"]


# ─── 4. PMF Binomial Negativa na grade 0..MAX_K, dispersão fixa proporcional ─
def nb_pmf_grid(lam: np.ndarray, r: float, max_k: int = MAX_K) -> np.ndarray:
    """PMF NB renormalizada em 0..max_k (mesma receita de
    CornersNB._marginal_pmf, mas grade menor pois é meio-jogo)."""
    k = np.arange(max_k + 1)
    lam = np.maximum(lam, 0.05)
    p = r / (r + lam)
    pmf = nbinom.pmf(k[None, :], n=r, p=p[:, None])
    pmf = pmf / pmf.sum(axis=1, keepdims=True)
    return pmf


def build_predictions(df_universe: pd.DataFrame, df_full_for_ratings: pd.DataFrame) -> pd.DataFrame:
    """Orquestra os passos 1-6 do prompt e retorna o CSV em formato LONGO
    (fixture_id, market, lambda, pmf)."""
    print(f"[candidate_b] universo de previsão: {len(df_universe)} fixtures")

    print("[candidate_b] computando GAP ratings de escanteio ponto-no-tempo "
          f"sobre o dataset inteiro ({len(df_full_for_ratings)} jogos, todas as competições)...")
    df_full_gap = add_gap_corner_ratings(df_full_for_ratings)
    gap_cols = ["gap_corners_home_att", "gap_corners_home_def",
                "gap_corners_away_att", "gap_corners_away_def",
                "gap_corners_exp_home", "gap_corners_exp_away"]
    df_universe = df_universe.copy()
    df_universe[gap_cols] = df_full_gap.loc[df_universe.index, gap_cols]

    print("[candidate_b] carregando artefatos da cascata de produção "
          "(shots_nb + style_ortho_weights + corners_cascade_rfixo)...")
    corners_model, shots_model, ortho_weights = load_cascade_artifacts()

    print("[candidate_b] prevendo TOTAL de escanteios (mandante/visitante, 90min)...")
    lambdas_total, mus_total = predict_total_corners(df_universe, corners_model, shots_model, ortho_weights)

    print("[candidate_b] aplicando função de forma (fração de 2T por lado)...")
    frac = hazard_frac_2t(df_universe)

    lam_home_2t = lambdas_total * frac["frac_2t_home"].to_numpy()
    lam_home_1t = lambdas_total - lam_home_2t
    lam_away_2t = mus_total * frac["frac_2t_away"].to_numpy()
    lam_away_1t = mus_total - lam_away_2t

    # dispersão: mantém a MESMA razão r/lambda do modelo total validado
    # (r_H_/r_A_ do corners_cascade_rfixo, ver docstring do módulo) — como
    # lambda de meio-jogo é ~metade do total, usamos r/2 pro mesmo índice
    # de dispersão relativo (variância/média preservada).
    r_h_half = corners_model.r_H_ / 2.0
    r_a_half = corners_model.r_A_ / 2.0

    pmf_home_1t = nb_pmf_grid(lam_home_1t, r_h_half)
    pmf_home_2t = nb_pmf_grid(lam_home_2t, r_h_half)
    pmf_away_1t = nb_pmf_grid(lam_away_1t, r_a_half)
    pmf_away_2t = nb_pmf_grid(lam_away_2t, r_a_half)

    def _pmf_str(arr2d):
        return [",".join(f"{v:.6f}" for v in row) for row in arr2d]

    fixture_ids = df_universe["fixture_id"].to_numpy()
    parts = []
    for market, lam_arr, pmf_arr in [
        ("home_1t", lam_home_1t, pmf_home_1t),
        ("away_1t", lam_away_1t, pmf_away_1t),
        ("home_2t", lam_home_2t, pmf_home_2t),
        ("away_2t", lam_away_2t, pmf_away_2t),
    ]:
        parts.append(pd.DataFrame({
            "fixture_id": fixture_ids,
            "market": market,
            "lambda": lam_arr,
            "pmf": _pmf_str(pmf_arr),
        }))
    out = pd.concat(parts, ignore_index=True)

    out.attrs["lambda_total_home"] = lambdas_total
    out.attrs["lambda_total_away"] = mus_total
    out.attrs["frac_2t_home"] = frac["frac_2t_home"].to_numpy()
    out.attrs["frac_2t_away"] = frac["frac_2t_away"].to_numpy()
    return out
