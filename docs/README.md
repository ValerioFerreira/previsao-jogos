# Platform Documentation Index

Welcome to the technical documentation library. This directory contains detailed specifications, architectures, database schemas, and mathematical details.

---

## 1. System Core Documents

*   **[System Architecture](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/ARCHITECTURE.md):** High-level monorepo organization, frontend/backend directories layout, and serverless hosting environment.
*   **[System Overview](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/SYSTEM_OVERVIEW.md):** General description of features, prediction capabilities, and promotional systems.
*   **[Data Flow Architecture](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/DATA_FLOW.md):** Data ingestion pipeline (offline ETL) and online real-time inference flow.
*   **[Domain Rules & Core Logic](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/DOMAIN.md):** Credit ledger transactions, ParcerIA promotion ticket rules, and value betting formulas.
*   **[Database Schema & Migrations](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/DATABASE.md):** Public data tables vs. `app_*` ORM schemas and Alembic migration structures.
*   **[API Endpoint Reference](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/API.md):** Request/response schemas, verification endpoints, and rate-limits.
*   **[Internal Services Reference](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/SERVICES.md):** Backend core domain service functions and methods.
*   **[Machine Learning Models](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/ML_MODELS.md):** Bivariate Dixon-Coles, count models, tail calibration, and expanding temporal folds verification.
*   **[Glossary of Terms](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/GLOSSARY.md):** Definition of mathematical, technical, and domain concepts.
*   **[Technical Debt & Roadmap](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/TECH_DEBT.md):** Legacy rollbacks, database egress issues, and future ML improvements.

---

## 2. Visual Architecture Diagrams

*   **[General Architecture Layout](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/diagrams/architecture_general.md):** High-level component interactions.
*   **[Data Flow Flowchart](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/diagrams/data_flow.md):** Processing states from API-Football raw data to predictions.
*   **[Database Entity-Relationship Diagram](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/diagrams/database_er.md):** Visual database tables mapping.
*   **[Prediction Pipeline Flowchart](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/diagrams/prediction_pipeline.md):** Features ingestion, cascaded ML predictions, and odds outputs.
*   **[API Sequence Diagram](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/diagrams/api_flow.md):** API routes sequence flow.
*   **[Module Dependencies Graph](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/diagrams/module_dependencies.md):** Backend modular domains dependencies.

---

## 3. Module Deep Dives

*   **[Auth Domain](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/modules/auth.md):** OTP code management and signup gates.
*   **[Database Engine](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/modules/database.md):** SQLAlchemy connections, pooling parameters, and Alembic env files.
*   **[API Gateway](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/modules/api.md):** FastAPI app init, middlewares, and routers.
*   **[Prediction Core](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/modules/prediction.md):** Predictor class logic and live forecast execution.
*   **[Feature Engineering](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/modules/features.md):** Feature groups and pre-match construction.
*   **[Model Training](file:///c:/Users/10341953440/Downloads/previsao-jogos/docs/modules/training.md):** ML fitting scripts and expanding temporal folds validation.
