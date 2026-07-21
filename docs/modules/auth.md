# Auth Module

This document details the authentication and identity verification system.

---

## 1. Purpose

The Auth module handles user onboarding, case-insensitive case identification, secure credential storage, sliding window rate limits, token-based verification (OTP), and JSON Web Token (JWT) session generation.

---

## 2. Architecture & Files Involved

The module resides in the domains structure:

*   **Router ([auth/router.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/router.py)):** Exposes registration, verification, login, token refresh, and logout endpoints.
*   **Service ([auth/service.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/service.py)):** Houses transactional business logic.
*   **Models ([auth/models.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/models.py)):** Declares the SQLAlchemy database mappings: `User`, `OtpCode`, `AuthSession`, and `AuthEvent` (Audit Log).
*   **Schemas ([auth/schemas.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/schemas.py)):** Pydantic models mapping registration and login inputs.
*   **Dependencies ([auth/deps.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/deps.py)):** Authentication filters (`get_current_user`, `require_admin`).
*   **Security Helpers ([core/security.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/core/security.py)):** Argon2 hashing helper functions and JWT encoders.
*   **Email Dispatcher ([core/email.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/core/email.py)):** Manages Zoho ZeptoMail integration.

---

## 3. Core Functions & Classes

*   **`User` Model:** Contains CPF, case-insensitive email (`CITEXT`), phone, password hash, status (`pending_verification`, `active`, `blocked`, `deleted`), and roles (`user`, `admin`).
*   **`OtpCode` Model:** Represents a verification ticket. Stores a HMAC code hash, purpose (`email_verify` / `password_reset`), expiration timestamp, and registration attempt counts.
*   **`register_user(db, email, cpf, phone)`:** Checks unique constraint duplicates, validates CPF structure, writes `User` (status: `pending_verification`), generates OTP, writes `OtpCode`, and dispatches verification email.
*   **`verify_email_otp(db, email, code)`:** Verifies code correctness. If valid, changes user status to `active` and dispatches `8 welcome bonus credits` to the wallet. If dispatching fails, it raises `502 Bad Gateway` and rolls back database entries to prevent orphaned accounts.

---

## 4. Internal Flow

```
[POST /auth/register]
        ||
        \/
1. Validate format & constraints
2. Create User (pending_verification)
3. Generate 6-digit OTP Code
4. Dispatch email via ZeptoMail
   ├── Success: DB Commit & Return 201
   └── Failure: DB Rollback & Return 502
```
