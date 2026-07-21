# API Module

This document details the REST API endpoints, routing structure, authentication filters, and error mappings.

---

## 1. Purpose

The API module handles incoming REST client calls, processes JSON validation, checks CORS origins, verifies user roles, and maps core domain routes.

---

## 2. Files Involved

*   **FastAPI App ([main.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/main.py)):** Instantiates `FastAPI`, applies CORS headers, registers domain routers, and mounts the global cron endpoints.
*   **API Schemas ([schemas.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/schemas.py)):** Stateless prediction schemas.
*   **Authentication filters ([auth/deps.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/deps.py)):** Authentication wrappers (`get_current_user`, `require_admin`).
*   **Domain Routers:** Sub-directories under `/backend/app/domains/` housing domain-level routers (e.g. `bets/router.py`, `payments/router.py`).

---

## 3. Core Routing Registry

All domain routers are registered in the main FastAPI application [main.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/main.py):

*   `auth_router` $\implies$ `/auth`
*   `wallet_router` $\implies$ `/wallet`
*   `payments_router` $\implies$ `/payments`
*   `analysis_router` $\implies$ `/analysis`
*   `bets_router` $\implies$ `/bets`
*   `admin_router` $\implies$ `/admin`

---

## 4. Key Request Flows

### 4.1 Prediction Request
```
[GET /h2h?home={team1}&away={team2}]
         ||
         \/
1. Validate team names using alias map
2. Load baseline Elo and rolling averages
3. Calculate live forecast
4. Return H2HResponse JSON
```

### 4.2 Checkout Flow
```
[POST /payments/orders/checkout]
         ||
         \/
1. Authenticate user
2. Create order record with state `created`
3. Call Mercado Pago API for Checkout Pro link
4. Return CheckoutResponse containing redirect URL
```
