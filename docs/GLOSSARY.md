# Glossary

This document defines technical, mathematical, and domain-specific terms used throughout the Previsão de Jogos platform.

---

## 1. Mathematical & Statistical Terms

*   **Bivariate Poisson / Dixon-Coles:** A model family that predicts the joint distribution of two dependent Poisson variables (goals scored by each team). Dixon-Coles adjusts these probabilities for low scores (0-0, 1-0, 0-1, 1-1) to account for correlation (draw tendency).
*   **Negative Binomial (NB):** A discrete probability distribution used for modeling count data (such as corners or shots) where the variance is significantly larger than the mean (overdispersion).
*   **Generalized Poisson (GP):** A generalization of the Poisson distribution. Useful for card counts where variance can be equal to or less than the mean (underdispersion).
*   **Expected Calibration Error (ECE):** A metric (expressed in %) that measures the difference between predicted probabilities and actual outcomes. For example, if a model predicts a $70\%$ probability for "Over 2.5 goals", the outcome should occur exactly $70\%$ of the time across those games.
*   **Log-Loss (Entropia Cruzada):** The primary metric used to evaluate probabilistic predictions. It heavily penalizes incorrect predictions made with high confidence.
*   **Brier Score:** The mean squared difference between predicted probabilities and actual binary outcomes (0 or 1).
*   **Isotonic Regression:** A non-parametric regression method that fits a monotonic (always increasing or always decreasing) curve to data. Used to calibrate tail probabilities.
*   **Gaussian Copula:** A mathematical function that binds individual marginal distributions (e.g. goals, corners, cards) into a joint multi-market distribution, accounting for correlation.

---

## 2. Domain & Platform Terms

*   **Monte sua Seleção:** The selection ticket panel where users combine up to 4 markets with combined odds $\le 2.00$ to participate in the ParcerIA promotion.
*   **ParcerIA Promotion (Só Paga se Acertar):** A risk-free promotion. A user's wallet credit is reserved. If the selection is validated (wins), the credit is consumed; if not, the credit is refunded.
*   **De-Vigging (Remover Margem):** The process of removing the bookmaker's commission (vig) from raw odds to calculate the true implied probability of an event.
*   **Expected Value (EV):** The theoretical return of a bet. An EV > 0 indicates "Value" (the odd offered by the bookmaker is higher than the model's calculated fair odd).
*   **Fator Árbitro:** Analytical stats showing a referee's historical card and foul averages, indicating if they tend to issue more cards than the tournament baseline.
*   **Radar de Anomalias:** A tool that highlights recent performance spikes or drops (Z-score deviation) compared to a team's historical average.
*   **Frequência de Minutos (Heatmap):** A visualization showing the distribution of goals scored or conceded in 15-minute intervals.
*   **Ledger Balance:** An append-only transaction log where balances are calculated by summing transaction records, ensuring billing transparency.
