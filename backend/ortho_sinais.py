import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
import joblib

STYLE_FEATS_FULL = [
    "home_style_crosses_l5", "home_style_crosses_l10",
    "away_style_crosses_l5", "away_style_crosses_l10",
    "home_style_ppda_l5", "home_style_ppda_l10",
    "away_style_ppda_l5", "away_style_ppda_l10",
    "home_style_fouls_suff_ratio_l5", "home_style_fouls_suff_ratio_l10",
    "away_style_fouls_suff_ratio_l5", "away_style_fouls_suff_ratio_l10"
]

def fit_ortho_regressions(df_train):
    """
    Fits Style_Feature ~ elo_diff strictly on the training split.
    Returns a dict with static regression weights.
    """
    weights = {}
    X_train = df_train[["elo_diff"]].values
    for feat in STYLE_FEATS_FULL:
        mask = df_train[feat].notna() & df_train["elo_diff"].notna()
        reg = LinearRegression()
        reg.fit(X_train[mask], df_train.loc[mask, feat].values)
        weights[feat] = {
            "intercept": float(reg.intercept_),
            "coef": float(reg.coef_[0])
        }
    return weights

def apply_ortho_residuals(df, weights):
    """
    Applies the static weights to compute residuals on the fly:
    resid_feature = raw_feature - (intercept + coef * elo_diff)
    """
    df_copy = df.copy()
    for feat, coefs in weights.items():
        intercept = coefs["intercept"]
        coef = coefs["coef"]
        resid_name = f"resid_{feat}"
        df_copy[resid_name] = df_copy[feat] - (intercept + coef * df_copy["elo_diff"])
        
    # Calculate diff of residuals
    for base_feat in ["style_crosses_l5", "style_crosses_l10",
                      "style_ppda_l5", "style_ppda_l10",
                      "style_fouls_suff_ratio_l5", "style_fouls_suff_ratio_l10"]:
        df_copy[f"diff_resid_{base_feat}"] = df_copy[f"resid_home_{base_feat}"] - df_copy[f"resid_away_{base_feat}"]
        
    return df_copy
