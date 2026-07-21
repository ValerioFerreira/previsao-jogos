# Internal Services Reference

This document covers the core internal backend services, their dependencies, inputs, outputs, and methods.

---

## 1. Predictor Service ([predictor_service.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/services/predictor_service.py))

*   **Responsibility:** Interacts with the public data tables (`matches`, `fixture_index`, `referees`) and manages the caching of historical match reports.
*   **Key Functions:**
    *   `get_recent_matches(db, team_name, limit)`: Fetches past games (up to 60) for a selection.
    *   `get_competition_benchmark(db, competition_name)`: Returns average metrics for a league tournament.
    *   `get_team_anomalies(db, team_name)`: Detects abnormal performance spikes using Z-scores.
    *   `get_goal_timing(db, team_name)`: Evaluates timing peaks based on 15-minute intervals.

---

## 2. Authentication Service ([auth/service.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/auth/service.py))

*   **Responsibility:** Coordinates signups, password verification, session tokens, and OTP flows.
*   **Dependencies:** `app.core.security` (argon2), `app.core.email` (ZeptoMail).
*   **Key Methods:**
    *   `register_user(db, email, cpf, phone)`: Validates inputs, creates a temporary user record, and dispatches registration OTP code.
    *   `verify_email_otp(db, email, code)`: Checks and consumes code, transitioning user status to verified.
    *   `authenticate_user(db, email, password)`: Computes argon2 password hash validation and yields session refresh JWTs.

---

## 3. Credit Wallet Ledger Service ([wallet/service.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/wallet/service.py))

*   **Responsibility:** Ledger audits, balance reservation, and balance release.
*   **Dependencies:** `SQLAlchemy.orm.Session`.
*   **Key Methods:**
    *   `adjust_wallet_balance(db, wallet_id, amount, reserved_delta, tx_type)`: Performs an atomic ledger insertion, calculating balances after insertion.
    *   `reserve_credit(db, wallet_id, reference_type, reference_id)`: Moves 1 credit from `available` to `reserved` balance.
    *   `release_credit(db, wallet_id, reference_type, reference_id)`: Unlocks 1 reserved credit back to available balance.

---

## 4. Selection Settlement Service ([bets/settlement.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/bets/settlement.py))

*   **Responsibility:** Processes finished matches to resolve open promotional tickets.
*   **Dependencies:** `app.domains.bets.results.ResultProvider` (API-Football data provider).
*   **Key Methods:**
    *   `evaluate_leg(group, selection, match_result)`: Evaluates if a single prediction leg won or lost based on real statistics.
    *   `settle_bet(db, bet, result)`: Evaluates all selections in a ticket. Updates status to resolved, releasing/consuming wallet credits.
    *   `run_due_settlements(db, provider)`: Batches and settles all pending tickets.

---

## 5. Affiliate Service ([affiliates/service.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/domains/affiliates/service.py))

*   **Responsibility:** Attribution tracking, partnership requests, and affiliate payouts.
*   **Key Methods:**
    *   `apply_for_partnership(db, user_id, cpf, phone)`: Registers active partners.
    *   `attach_checkout_attribution(db, order_id, anon_id, ref_code)`: Associates payment checkouts to referring campaigns.
