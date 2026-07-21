# Machine Learning Models

This document details the Machine Learning classifiers, feature pipelines, training processes, and validation protocols used in production.

---

## 1. Model Architectures & Artifacts

All models are trained offline and serialized as `.joblib` artifacts inside [backend/model_artifacts/](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/model_artifacts).

| Target | Artefact | Architecture | Description |
|---|---|---|---|
| Match Outcome / Goals / BTTS / Over 2.5 / Correct Score | `dixon_coles_goals.joblib` | **Dixon-Coles NB** | Bivariate Dixon-Coles model mapping lambdas ($\lambda$) and mus ($\mu$) via Gradient Boosting Regressors. |
| Corners | `corners_cascade_rfixo.joblib` | **Negative Binomial (NB)** | Count model with fixed dispersion parameters ($r_{\text{home}}=10$, $r_{\text{away}}=8.5$) fed by predicted shots. |
| Shots / Shots on Target | `shots_nb.joblib` & `shots_on_target_nb.joblib` | **Negative Binomial (NB)** | Count model with time-decay parameters ($H=2$). |
| Cards | `cards_gp.joblib` | **Generalized Poisson (GP)** | Low-count model mapping yellow/red card distributions. |

---

## 2. In-Depth Architecture Details

### 2.1 Dixon-Coles NB (`dixon_coles_model.py`)
Calculates joint goals distributions. It is powered by two Gradient Boosting Regressors (sklearn GBM) trained on $158$ features to estimate home expected goals ($\lambda$) and away expected goals ($\mu$).
A maximum likelihood optimization estimates:
*   Dispersion parameters ($r_h, r_a$) for the Negative Binomial marginals.
*   The Dixon-Coles coupling coefficient $\rho$ (typically $\approx -0.046$) which shifts probabilities for low scores to match historical draw patterns.

### 2.2 Cascaded Corners & CardsNB
*   **CornersNB:** Maps corners using Negative Binomial distributions to address overdispersion (variance $>$ mean).
*   **Cascade Flow:** The system first predicts shots (`pred_shots`). This prediction is injected as a feature into the corners and cards models.
*   **Generalized Poisson (GP):** Used for cards because cards have a low mean count and Poisson assumptions work better than Negative Binomial under low dispersion.

---

## 3. Features Configuration

The models consume up to $274$ point-in-time features:
1.  **Base Features (158):** pre-match Elo ratings, Elo diff, Elo win probability (`elo_home_winprob`), resting days (`*_days_rest`), tournament weights, H2H statistics, and goal averages (winrate, bttsrate, clean sheet rate) computed in l3/l5/l10 rolling windows.
2.  **Advanced Statistics:** Rolling averages of corners, shots, fouls, cards, and possession (only available for the 41% of games with box-score data).
3.  **Orthogonal Style Residuals:** Calculated in [ortho_sinais.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/ortho_sinais.py) to extract pressing metrics independent of team strength.
4.  **Mando Interactions:** Product interaction terms between the neutral field indicator and offensive drivers.

---

## 4. Calibration & Walk-Forward Validation

### 4.1 Isotonic O/U Calibrators
In extreme tail distributions (e.g. Over 11.5 corners), Negative Binomial and Generalized Poisson calculations can be miscalibrated.
The system applies **Isotonic Regression** calibrators (`ou_calibrators.joblib`) on the total lines. This preserves probability order (monotonicity) while significantly reducing ECE (Expected Calibration Error).

| Target | ECE (Before) | ECE (Calibrated) | Veredito |
|---|---|---|---|
| Escanteios | $4.5\%$ | **$2.8\%$** | ✅ Promovido |
| Cartões | $2.8\%$ | **$2.1\%$** | ✅ Promovido |
| Finalizações a gol | $3.0\%$ | **$2.5\%$** | ✅ Promovido |

### 4.2 Validation Protocol ("The Gate")
No model is promoted to production without passing the validation gate in [protocol.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/bets/markets.py):
1.  **Temporal Expanding Folds:** Chronological cross-validation (training on past records, testing on future windows). Split-validation is forbidden.
2.  **Metrics Evaluation:** Focuses on probabilistic calibration:
    *   **Log-loss:** Penalizes overconfident wrong predictions.
    *   **ECE (Expected Calibration Error):** Measures alignment between model probability and historical frequency.
    *   **Tail-ECE:** Focuses on extreme lines.
    *   **Brier Score:** Quadratic error metric for binary lines.
