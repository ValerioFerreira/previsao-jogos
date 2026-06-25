import sys
import json
import pandas as pd
from pathlib import Path

# Add api directory to sys.path
sys.path.append(str(Path("api").resolve()))
from dixon_coles_model import DixonColesNBRegressor

def train():
    csv_path = Path("international_features_enriched_apifootball.csv")
    meta_path = Path("api/model_artifacts_apifootball/meta.json")
    
    if not csv_path.exists():
        print(f"[ERRO] {csv_path} não encontrado.")
        return
        
    # Load dataset
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # Load feature lists from APIFootball meta.json
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    base_feats = meta["base_feats"]
    
    print(f">> Dataset APIFootball carregado: {len(df)} jogos")
    print(f">> Features base para treinamento: {len(base_feats)}")
    
    # Fit model on the entire dataset
    dc_model = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    dc_model.fit(df[base_feats], df["home_score"], df["away_score"])
    
    # Save directly to production artifacts path
    out_path = Path("api/model_artifacts/dixon_coles_goals.joblib")
    dc_model.save(out_path)
    print(f">> Modelo Dixon-Coles treinado na base da API e salvo com sucesso em: {out_path}")

if __name__ == "__main__":
    train()
