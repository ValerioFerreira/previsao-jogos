# System Architecture — Monorepo Overview

This document describes the technical architecture, infrastructure strategy, and module interactions of the Previsão de Jogos (ApostAI) platform.

---

## 1. Monorepo Overview

The repository is organized as a monorepo containing two main packages: the frontend and the backend.

```
previsao-jogos/
├── frontend/                # Next.js client-side application
└── backend/                 # FastAPI server-side application & ML models
```

### 1.1 Technical Stack
*   **Frontend:** Next.js (TypeScript) running on [Vercel](https://vercel.com) using Turbopack. Uses Tailwind CSS for styles and Lucide-React for icons.
*   **Backend:** Python 3.12 (FastAPI) running on [Render](https://render.com). Uses Uvicorn for local execution.
*   **Database:** Neon serverless PostgreSQL database (with SQLAlchemy ORM and Alembic migrations).

---

## 2. Infrastructure & Deploy Strategy

The monorepo separates static client-side rendering from transactional/predictive API computation:

```
+------------------+         REST API (CORS)          +------------------+
|     Vercel       | ===============================> |     Render       |
| (Next.js Client) | <=============================== | (FastAPI Server) |
+------------------+                                  +------------------+
                                                               ||
                                                       SQLAlchemy (ORM / Core)
                                                               ||
                                                               \/
                                                      +------------------+
                                                      | Neon PostgreSQL  |
                                                      |   (Serverless)   |
                                                      +------------------+
```

*   **Frontend (Vercel):** Connected via a custom domain `apostainfo.com.br` in production. Communicates with the backend using the environment variable `NEXT_PUBLIC_API_URL`.
*   **Backend (Render):** Deployed as a Docker-less web service. Exposes FastAPI documentation under `/docs`. Restricted via CORS to allow origins resolved dynamically from environment configurations via [allowed_origins](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/services/predictor_service.py).
*   **Database (Neon):** Managed serverless database. Configured with connection pooling parameters (`pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`) in [backend/app/db/connection.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/db/connection.py) to mitigate cold starts and handle serverless scale down.

---

## 3. Module Architecture (Backend)

The backend is structured into two distinct execution paths: **Data Pipelines & ML Models** (stateless, pandas-based Core operations) and the **Transactional Layer** (modular DDD-inspired domains using SQLAlchemy ORM).

### 3.1 Backend Layout
The entry point of the server is [main.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/main.py). It initializes the application, checks startup configs in [startup.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/core/startup.py), and mounts the modular routers.

```
backend/app/
├── core/                    # System configurations, security primitives, startup gates
├── db/                      # Declarative base, database engines, and migration scripts
├── domains/                 # Domain modules (auth, wallet, payments, analysis, bets, etc.)
├── services/                # Backend statistics and data-lake aggregator services
├── schemas.py               # Global Pydantic models for stateless predictions
└── predictor.py             # Inference motor that loads ML artifacts and calculates metrics
```

### 3.2 Key Backend Domains
As highlighted in the Graphify community structure, the transactional logic is divided into domains under `backend/app/domains/`:
1.  **Auth ([auth](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/router.py)):** Manages user signups, argon2 hashing, JWT tokens generation, and Zoho ZeptoMail OTP emails.
2.  **Wallet ([wallet](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/wallet/router.py)):** Ledger based transactions representing credits.
3.  **Payments ([payments](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/payments/router.py)):** Interacts with payment gateway (Mercado Pago adapter).
4.  **Analysis ([analysis](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/analysis/router.py)):** Creates predictive snapshot mappings that are persisted to prevent data shift.
5.  **Bets / Seleções ([bets](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/bets/router.py)):** Implements the "Monte sua Seleção" bilhete rules and safety check validations.
6.  **Affiliates ([affiliates](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/affiliates/router.py)):** Click attributes, commissions, and coupon relations.
7.  **Legal ([legal](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/legal/router.py)):** User acceptances for versioned Terms & Privacy rules.
8.  **Support ([support](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/support/router.py)):** Credit adjustment and transactional refund tickets.
9.  **Admin ([admin](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/admin/router.py)):** Global settings modification, user blocking, and audit logger.

---

## 4. Communication & Flow Architecture

### 4.1 Internal API Communication
All frontend routes consume REST endpoints provided by FastAPI.
Authentication is stateful client-side, managed by [AuthContext.tsx](file:///c:/Users/10341953440/Downloads/previsao-jogos/frontend/src/lib/AuthContext.tsx) which caches JWT bearer tokens.
Local persistence of selections and active analysis is managed by [PredictionContext.tsx](file:///c:/Users/10341953440/Downloads/previsao-jogos/frontend/src/lib/PredictionContext.tsx) inside the client browser.

### 4.2 Module Dependency Chain
The data pipeline writes raw data to Postgres which is read by [predictor_service.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/services/predictor_service.py).
When a user requests a prediction, `analysis/service.py` invokes [Predictor](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/predictor.py), records the JSON result, reserves 1 credit from `wallet/service.py` via ledger entries, and exposes the `BetBuilder` selection panel.

A cron process periodically hits `/api/cron/settle-bets` to resolve the selections and update ledger balances.
