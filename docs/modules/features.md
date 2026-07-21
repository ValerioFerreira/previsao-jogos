# Features Module

This document details the feature engineering pipeline, features grouping, and time-series rules.

---

## 1. Purpose

The Features module processes raw historical match records into enriched point-in-time features. This ensures models only train on information that was available *before* kickoff (preventing data leakage).

---

## 2. Files Involved

*   **Final Dataset Builder ([build_final_dataset.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/build_final_dataset.py)):** Aggregates data sources, calculates Elo, formats rolling windows, and outputs the training CSV/Parquet files.
*   **Orthogonal Style Residuals ([ortho_sinais.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/backend/ortho_sinais.py)):** Removes Elo signal from advanced parameters to extract pure playstyle residuals.

---

## 3. Core Feature Groups

The feature space consists of $158$ base features (up to $274$ for count models):

### 3.1 strength & Mando (Elo Features)
*   `home_elo_pre` / `away_elo_pre`: Pre-match Elo ratings.
*   `elo_diff`: Elo home minus away.
*   `elo_home_winprob`: Pure probability calculated using Elo rating difference and home advantage weight.
*   `neutral`: Field neutrality flag.
*   `real_home_advantage`: Active mando weight (zero if neutral field).

### 3.2 Time Series Rolling Features (l3 / l5 / l10)
Calculated using rolling windows over the matches table:
*   `winrate_l5` / `winrate_l10`: Historical win rate.
*   `gf_l5` / `ga_l5`: Average goals scored and conceded.
*   `bttsrate_l10`: Ambas Marcam historical rate.
*   `csrate_l10`: Clean sheet historical rate.
*   `days_rest`: Number of days since the team's last match.

### 3.3 Box-Score Statistics (Contagem Models Only)
*   `sb_shots_l5` / `sb_corners_l10`: Rolling averages for shots and corners.
*   `resid_*_style_*`: Residual pressing style markers.
*   `pred_*_shots`: Predicted shots generated during cascade step.

---

## 4. Ingestion Workflow

```
[Raw Matches Database]
          ||
          \/
1. Sort matches chronologically
2. Compute pre-match Elo rating per team
3. Calculate shift(1) rolling averages (l3, l5, l10)
4. Compute rest days since previous match
5. Calculate tournament weights and final features row
```
