# API Reference

This document details the REST API endpoints provided by the FastAPI backend, including request/response formats, security parameters, and validation rules.

---

## 1. Authentication & Security

Most transactional endpoints require a valid JWT Access Token passed in the `Authorization` header:
`Authorization: Bearer <JWT_ACCESS_TOKEN>`

### 1.1 CORS Policies
CORS is restricted in production to the domain specified by the `FRONTEND_URL` environment variable (mapped to `apostainfo.com.br`). Local requests from `localhost:3000` are permitted by fallback.

---

## 2. Predictions & Analytics Endpoints (Stateless)

### 2.1 Get Teams
*   **Path:** `GET /teams`
*   **Response Model:** `TeamsResponse`
*   **Output:** Returns lists of available selections and active tournament weights.

### 2.2 Get Head to Head (H2H)
*   **Path:** `GET /h2h?home={team1}&away={team2}`
*   **Response Model:** `H2HResponse`
*   **Validation:** Throws `400 Bad Request` if teams are identical or unrecognized.

### 2.3 Get Referee Stats
*   **Path:** `GET /referees`
*   **Response Model:** `RefereeStatsResponse`
*   **Output:** Returns historical yellow/red cards and fouls averages per referee.

---

## 3. Transactional & Auth Endpoints (Modular Domains)

Mount paths are registered in the main FastAPI application [main.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/main.py):

### 3.1 Authentication Domain (`/auth`)
*   **`POST /auth/register`**: Registers a new user. Triggers a Zoho ZeptoMail OTP message.
*   **`POST /auth/verify-email`**: Verifies registration OTP.
*   **`POST /auth/login`**: Authenticates credentials and returns access/refresh JWT tokens.
*   **`POST /auth/refresh`**: Rotates the short-lived access token using a refresh token.

### 3.2 Wallet & Billing Domain (`/wallet`, `/payments`)
*   **`GET /wallet/balance`**: Returns current credit balance (available and reserved).
*   **`GET /wallet/transactions`**: Returns paginated credit ledger logs.
*   **`POST /payments/orders/checkout`**: Creates a Mercado Pago checkout link for credit packages.
*   **`POST /payments/webhooks/mercadopago`**: Receives payment notifications. Validated via signature HMAC verification.

### 3.3 Analysis & Bets Domain (`/analysis`, `/bets`)
*   **`POST /analysis/generate`**: Creates a prediction snapshot. Reserves 1 credit for future matches or consumes 1 immediately for independent ones.
*   **`GET /bets/markets/{analysis_id}`**: Retrieves option candidates for the "Monte sua Seleção" card.
*   **`POST /bets/preview`**: Simulates the combined odd in real-time applying the Gaussian Copula.
*   **`POST /bets/confirm`**: Registers a selection ticket. If payload is empty, triggers auto-selection.

### 3.4 Support & Admin Domains (`/support`, `/admin`)
*   **`POST /support/tickets`**: Creates a customer support ticket.
*   **`POST /admin/adjust-credits`**: Adjusts a user's wallet credit manually (requires admin role). Creates an audit log entry in `app_admin_audit_log`.

---

## 4. Error Handling & HTTP Status Codes

The API returns RFC-compliant JSON responses for errors:
```json
{
  "detail": "Error message description"
}
```

*   `400 Bad Request`: Invalid arguments (e.g. combined odds $> 2.00$ or missing fields).
*   `401 Unauthorized`: Missing, expired, or invalid JWT tokens.
*   `403 Forbidden`: Insufficient role permissions (e.g. non-admin accessing `/admin/*`).
*   `409 Conflict`: Double submission or duplicated idempotency key.
*   `429 Too Many Requests`: Triggered by sliding window rate-limiters.
*   `502 Bad Gateway`: External adapter integration failures (e.g. ZeptoMail email dispatch errors).
