# Technical Debt & Engineering Roadmap

This document outlines identified areas of technical debt, architectural bottlenecks, model rollbacks, and future roadmap directions.

---

## 1. Architectural Bottlenecks & Code Debt

### 1.1 Database Egress (Neon Serverless)
*   **Current State:** Live API calls historically suffered from high network transfer costs because they loaded and parsed raw JSON stats (`match_detail_cache` - 44 MB) on the fly.
*   **Debt:** Although we precompute aggregates (`referee_stats_agg`, `goal_timing_agg`) to mitigate this, the raw `match_detail_cache` table still resides in the production Neon instance.
*   **Roadmap:** Migrate raw JSON tables off the primary Neon DB into an S3 bucket or local sqlite replica, keeping only transactional tables (`app_*`) and aggregate vectors on Neon.

### 1.2 Local SQLite Cache Dependency
*   **Current State:** Model training and ETL scripts bypass Neon by reading a local SQLite file `backend/data/raw_cache.sqlite`.
*   **Debt:** This introduces state synchronization drift between the production Neon DB and the developer's local environment.

---

## 2. Models Rollbacks & Experimental Findings

### 2.1 Dynamic Corners Dispersion (GAMLSS Rollback)
*   **The Issue:** We attempted to model escanteios dispersion dynamically ($r$ parameter) based on match variables using MLE (two-stage GAMLSS). This was rolled back because it overfit the body of the distribution and underestimated tail probabilities (resulting in a high Tail-ECE).
*   **Current State:** The system uses fixed dispersion values ($r_{\text{home}}=10$, $r_{\text{away}}=8.5$).
*   **Roadmap:** Investigate regularized dispersion models or hierarchical Bayesian priors to estimate dynamic dispersion safely.

### 2.2 Player Card & Referee Features
*   **Player Cards:** An experiment to predict "Jogador a levar cartão" failed the validation gate (`scripts/test_player_cards.py` yielded an AUC of $0.62$), primarily due to sparse player lineups in international windows.
*   **Referee Volatility:** Referee stats suffer from small sample sizes.
*   **Roadmap:** Implement hierarchical shrinkage models for referees (regressing referee stats toward their confederation mean).

---

## 3. Future Roadmap

1.  **xG Feature Extraction:** Currently, xG features are absent. Since xG data is available for ~41% of games in the raw API feed, extracting and imputing this value for low-coverage games could improve goals and shots predictions.
2.  **RPS & Yield Backtesting:** Integrate Ranked Probability Score (RPS) for goal distributions and build automated backtesting tools to track ROI based on historical odds closing data.
