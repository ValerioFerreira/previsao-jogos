# Domain Rules & Prediction Logic

This document details the core business rules, financial ledger behaviors, promotion requirements, and mathematical concepts behind the forecasting model.

---

## 1. Credit Ledger & Wallet Rules

The wallet domain ([wallet](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/wallet/router.py)) operates on a strict double-entry-style **append-only ledger** model to prevent race conditions or balance discrepancies:
*   **Balance Lock:** Wallet balances (`available_balance` and `reserved_balance`) are only updated within the same database transaction as the creation of a `credit_transactions` log entry.
*   **Idempotency:** Every transaction requires a unique `idempotency_key`. A duplicated key instantly triggers a conflict rollback, protecting against double-billing.

### Transaction Types
*   `purchase`: Credits added by purchasing a credit package.
*   `bonus`: Free credits given on registration (default bonus is 8 credits) or promotional referrals.
*   `reservation`: 1 credit is temporarily held when creating a "Partida Futura" analysis.
*   `reservation_release`: Credit returned to `available_balance` if a promo selection fails or is voided.
*   `consumption`: Credit permanently deducted from the wallet (occurs immediately for "Análise Independente" or when a promo selection is validated).

---

## 2. "ParcerIA" Promotion Rules

The "ParcerIA" promotion (historically named "Só Paga se Acertar") is governed by the following rules:
*   **Eligibility:** Only enabled for Future Matches (scheduled matches that have not yet started).
*   **Combined Odd Limitation:** A selection ticket cannot exceed a combined odd of **$2.00$**.
*   **Markets Mapping:** A ticket combines up to 4 selections from different market groups (e.g. escanteios, cartões, gols). Interdependent markets of the same base type (e.g. over 1.5 goals and over 2.5 goals) are blocked using the [base_market](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/bets/markets.py) checker.
*   **Auto Selection:** If a user prefers not to select manually, the system auto-generates a ticket with combined odds as close to $2.00$ as possible.
*   **Immutability:** Once confirmed by the user, the ticket cannot be edited or deleted.
*   **Settlement Flow:** The settlement engine ([settlement.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/bets/settlement.py)) processes the ticket post-match:
    *   If **all** legs win $\implies$ Status: `won` $\implies$ Credit is **consumed**.
    *   If **any** leg loses $\implies$ Status: `lost` $\implies$ Credit is **refunded**.
    *   If any leg cannot be resolved (postponed match) $\implies$ Status: `void` $\implies$ Credit is **refunded**.

---

## 3. Mathematical Predictions Logic

### 3.1 Dixon-Coles Bivariate poisson model
For match outcomes (1X2, BTTS, Over/Under 2.5, Exact Score), the platform implements a Dixon-Coles model combined with a Negative Binomial distribution in [dixon_coles_model.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/scripts/dixon_coles_model.py):
*   **Attack & Defense Estimation:** A Gradient Boosting Regressor (GBM) estimates expected home goals $\lambda$ and away goals $\mu$.
*   **Low Score Dependency:** Dixon-Coles introduces a correction parameter $\tau(x,y)$ to adjust low-scoring outcomes (0-0, 1-0, 0-1, 1-1) where independent Poisson distributions under-represent actual draw rates:
    $$P(X=x, Y=y) = \tau(x,y) \cdot f(x;\lambda) \cdot g(y;\mu)$$

### 3.2 Count Models (Negative Binomial & Generalized Poisson)
*   **Negative Binomial (NB):** Applied to escanteios, shots, and shots on target to account for high variance (overdispersion):
    $$\text{Var}(X) = \mu + \alpha \mu^2 > \mu$$
*   **Generalized Poisson (GP):** Applied to cards where counts are low and the distribution is closer to Poisson.
*   **Cascade Structure:** Shots are predicted first. The predicted value `pred_shots` is then injected as a feature for corners and cards predictions.

### 3.3 Value Betting & De-Vig Calculation
*   **Implied Probability:** $P_{\text{raw}} = \frac{1}{\text{odd}}$.
*   **De-Vigging (Margem da Casa):** For a 2-way market (e.g. Over/Under):
    $$\text{Overround} = \frac{1}{\text{odd}_{\text{over}}} + \frac{1}{\text{odd}_{\text{under}}}$$
    $$P_{\text{clean}} = \frac{P_{\text{raw}}}{\text{Overround}}$$
*   **Expected Value (EV):** Calculated by comparing the clean model probability ($P_{\text{model}}$) to the bookmaker odd ($\text{odd}_{\text{house}}$):
    $$\text{EV} = P_{\text{model}} \cdot (\text{odd}_{\text{house}} - 1) - (1 - P_{\text{model}})$$
    If $\text{EV} > 0$, the market contains "Value".
