#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp7_multivariate_counts.py — EXPERIMENTO 2: Modelagem conjunta multivariada
====================================================================================
Hipótese: finalizações, escanteios e cartões são impulsionados por um mesmo fator latente
("intensidade territorial"), e o CASCADE (pred_shots -> escanteios -> cartões) só captura
parte dessa dependência. Testamos se estruturar a dependência MULTIVARIADA COMPLETA melhora
o log-loss CONJUNTO das contagens vs os marginais NB/GP INDEPENDENTES de produção.

Método (cópula gaussiana sobre os marginais de produção):
  1. Para cada jogo, pega a PMF do TOTAL de cada contagem dos modelos deployados.
  2. mid-PIT: u_i = (F_i(k-1)+F_i(k))/2 no valor observado; z_i = Φ⁻¹(u_i).
  3. TREINO: estima a matriz de correlação Σ dos z (a estrutura da cópula), point-in-time.
  4. NLL conjunto: independente = −Σ log pmf_i ; cópula = idem − log c_Σ(z)
     com c_Σ(z) = |Σ|^{-1/2} exp(−½ zᵀ(Σ⁻¹−I)z).
  5. Compara NLL_indep vs NLL_copula, CV temporal expanding. Se a cópula reduz o NLL conjunto
     de forma consistente, a dependência multivariada importa (há valor além do cascade).
Métrica: NLL conjunto (log-loss multivariado). Gate §6 temporal.
Saída: docs/EXP7_CONTAGEM_MULTIVARIADA.md + console.
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib
from scipy.stats import norm
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ortho_sinais import apply_ortho_residuals
from corner_interactions import add_corner_interactions
ART = ROOT / "model_artifacts"; CSV = ROOT / "international_features_enriched_apifootball.csv"
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib")
OOF = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")

MARKETS = [  # (nome, artefato, coluna_home, coluna_away)
    ("finalizacoes", "shots_nb.joblib", "home_cur_sb_shots", "away_cur_sb_shots"),
    ("escanteios", "corners_cascade_rfixo.joblib", "home_cur_sb_corners", "away_cur_sb_corners"),
    ("cartoes", "cards_gp.joblib", "home_cur_sb_cards", "away_cur_sb_cards"),
]


def enrich(te):
    te = apply_ortho_residuals(te, ORTHO_W)
    te = te.merge(OOF, on="match_id", how="left")
    if "pred_home_shots_oof" in te.columns:
        te["pred_home_shots"] = te["pred_home_shots_oof"]; te["pred_away_shots"] = te["pred_away_shots_oof"]
    return add_corner_interactions(te)


def total_pmf(model, X):
    return model.predict_distributions(X)["total"]  # (N, K)


def mid_pit(pmf, obs):
    """u = (F(k-1)+F(k))/2 no valor observado (por linha)."""
    cdf = np.cumsum(pmf, axis=1)
    k = np.clip(obs.astype(int), 0, pmf.shape[1] - 1)
    idx = np.arange(len(obs))
    Fk = cdf[idx, k]
    Fk1 = np.where(k > 0, cdf[idx, np.maximum(k - 1, 0)], 0.0)
    u = 0.5 * (Fk + Fk1)
    p = pmf[idx, k]
    return np.clip(u, 1e-4, 1 - 1e-4), np.clip(p, 1e-9, None)


def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy()
    for _, _, ch, ca in MARKETS:
        adv = adv.dropna(subset=[ch, ca])
    adv = enrich(adv).sort_values("date").reset_index(drop=True)
    print(f"jogos com as 3 contagens: {len(adv)}", flush=True)

    # PMFs e observados por mercado
    Z = np.zeros((len(adv), len(MARKETS))); LOGP = np.zeros((len(adv), len(MARKETS)))
    for j, (name, artf, ch, ca) in enumerate(MARKETS):
        model = joblib.load(ART / artf)
        pmf = total_pmf(model, adv[model.feats])
        obs = (adv[ch].astype(int) + adv[ca].astype(int)).values
        u, p = mid_pit(pmf, obs)
        Z[:, j] = norm.ppf(u); LOGP[:, j] = np.log(p)
    adv["_z0"], adv["_z1"], adv["_z2"] = Z[:, 0], Z[:, 1], Z[:, 2]
    adv["_lp"] = LOGP.sum(1)

    # correlação empírica global (referência)
    print("corr(z) global:\n", np.round(np.corrcoef(Z.T), 3), flush=True)

    cuts = np.linspace(0.5, 0.85, 4); rows = []
    for c in cuts:
        n = int(len(adv) * c); m = int(len(adv) * min(c + 0.15, 1.0))
        tr, te = adv.iloc[:n], adv.iloc[n:m]
        if len(te) < 80: continue
        Ztr = tr[["_z0", "_z1", "_z2"]].values; Zte = te[["_z0", "_z1", "_z2"]].values
        S = np.corrcoef(Ztr.T)                      # matriz da cópula (estimada no passado)
        Sinv = np.linalg.inv(S); sign, logdet = np.linalg.slogdet(S)
        # densidade da cópula gaussiana por linha (test)
        quad = np.einsum("ij,jk,ik->i", Zte, (Sinv - np.eye(3)), Zte)
        log_c = -0.5 * logdet - 0.5 * quad
        nll_indep = -te["_lp"].values                       # −Σ log pmf
        nll_cop = nll_indep - log_c                          # + correção da cópula
        rows.append(dict(fold=round(c, 2), n=len(te),
                         nll_indep=nll_indep.mean(), nll_cop=nll_cop.mean(),
                         dNLL=(nll_cop - nll_indep).mean(),
                         corr01=S[0, 1], corr02=S[0, 2], corr12=S[1, 2]))
    R = pd.DataFrame(rows)
    print("\n=== NLL conjunto: independente vs cópula gaussiana ===")
    print(R.to_string(index=False))
    dnll = R.dNLL.mean()
    verdict = "APROVADO" if (dnll < 0 and int((R.dNLL < 0).sum()) >= len(R) - 1) else "REPROVADO"
    print(f"\n>> dNLL medio {dnll:+.4f} (cópula melhora {int((R.dNLL<0).sum())}/{len(R)}) | VEREDITO: {verdict}")
    (ROOT / "data" / "reports").mkdir(parents=True, exist_ok=True)
    R.to_csv(ROOT / "data" / "reports" / "exp7_multivariate.csv", index=False)


if __name__ == "__main__":
    main()
