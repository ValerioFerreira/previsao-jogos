# Prediction Module

This document details the forecasting engine, its initialization steps, model loading, and calculation logic.

---

## 1. Purpose

The Prediction module acts as the core forecasting engine of the system. It loads trained ML models from `.joblib` files, processes pre-match features, applies calculations, and generates joint distributions for goals and count markets (corners, cards, shots, offsides).

---

## 2. Files Involved

*   **Predictor Engine ([predictor.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/predictor.py)):** Loads ML models, builds feature rows, calculates match distributions, and formats response JSONs.
*   **Dixon-Coles Model ([dixon_coles_model.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/scripts/dixon_coles_model.py) / [dixon_coles_model.py in backend](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/dixon_coles_model.py)):** Implements the bivariate goals model.
*   **Corners Model ([corners_nb_model.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/corners_nb_model.py)):** Negative Binomial model for corners total distributions.
*   **Cards Model ([cards_gp_model.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/cards_gp_model.py)):** Generalized Poisson model for yellow/red card distributions.
*   **Shots Model ([shots_nb_model.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/shots_nb_model.py)):** Negative Binomial model for shots.

---

## 3. Core Class: Predictor

The [Predictor](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/predictor.py) class acts as the singleton manager for model inference.

### 3.1 Initialization
When initialized, it loads the following ML models into memory:
*   `self.dc` $\implies$ Dixon-Coles model.
*   `self.corners` $\implies$ negative binomial model.
*   `self.cards` $\implies$ generalized poisson model.
*   `self.shots` & `self.shots_on_target` $\implies$ negative binomial models.
*   `self.ou_calibrators` $\implies$ isotonic calibrators.
*   `self.meta` $\implies$ metadata json (`meta.json`).
*   `self.results` $\implies$ historical database slim CSV (`results_slim.csv`).

### 3.2 Key Methods
*   **`predict(home_team, away_team, neutral, tournament)`:** Calculates the complete probability mappings for all supported markets.
    *   1. Normalizes team names using aliases.
    *   2. Computes the H2H stats summary.
    *   3. Generates the joint goals probability matrix (up to 10 goals).
    *   4. Cascades finalization predictions (`pred_shots`) to extract corners and cards.
    *   5. Returns the structured dictionary matching prediction schemas.
*   **`build_row(...)`:** Constructs a single feature row containing current statistics, Elos, resting days, and tournament parameters.
*   **`team_defaults(team)`:** Returns baseline parameters (Elo and rolling averages) for a given team name.
