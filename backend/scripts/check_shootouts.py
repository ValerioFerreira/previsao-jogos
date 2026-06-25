import sys
import pandas as pd
import numpy as np
from pathlib import Path

def check():
    csv_path = Path("international_features_enriched_apifootball.csv")
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # Split
    df_adv = df[df["has_advanced_stats"] == 1].copy()
    n_train_idx = int(len(df_adv) * 0.8)
    cutoff_date = df_adv.iloc[n_train_idx]["date"]
    
    df_train = df[df["date"] <= cutoff_date].copy()
    df_test = df[(df["date"] > cutoff_date) & (df["has_advanced_stats"] == 1)].copy()
    
    print("="*80)
    print("SHOOTOUT WINRATE FEATURE STATISTICS IN TRAIN AND TEST SETS")
    print("="*80)
    
    for col in ["home_shootout_winrate_pre", "away_shootout_winrate_pre"]:
        # Train
        train_col = df_train[col]
        train_nans = train_col.isna().sum()
        train_non_nans = train_col.dropna()
        print(f"{col} (TRAIN):")
        print(f"  Total rows: {len(df_train)}")
        print(f"  NaNs: {train_nans} ({train_nans/len(df_train)*100:.2f}%)")
        if len(train_non_nans) > 0:
            print(f"  Non-NaN Range: [{train_non_nans.min():.4f}, {train_non_nans.max():.4f}]")
            print(f"  Non-NaN Mean: {train_non_nans.mean():.4f}")
            print(f"  Non-NaN Median: {train_non_nans.median():.4f}")
            print(f"  Count of non-zero non-NaNs: {(train_non_nans != 0).sum()}")
            
        # Test
        test_col = df_test[col]
        test_nans = test_col.isna().sum()
        test_non_nans = test_col.dropna()
        print(f"{col} (TEST):")
        print(f"  Total rows: {len(df_test)}")
        print(f"  NaNs: {test_nans} ({test_nans/len(df_test)*100:.2f}%)")
        if len(test_non_nans) > 0:
            print(f"  Non-NaN Mean: {test_non_nans.mean():.4f}")
            print(f"  Count of non-zero non-NaNs: {(test_non_nans != 0).sum()}")
        print()

    # Let's inspect the snapshots in meta.json
    meta_path = Path("api/model_artifacts/meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    snapshot = meta.get("snapshot", {})
    print("="*80)
    print("SHOOTOUT WINRATE IN SNAPSHOTS (meta.json)")
    print("="*80)
    shootout_vals = []
    for team, snap in snapshot.items():
        val = snap.get("shootout_winrate_pre")
        if val is not None and pd.notna(val):
            shootout_vals.append((team, val))
    
    print(f"Total teams with shootout_winrate_pre in snapshot: {len(shootout_vals)} / {len(snapshot)}")
    shootout_vals.sort(key=lambda x: x[1], reverse=True)
    print("Top 10 teams by shootout_winrate_pre:")
    for team, val in shootout_vals[:10]:
        print(f"  {team}: {val:.4f}")

if __name__ == "__main__":
    check()
