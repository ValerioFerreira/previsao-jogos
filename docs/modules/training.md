# Training & Validation Module

This document details the offline model training pipelines, cross-validation configurations, and model diagnostic scripts.

---

## 1. Purpose

The Training and Validation module manages the offline optimization of machine learning models. It processes the historical dataset, fits the regression weights, calculates maximum likelihood parameters for the count distributions, and builds the post-processing isotonic calibrators.

---

## 2. Files Involved

*   **Training Entrypoint ([scripts/train_and_save_apifootball.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/scripts/train_and_save_apifootball.py)):** Loads dataset, builds folds, fits Dixon-Coles, Negative Binomial, and Generalized Poisson models, and serializes the resulting artifacts.
*   **Model Diagnostic ([scripts/diagnose_models.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/scripts/diagnose_models.py)):** Runs calibration and accuracy checks.
*   **Calibration Optimizer ([scripts/count_calibration_walkforward.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/scripts/count_calibration_walkforward.py)):** Tests and generates the isotonic calibrators (`ou_calibrators.joblib`).

---

## 3. Training Workflow

```
[international_features_enriched_apifootball.csv]
                      ||
                      \/
          1. Split chronologically
                      ||
                      \/
          2. Train GBRs on features
                      ||
                      \/
3. Optimize MLE for Dixon-Coles and Dispersion
                      ||
                      \/
  4. Fit post-hoc Isotonic Calibrators
                      ||
                      \/
         5. Save .joblib artifacts
```

### 3.1 Dixon-Coles Training Flow
1.  Trains two Scikit-Learn `GradientBoostingRegressor` instances to predict expected goals for home and away teams.
2.  Calculates the coupling parameter $\rho$ and dispersion parameters $r_h, r_a$ by maximizing log-likelihood (MLE) on the residual goals:
    $$\log L(\rho, r_h, r_a) = \sum \log P(X=x, Y=y)$$

### 3.2 Count Models Training Flow
1.  Trains regression models (e.g. Ridge or GBR) to output expected averages ($\lambda$) for corners, cards, or shots.
2.  Solves the Negative Binomial dispersion parameter $r$ using the Nelder-Mead optimization method to minimize the negative log-likelihood of counts.
3.  For corners, the dispersion parameters are fixed ($r_H=10, r_A=8.5$) to prevent tail calibration errors in GAMLSS dynamic models.

---

## 4. Expanding Temporal Folds

Cross-validation does *not* use random K-fold splits (which would leak future statistics into past records). Instead, the system uses expanding temporal folds:

*   **Fold 1:** Train on matches from 2016 to 2021; Test on 2022.
*   **Fold 2:** Train on matches from 2016 to 2022; Test on 2023.
*   **Fold 3:** Train on matches from 2016 to 2023; Test on 2024.
*   **Fold 4:** Train on matches from 2016 to 2024; Test on 2025/2026.

This ensures the model is evaluated on future data relative to its training set, matching the real-world inference scenario.
