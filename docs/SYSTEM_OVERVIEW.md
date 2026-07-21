# System Overview

This document presents a high-level view of the Previsão de Jogos (ApostAI) platform, its objective, key functionalities, and tech stack.

---

## 1. Goal of the System

The primary objective of the system is to calculate and serve **probabilistic predictions for international football (soccer) matches** (men's adult national selections).
Unlike typical platforms that output simple binary predictions (e.g. "team A wins"), ApostAI generates full probability distributions (PMFs) for match results, goals, corners, cards, offsides, and shots. This enables users to perform **value betting analysis** by comparing the model's fair odds against bookmakers' odds.

---

## 2. Key Features

1.  **Match Prediction Engine:** Calculates detailed statistical predictions using customized machine learning models trained on historical data.
2.  **Matchups & Visualizations:**
    *   **Style Radar:** Evaluates team stats (pressing, corners, cards, etc.) relative to international baselines using Recharts.
    *   **Style Matchup:** A 2x2 grid comparing home vs away attack and defense parameters.
    *   **Goal Timing (Heatmap):** Visualizes the probability of goals being scored during specific 15-minute intervals.
3.  **Monte sua Seleção Promotion (ParcerIA):**
    *   A promo offering risk-free credit consumption. The user registers a coupon or utilizes credits to request a future match analysis.
    *   The user creates a combination of up to 4 markets with a combined odd $\le 2.00$ (or requests an automatic suggestion).
    *   A credit is reserved. If the selection is validated (wins), the credit is consumed; if not, the credit is refunded.
4.  **Value Betting & De-Vig Tool:**
    *   Compares model probabilities to bookmaker odds.
    *   Computes expected value (EV) and removes bookmaker margin (de-vig) using opposite-side pricing.
5.  **User Wallet & Ledger:**
    *   Enables buying packages of credits via Mercado Pago.
    *   Maintains transaction transparency using an append-only ledger transaction log.
6.  **Partner & Affiliate Program:**
    *   Allows partners to solicit partnership, configure custom referral links, track conversion clicks, and earn comissions.

---

## 3. High-Level Flow

```
+--------------+        1. Select Match         +-----------------+
|   User UI    | =============================> |  FastAPI Server |
|  (Frontend)  | <============================= |    (Backend)    |
+--------------+       2. Return Cache /        +-----------------+
       ||                 Calculate Live                 ||
       ||                                                ||
       || 3. Spend Credit                       4. Query DB & Predict
       \/                                                \/
+--------------+                                +-----------------+
| Wallet / Led | <============================> |  ML Classifiers |
| (PostgreSQL) |                                |  (Scikit-Learn) |
+--------------+                                +-----------------+
```

---

## 4. Technologies Used

*   **Next.js (v15/16) / React / Tailwind CSS:** Used to build a responsive, dashboard-like single-page interface at [frontend/src/app/page.tsx](file:///c:/Users/10341953440/Downloads/previsao-jogos/frontend/src/app/page.tsx) and `/estatisticas`.
*   **FastAPI / Uvicorn:** Powers the backend REST endpoints.
*   **PostgreSQL (Neon) / SQLAlchemy / Alembic:** Provides ACID transaction safety and modular migrations.
*   **Scikit-Learn / Joblib / Pandas / NumPy:** Orchestrates the ML data processing, training, and real-time inference.
