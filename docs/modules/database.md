# Database Module

This document details the database connectivity, transaction mechanisms, tables mapping, and migration filters.

---

## 1. Purpose

The Database module configures the database connection to the serverless Neon PostgreSQL provider. It handles transactional operations for the application (`app_*` tables) using SQLAlchemy ORM, and bulk data updates for the prediction engine (Core and pandas).

---

## 2. Files Involved

*   **Connection manager ([db/connection.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/db/connection.py)):** Instantiates the SQLAlchemy Engine, controls the pool sizes, and exports Core write helpers (`upsert_df`, `truncate_and_append`).
*   **Base Declarative ORM ([db/base.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/db/base.py)):** Declares the SQLAlchemy declarative base used by domain entities. Includes global mixins (`UUIDPrimaryKeyMixin`, `TimestampMixin`).
*   **Alembic Environment ([alembic/env.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/alembic/env.py)):** Configures migrations to run either offline or online.

---

## 3. Core Engine Settings & Optimization

To handle serverless scale downs and potential connection terminations:
*   **`pool_pre_ping=True`:** Prevents querying terminated TCP connections by checking connection health before querying.
*   **`pool_size=5` / `max_overflow=10`:** Keeps the active connection pool within constraints.
*   **Aggregate Tables:** Read optimizations are implemented in [aggregates.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/app/services/aggregates.py) to write and fetch precomputed stats, preventing heavy scans on raw blobs.

---

## 4. Alembic Migration Filter

Migrations are isolated so they never modify raw data tables like `matches` or `features_enriched`. The filter in `alembic/env.py` checks target table names:

```python
def include_object(object, name, type_, reflected, compare_to):
    # Only manage objects with app_ prefix
    if type_ == "table":
        return name.startswith("app_")
    return True
```

This ensures only entities defined with the prefix `app_` are managed by Alembic.
