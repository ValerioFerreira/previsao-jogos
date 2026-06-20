import pandas as pd
import numpy as np

# Load datasets
df_ap = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"])
stats = pd.read_parquet("data/built/matches.parquet")
stats["date_str"] = pd.to_datetime(stats["date"]).dt.strftime("%Y-%m-%d")

# Find the matches that have advanced stats
df_ap_adv = df_ap[df_ap["has_advanced_stats"] == 1].copy()

# Set up lookup to check raw values
stats_lookup = stats.set_index(["date_str", "team"])

print(f"Total advanced matches in df_ap: {len(df_ap_adv)}")

# Let's re-run the matching logic on the advanced matches to identify which ones were swapped or shifted.
swapped_matches = []
shifted_matches = []
exact_matches = []

for idx, row in df_ap_adv.iterrows():
    ht, at = row["home_team"], row["away_team"]
    d = row["date"]
    ds = d.strftime("%Y-%m-%d")
    
    # Let's find how this match was matched
    matched_delta = None
    matched_swapped = False
    
    for delta in [0, 1, -1, 2, -2]:
        c_d = d + pd.Timedelta(days=delta)
        c_ds = c_d.strftime("%Y-%m-%d")
        
        # Check normal
        if (c_ds, ht) in stats_lookup.index and (c_ds, at) in stats_lookup.index:
            scores_match = True
            if delta != 0:
                goals_h = stats_lookup.loc[(c_ds, ht), "goals_scored"]
                goals_a = stats_lookup.loc[(c_ds, at), "goals_scored"]
                if isinstance(goals_h, pd.Series): goals_h = goals_h.iloc[0]
                if isinstance(goals_a, pd.Series): goals_a = goals_a.iloc[0]
                if pd.isna(goals_h) or pd.isna(goals_a) or int(goals_h) != int(row["home_score"]) or int(goals_a) != int(row["away_score"]):
                    scores_match = False
            if scores_match:
                # Check stats
                row_h = stats_lookup.loc[(c_ds, ht)]
                row_a = stats_lookup.loc[(c_ds, at)]
                stats_exist = True
                for col in ["sb_shots", "sb_shots_on_target", "sb_corners", "sb_cards"]:
                    val_h = row_h[col]
                    val_a = row_a[col]
                    if isinstance(val_h, pd.Series): val_h = val_h.iloc[0]
                    if isinstance(val_a, pd.Series): val_a = val_a.iloc[0]
                    if pd.isna(val_h) or pd.isna(val_a):
                        stats_exist = False
                        break
                if stats_exist:
                    matched_delta = delta
                    matched_swapped = False
                    break
        
        # Check swapped
        if (c_ds, at) in stats_lookup.index and (c_ds, ht) in stats_lookup.index:
            scores_match = True
            if delta != 0:
                goals_h = stats_lookup.loc[(c_ds, at), "goals_scored"]
                goals_a = stats_lookup.loc[(c_ds, ht), "goals_scored"]
                if isinstance(goals_h, pd.Series): goals_h = goals_h.iloc[0]
                if isinstance(goals_a, pd.Series): goals_a = goals_a.iloc[0]
                if pd.isna(goals_h) or pd.isna(goals_a) or int(goals_h) != int(row["away_score"]) or int(goals_a) != int(row["home_score"]):
                    scores_match = False
            if scores_match:
                row_h = stats_lookup.loc[(c_ds, at)]
                row_a = stats_lookup.loc[(c_ds, ht)]
                stats_exist = True
                for col in ["sb_shots", "sb_shots_on_target", "sb_corners", "sb_cards"]:
                    val_h = row_h[col]
                    val_a = row_a[col]
                    if isinstance(val_h, pd.Series): val_h = val_h.iloc[0]
                    if isinstance(val_a, pd.Series): val_a = val_a.iloc[0]
                    if pd.isna(val_h) or pd.isna(val_a):
                        stats_exist = False
                        break
                if stats_exist:
                    matched_delta = delta
                    matched_swapped = True
                    break
                    
    info = {
        "idx": idx,
        "date": ds,
        "home_team": ht,
        "away_team": at,
        "home_score": row["home_score"],
        "away_score": row["away_score"],
        "delta": matched_delta,
        "swapped": matched_swapped,
        "row_data": row
    }
    
    if matched_swapped:
        swapped_matches.append(info)
    elif matched_delta != 0:
        shifted_matches.append(info)
    else:
        exact_matches.append(info)

print(f"Exact Matches (delta=0, swapped=False): {len(exact_matches)}")
print(f"Shifted Matches (delta!=0, swapped=False): {len(shifted_matches)}")
print(f"Swapped Matches (swapped=True): {len(swapped_matches)}")

# Count draws in shifted matches
shifted_draws = [m for m in shifted_matches if m["home_score"] == m["away_score"]]
print(f"Draws in Shifted Matches: {len(shifted_draws)}")

# Sample shifted matches (including draws and non-draws)
sample_matches = shifted_draws[:4] + [m for m in shifted_matches if m["home_score"] != m["away_score"]][:4]

print("\n================================================================================")
print("MANUAL VERIFICATION OF SHIFTED MATCHES SAMPLE")
print("================================================================================")

for i, m in enumerate(sample_matches):
    print(f"\n--- Match Sample {i+1} ---")
    is_draw = "DRAW" if m['home_score'] == m['away_score'] else "DECISIVE"
    print(f"martj42 game ({is_draw}): {m['date']} | {m['home_team']} {int(m['home_score'])}-{int(m['away_score'])} {m['away_team']}")
    
    # Find match in stats
    c_d = pd.to_datetime(m['date']) + pd.Timedelta(days=m['delta'])
    c_ds = c_d.strftime("%Y-%m-%d")
    
    # Retrieve stats row
    stats_h = stats_lookup.loc[(c_ds, m['home_team'])]
    stats_a = stats_lookup.loc[(c_ds, m['away_team'])]
    
    # Get scores in stats to verify
    goals_h = stats_h["goals_scored"]
    goals_a = stats_a["goals_scored"]
    if isinstance(goals_h, pd.Series): goals_h = goals_h.iloc[0]
    if isinstance(goals_a, pd.Series): goals_a = goals_a.iloc[0]
    
    is_home_h = stats_h["is_home"]
    if isinstance(is_home_h, pd.Series): is_home_h = is_home_h.iloc[0]
    api_home = m['home_team'] if is_home_h == 1 else m['away_team']
    api_away = m['away_team'] if is_home_h == 1 else m['home_team']
    print(f"Matched API-Football date: {c_ds} (delta={m['delta']}) | Score in Parquet: {int(goals_h)}-{int(goals_a)}")
    print(f"  API-Football Home Team: {api_home}")
    print(f"  API-Football Away Team: {api_away}")
    
    # Check if df_ap values match the team statistics
    print("\n  Comparison of values in enriched CSV vs raw stats in parquet:")
    
    metrics = [
        ("shots", "sb_shots", "home_cur_sb_shots", "away_cur_sb_shots"),
        ("corners", "sb_corners", "home_cur_sb_corners", "away_cur_sb_corners"),
        ("cards", "sb_cards", "home_cur_sb_cards", "away_cur_sb_cards"),
    ]
    
    for label, raw_col, csv_h_col, csv_a_col in metrics:
        csv_h_val = m['row_data'][csv_h_col]
        csv_a_val = m['row_data'][csv_a_col]
        
        raw_h_val = stats_h[raw_col]
        raw_a_val = stats_a[raw_col]
        if isinstance(raw_h_val, pd.Series): raw_h_val = raw_h_val.iloc[0]
        if isinstance(raw_a_val, pd.Series): raw_a_val = raw_a_val.iloc[0]
        
        print(f"    {label.upper()}:")
        print(f"      Home ({m['home_team']}): enriched CSV = {csv_h_val} | raw stats parquet = {raw_h_val}")
        print(f"      Away ({m['away_team']}): enriched CSV = {csv_a_val} | raw stats parquet = {raw_a_val}")
        
        # Verify
        assert csv_h_val == raw_h_val, f"Mismatch for home team {label}!"
        assert csv_a_val == raw_a_val, f"Mismatch for away team {label}!"
        
    print("  => VERIFIED: Statistics are correctly attributed to their respective teams!")
