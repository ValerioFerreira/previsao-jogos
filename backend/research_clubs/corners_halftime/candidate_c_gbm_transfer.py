#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/corners_halftime/candidate_c_gbm_transfer.py
=============================================================
Candidato C ("GBM de transferência, feature set completo") da pesquisa de
escanteios por tempo (1T/2T) de clube.

Não existe rótulo real de escanteio por tempo (API-Football não separa
"Corner" por tempo nem em eventos nem em estatísticas). Abordagem: aprender
a função "contexto do jogo -> fração no 2º tempo" com GRADIENT BOOSTING sobre
o feature set COMPLETO de produção (`meta["base_feats"]`, 170 colunas — forma
rolling l3/l5/l10, streaks, H2H, árbitro, Elo, GAP ratings de chutes/
escanteios), usando GOLS e CARTÕES por tempo (reais,
`club_halftime_targets.parquet`) como alvo PROXY — dois
`GradientBoostingRegressor` independentes (`goals_2t_share`, `cards_2t_share`),
combinados por média ponderada pelo R² fora-da-amostra (holdout temporal).
Mesma receita/pipeline de `corners_nb_model.py::CornersNB._create_base_regressor`
(`SimpleImputer(mediana)` + `GradientBoostingRegressor`).

Diferença chave vs. um scaling direto do lambda (abordagem mais simples):
a fração prevista é usada para partir a distribuição do TOTAL do modelo de
produção já validado (`corners_cascade_rfixo.joblib`) via MISTURA BINOMIAL:

    home_corners_2t | home_corners_total = n  ~  Binomial(n, p_2t)
    home_corners_1t | home_corners_total = n  ~  Binomial(n, 1 - p_2t)

marginalizando sobre a PMF do total (já calibrada pela cascata de produção —
chutes ortogonalizados -> escanteios, GBR + NB de dispersão por MLE). Isso
preserva EXATAMENTE E[home_1t] + E[home_2t] = E[home_total] (linearidade da
esperança) e dá um formato de PMF mais correto que reescalar uma NB de
dispersão fixa "no chute" pro meio-jogo (a incerteza do total, já validada,
é propagada para os dois tempos em vez de reinventada).

GAP ratings de chutes/escanteios (`gap_shots_*`/`gap_corners_*`) NÃO estão
materializados como coluna em `club_features_enriched.parquet` — só entram em
`predictor.py::build_row()` em tempo de inferência (lookup no
`meta["gap_ratings_state"]`). Aqui são RECOMPUTADOS point-in-time exatamente
como `scripts/build_clubs_production_artifacts.py` faz
(`research_clubs.ratings.compute_gap_ratings` sobre o df inteiro ordenado por
data — o rating da linha i só depende de jogos anteriores, sem vazamento).
Não precisamos reproduzir `disambiguate_collisions` (renomeação só de
exibição): treino e predição usam o MESMO df/mesmos nomes de time, então a
consistência interna das chaves é o que importa, não bater com o
`meta.json` de produção.

Não mexe em `model_artifacts_clubes/*.joblib` (só LÊ os de produção) nem em
`predictor.py`.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import comb
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
import joblib

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_clubs.ratings import compute_gap_ratings  # noqa: E402
from ortho_sinais import apply_ortho_residuals  # noqa: E402
from corner_interactions import add_corner_interactions  # noqa: E402
from corners_nb_model import CornersNB  # noqa: E402,F401 (necessario p/ joblib.load reconhecer a classe)
from shots_nb_model import ShotsNB  # noqa: E402,F401 (idem)

warnings.filterwarnings("ignore", category=FutureWarning)

# ------------------------------------------------------------------ caminhos
FEATURES_PARQUET = ROOT / "data" / "built" / "club_features_enriched.parquet"
HALFTIME_TARGETS_PARQUET = ROOT / "data" / "built" / "club_halftime_targets.parquet"

ART_DIR = ROOT / "model_artifacts_clubes"
META_PATH = ART_DIR / "meta.json"
SHOTS_MODEL_PATH = ART_DIR / "shots_nb.joblib"
ORTHO_WEIGHTS_PATH = ART_DIR / "style_ortho_weights.joblib"
CORNERS_MODEL_PATH = ART_DIR / "corners_cascade_rfixo.joblib"

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
GOALS_MODEL_PATH = ARTIFACT_DIR / "candidate_c_goals_share.joblib"
CARDS_MODEL_PATH = ARTIFACT_DIR / "candidate_c_cards_share.joblib"
META_OUT_PATH = ARTIFACT_DIR / "candidate_c_meta.json"

# --------------------------------------------------------------- universo
TARGET_TOURNAMENTS = [
    "La Liga", "Champions League", "Bundesliga", "Ligue 1",
    "Premier League", "Serie A Italia",
]

OUT_GRID = 16          # PMF de saida do contrato: indices 0..15
TOTAL_GRID = 25        # max_corners do modelo de producao (corners_cascade_rfixo)
FRAC_2T_MIN, FRAC_2T_MAX = 0.05, 0.95
GBM_PARAMS = dict(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42)


# ============================================================ features (base_feats + GAP)
def load_meta() -> dict:
    # meta.json tem caracteres nao-ASCII -> precisa de encoding="utf-8" explicito
    # (Windows tenta cp1252 por padrao e quebra).
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_feature_universe() -> pd.DataFrame:
    """club_features_enriched.parquet ordenado por data, com as 12 colunas GAP
    (chutes/escanteios) recomputadas point-in-time."""
    df = pd.read_parquet(FEATURES_PARQUET)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    gap_shots_df, _ = compute_gap_ratings(
        df, "home_cur_sb_shots", "away_cur_sb_shots", prefix="gap_shots", return_state=True)
    gap_corners_df, _ = compute_gap_ratings(
        df, "home_cur_sb_corners", "away_cur_sb_corners", prefix="gap_corners", return_state=True)
    df = pd.concat([df, gap_shots_df, gap_corners_df], axis=1)
    return df


def get_base_feats(df: pd.DataFrame) -> list[str]:
    meta = load_meta()
    feats = meta["base_feats"]
    missing = [f for f in feats if f not in df.columns]
    if missing:
        raise RuntimeError(f"base_feats ausentes apos recomputar GAP ratings: {missing}")
    return feats


# ============================================================ alvo proxy (gols/cartoes 2T)
def build_proxy_targets(df_features: pd.DataFrame) -> pd.DataFrame:
    """Merge com club_halftime_targets.parquet + as 2 fracoes proxy (gols e
    cartoes que caem no 2T). NaN onde o alvo nao e valido (0x0 pra gols,
    sem eventos de cartao ou 0 cartoes pra cartoes) -- essas linhas sao
    excluidas do FIT (dropna), nao usadas com valor degenerado."""
    tgt = pd.read_parquet(HALFTIME_TARGETS_PARQUET)
    d = df_features.merge(tgt, on="fixture_id", how="inner")

    total_goals = d["home_goals_1t"] + d["home_goals_2t"] + d["away_goals_1t"] + d["away_goals_2t"]
    goals_2t = d["home_goals_2t"] + d["away_goals_2t"]
    d["goals_2t_share"] = np.where(total_goals > 0, goals_2t / total_goals.clip(lower=1), np.nan)

    total_cards = d["home_cards_1t"] + d["home_cards_2t"] + d["away_cards_1t"] + d["away_cards_2t"]
    cards_2t = d["home_cards_2t"] + d["away_cards_2t"]
    valid_cards = (d["has_card_events"] == 1) & (total_cards > 0)
    d["cards_2t_share"] = np.where(valid_cards, cards_2t / total_cards.clip(lower=1), np.nan)

    return d


# ============================================================ modelo do candidato
class ShareGBM:
    """Pipeline SimpleImputer(mediana) + GradientBoostingRegressor -- mesmo
    padrao de corners_nb_model.py::CornersNB._create_base_regressor, so que
    prevendo uma FRACAO (0..1) em vez de uma contagem."""

    def __init__(self, feats: list[str], **gbm_params):
        self.feats = feats
        self.gbm_params = {**GBM_PARAMS, **gbm_params}
        self.pipeline_: Pipeline | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "ShareGBM":
        self.pipeline_ = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("reg", GradientBoostingRegressor(loss="squared_error", **self.gbm_params)),
        ])
        self.pipeline_.fit(X[self.feats], np.asarray(y, dtype=float))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipeline_.predict(X[self.feats])

    @property
    def feature_importances_(self) -> np.ndarray:
        return self.pipeline_.named_steps["reg"].feature_importances_

    def top_features(self, n: int = 10) -> list[tuple[str, float]]:
        imp = self.feature_importances_
        order = np.argsort(imp)[::-1][:n]
        return [(self.feats[i], float(imp[i])) for i in order]

    def save(self, path: Path = None) -> None:
        path = path or GOALS_MODEL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path) -> "ShareGBM":
        return joblib.load(path)


def temporal_holdout_r2(df: pd.DataFrame, feats: list[str], target_col: str,
                         holdout_frac: float = 0.15) -> float:
    """R^2 fora-da-amostra (ultimos holdout_frac% por DATA) -- so pra medir a
    confianca relativa dos 2 proxies (gols vs cartoes), usada como PESO na
    combinacao final. Nao afeta o modelo de producao (esse e treinado na base
    INTEIRA, mesma convencao de build_clubs_production_artifacts.py)."""
    d = df.dropna(subset=[target_col]).sort_values("date")
    n = len(d)
    cut = int(n * (1 - holdout_frac))
    d_train, d_valid = d.iloc[:cut], d.iloc[cut:]
    m = ShareGBM(feats).fit(d_train, d_train[target_col].to_numpy(dtype=float))
    pred = m.predict(d_valid)
    y = d_valid[target_col].to_numpy(dtype=float)
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


# ================================================ cascata de producao (so leitura)
def production_corners_distributions(df: pd.DataFrame) -> dict:
    """Reproduz a cascata de producao (chutes ortogonalizados -> escanteios)
    EXATAMENTE como predictor.py faz na inferencia ao vivo, em lote sobre um
    dataframe historico com as features ja materializadas. So LEITURA dos
    artefatos existentes -- nenhum modelo e retreinado ou alterado aqui.
    Retorna dict com 'home'/'away' (PMF do TOTAL do jogo, grade 0..25) e
    'lambdas'/'mus' (esperanca pontual mandante/visitante)."""
    ortho_weights = joblib.load(ORTHO_WEIGHTS_PATH)
    shots_model = joblib.load(SHOTS_MODEL_PATH)
    corners_model = joblib.load(CORNERS_MODEL_PATH)

    X_resid = apply_ortho_residuals(df, ortho_weights)
    shots_dist = shots_model.predict_distributions(X_resid)
    X_resid = X_resid.copy()
    X_resid["pred_home_shots"] = shots_dist["lambdas"]
    X_resid["pred_away_shots"] = shots_dist["mus"]

    X_corners = add_corner_interactions(X_resid)
    return corners_model.predict_distributions(X_corners)


# ================================================================== mistura binomial
def binom_mixture(total_pmf: np.ndarray, p: np.ndarray, total_grid: int = TOTAL_GRID,
                   out_grid: int = OUT_GRID) -> np.ndarray:
    """PMF marginal de K ~ Binomial(n, p) misturada sobre a PMF de n (grade
    0..total_grid, ja normalizada, uma linha por jogo), truncada numa grade de
    saida 0..out_grid-1 -- a massa de j >= out_grid-1 e absorvida no ultimo bin
    (preserva soma ~1.0 mesmo pra jogos raros com total > out_grid-1).

    Mais correto estatisticamente que so escalar um lambda: propaga a forma
    da incerteza do TOTAL (ja calibrada pela cascata de producao, GBR + NB por
    MLE) para o meio-jogo, em vez de assumir uma dispersao fixa "no chute".
    """
    p = np.clip(np.asarray(p, dtype=float), 1e-3, 1 - 1e-3)
    n_rows = len(p)
    out = np.zeros((n_rows, out_grid))
    last = out_grid - 1
    for n in range(total_grid + 1):
        w = total_pmf[:, n]
        if not np.any(w > 1e-12):
            continue
        j = np.arange(0, n + 1)
        c = comb(n, j)                                          # (n+1,)
        b = (c[None, :] * (p[:, None] ** j[None, :])
             * ((1.0 - p[:, None]) ** (n - j)[None, :]))         # (N, n+1)
        if n <= last:
            out[:, :n + 1] += w[:, None] * b
        else:
            out[:, :last] += w[:, None] * b[:, :last]
            out[:, last] += w * b[:, last:].sum(axis=1)
    out = out / out.sum(axis=1, keepdims=True)
    return out


def pmf_to_string(pmf_row: np.ndarray) -> str:
    return ",".join(f"{v:.6f}" for v in pmf_row)


# ================================================================== pipeline completo
def train_and_predict() -> dict:
    """Roda o candidato de ponta a ponta: treina os 2 GBM de fracao 2T,
    prediz sobre o universo-alvo, roda a cascata de producao e decompoe via
    mistura binomial. Retorna um dict com tudo que o runner precisa (CSV +
    sanity check) -- ver scripts/adhoc_corners_halftime_candidate_c_train.py.
    """
    print("[1/6] Carregando universo de features + recomputando GAP ratings (point-in-time)...")
    df_all = load_feature_universe()
    feats = get_base_feats(df_all)
    print(f"  base_feats: {len(feats)} colunas (inclui gap_shots_*/gap_corners_*)")

    print("\n[2/6] Construindo alvos proxy (goals_2t_share, cards_2t_share)...")
    df_proxy = build_proxy_targets(df_all)
    d_goals = df_proxy.dropna(subset=["goals_2t_share"])
    d_cards = df_proxy.dropna(subset=["cards_2t_share"])
    print(f"  goals_2t_share: N={len(d_goals)} (media={d_goals['goals_2t_share'].mean():.4f})")
    print(f"  cards_2t_share: N={len(d_cards)} (media={d_cards['cards_2t_share'].mean():.4f})")

    print("\n[3/6] Holdout temporal (15%) -- confianca relativa dos 2 proxies...")
    r2_goals = temporal_holdout_r2(d_goals, feats, "goals_2t_share")
    r2_cards = temporal_holdout_r2(d_cards, feats, "cards_2t_share")
    print(f"  R^2 fora-da-amostra: gols={r2_goals:.4f}  cartoes={r2_cards:.4f}")
    w_goals_raw, w_cards_raw = max(r2_goals, 0.01), max(r2_cards, 0.01)
    w_goals = w_goals_raw / (w_goals_raw + w_cards_raw)
    w_cards = w_cards_raw / (w_goals_raw + w_cards_raw)
    print(f"  pesos da combinacao (~R^2, piso 0.01): gols={w_goals:.3f}  cartoes={w_cards:.3f}")

    print("\n[4/6] Treinando os 2 GBM de producao (base inteira, sem holdout)...")
    goals_model = ShareGBM(feats).fit(d_goals, d_goals["goals_2t_share"].to_numpy(dtype=float))
    cards_model = ShareGBM(feats).fit(d_cards, d_cards["cards_2t_share"].to_numpy(dtype=float))
    goals_model.save(GOALS_MODEL_PATH)
    cards_model.save(CARDS_MODEL_PATH)
    print(f"  artefatos salvos: {GOALS_MODEL_PATH.name}, {CARDS_MODEL_PATH.name}")

    top_goals = goals_model.top_features(10)
    top_cards = cards_model.top_features(10)

    print("\n[5/6] Universo de previsao (6 competicoes-alvo) + fracao 2T combinada...")
    df_pred = df_all[df_all["tournament"].isin(TARGET_TOURNAMENTS)].reset_index(drop=True)
    print(f"  fixtures: {len(df_pred)}")
    p_goals = np.clip(goals_model.predict(df_pred), FRAC_2T_MIN, FRAC_2T_MAX)
    p_cards = np.clip(cards_model.predict(df_pred), FRAC_2T_MIN, FRAC_2T_MAX)
    p2t = np.clip(w_goals * p_goals + w_cards * p_cards, FRAC_2T_MIN, FRAC_2T_MAX)
    print(f"  fracao 2T combinada -- media={p2t.mean():.4f} min={p2t.min():.4f} max={p2t.max():.4f}")

    print("\n[6/6] Cascata de producao (chutes -> escanteios, so leitura) + mistura binomial...")
    cd = production_corners_distributions(df_pred)
    lam_home_total = np.asarray(cd["lambdas"], dtype=float)
    lam_away_total = np.asarray(cd["mus"], dtype=float)
    home_total_pmf = np.asarray(cd["home"], dtype=float)   # (N, TOTAL_GRID+1)
    away_total_pmf = np.asarray(cd["away"], dtype=float)

    # lambda exato por linearidade (E[Binomial mixture] = E[n] * p) -- nao
    # depende da grade/truncamento usados na PMF.
    lam_home_2t = lam_home_total * p2t
    lam_home_1t = lam_home_total * (1.0 - p2t)
    lam_away_2t = lam_away_total * p2t
    lam_away_1t = lam_away_total * (1.0 - p2t)

    pmf_home_2t = binom_mixture(home_total_pmf, p2t)
    pmf_home_1t = binom_mixture(home_total_pmf, 1.0 - p2t)
    pmf_away_2t = binom_mixture(away_total_pmf, p2t)
    pmf_away_1t = binom_mixture(away_total_pmf, 1.0 - p2t)

    meta_out = {
        "r2_goals_holdout": r2_goals, "r2_cards_holdout": r2_cards,
        "weight_goals": w_goals, "weight_cards": w_cards,
        "p2t_mean": float(p2t.mean()), "p2t_min": float(p2t.min()), "p2t_max": float(p2t.max()),
        "top_features_goals_2t_share": top_goals,
        "top_features_cards_2t_share": top_cards,
        "n_fixtures": int(len(df_pred)),
        "n_train_goals": int(len(d_goals)), "n_train_cards": int(len(d_cards)),
        "target_tournaments": TARGET_TOURNAMENTS,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with open(META_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2)

    return {
        "fixture_id": df_pred["fixture_id"].to_numpy(),
        "lam_home_1t": lam_home_1t, "lam_home_2t": lam_home_2t,
        "lam_away_1t": lam_away_1t, "lam_away_2t": lam_away_2t,
        "pmf_home_1t": pmf_home_1t, "pmf_home_2t": pmf_home_2t,
        "pmf_away_1t": pmf_away_1t, "pmf_away_2t": pmf_away_2t,
        "lam_home_total_orig": lam_home_total, "lam_away_total_orig": lam_away_total,
        "r2_goals": r2_goals, "r2_cards": r2_cards,
        "w_goals": w_goals, "w_cards": w_cards,
        "top_features_goals": top_goals, "top_features_cards": top_cards,
        "p2t": p2t,
    }
