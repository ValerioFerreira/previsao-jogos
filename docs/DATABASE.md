# Database Schema & Migrations

This document describes the database architecture, schema division, table descriptions, migrations framework, and performance optimizations.

---

## 1. Schema Division

To protect the integrity of the Machine Learning features and allow transactional features (users, payments, tickets) to grow independently, the database is divided into two distinct logical areas inside the public schema:

1.  **Public Data Tables (Stateless Data Ingestion):**
    *   Updated via pandas and SQLAlchemy Core during ETL cycles.
    *   No constraints or relationships enforced to maximize write throughput.
    *   Table names: `matches`, `features_enriched`, `fixture_index`, `past_fixtures`, `referees`, `team_ids`, `odds_registry`, `match_detail_cache`.
2.  **Transactional Application Tables (ORM & Migrations):**
    *   Managed by SQLAlchemy 2.0 ORM declarations under `backend/app/domains/*/models.py`.
    *   Table names are strictly prefixed with **`app_`**.
    *   Versioned via **Alembic** migrations.

---

## 2. Table Schemas & Relationships

```
                     +-------------------+
                     |     app_users     |
                     +-------------------+
                               ||
          +====================++====================+
          ||                   ||                   ||
          \/                   \/                   \/
+-------------------+ +------------------+ +-------------------+
|    app_wallets    | | app_auth_session | | app_legal_accept  |
+-------------------+ +------------------+ +-------------------+
          ||
          \/
+-------------------+
|  app_credit_txs   |
+-------------------+
```

### 2.1 Core Identity tables
*   **`app_users`:** Stores credentials and verification status.
    *   `id` (UUID, Primary Key)
    *   `email` (CITEXT, Case-Insensitive Unique)
    *   `cpf` (VARCHAR(11), Unique)
    *   `status` (Enum: `pending_verification`, `active`, `blocked`, `deleted`)
    *   `role` (Enum: `user`, `admin`, `superadmin`)
*   **`app_otp_codes`:** Temporary codes for registration validation.
    *   `user_id` (UUID, Foreign Key $\rightarrow$ `app_users.id`)
*   **`app_auth_sessions`:** Keeps track of refresh token hashes and user agent IPs.

### 2.2 Billing & Ledger tables
*   **`app_wallets`:** Derivative balances of user credits.
    *   `user_id` (UUID, Unique Foreign Key $\rightarrow$ `app_users.id`)
    *   `available_balance` (Decimal)
    *   `reserved_balance` (Decimal)
*   **`app_credit_transactions`:** Ledger log of all movements.
    *   `wallet_id` (UUID, Foreign Key $\rightarrow$ `app_wallets.id`)
    *   `type` (Enum: `purchase`, `bonus`, `reservation`, `consumption`, etc.)
    *   `idempotency_key` (VARCHAR, Unique)

### 2.3 Selections & Bilhetes tables
*   **`app_analyses`:** Persistent snapshot of predictions.
    *   `snapshot` (JSONB - contains full probability arrays)
*   **`app_bets` (Seleções):**
    *   `user_id` (UUID, Foreign Key $\rightarrow$ `app_users.id`)
    *   `analysis_id` (UUID, Foreign Key $\rightarrow$ `app_analyses.id`)
    *   `status` (Enum: `awaiting_start`, `won`, `lost`, `credit_consumed`, etc.)
*   **`app_bet_selections`:** Leg level selections.
    *   `bet_id` (UUID, Foreign Key $\rightarrow$ `app_bets.id`)

---

## 3. Alembic Migrations

Migrations are isolated in [backend/alembic](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/alembic).
To avoid interfering with the public data tables (e.g. `matches`), the migration script [env.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/alembic/env.py) implements the `include_object` filter:

```python
def include_object(object, name, type_, reflected, compare_to):
    # Only manage objects with app_ prefix
    if type_ == "table":
        return name.startswith("app_")
    return True
```

*   **Command to apply migrations:**
    ```bash
    cd backend
    ..\.venv\Scripts\python -m alembic upgrade head
    ```

---

## 4. Performance Optimizations

### 4.1 Neon Network Egress Optimization
Historically, loading raw JSON stats (`match_detail_cache`) on every request created massive egress bandwidth overhead. This was resolved by precomputing hourly/daily stats using [precompute_aggregates.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/scripts/precompute_aggregates.py). It populates aggregate tables:
*   `referee_stats_agg` (264 kB)
*   `goal_timing_agg` (280 kB)
*   `competition_bench_agg` (16 kB)

These tables allow the server to fetch a single row by index rather than querying full database columns.

### 4.2 SQLite Local Mirror Cache
For local development and heavy training runs, [raw_cache.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/services/raw_cache.py) redirects requests to a local SQLite cache file `backend/data/raw_cache.sqlite` to bypass Neon queries.
