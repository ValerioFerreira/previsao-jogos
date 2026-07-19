import pandas as pd
import sys
sys.path.append('.')
from predictor import Predictor

def main():
    df = pd.read_csv('international_features_enriched_apifootball.csv')
    wc26 = df[(df['tournament'] == 'FIFA World Cup') & (df['date'].str[:4] == '2026')].copy()
    
    # We only care about matches that have boxscore data
    wc26 = wc26.dropna(subset=['home_cur_sb_shots', 'away_cur_sb_shots'])
    print(f"Total de jogos da Copa de 2026 com dados de stats: {len(wc26)}")
    
    p = Predictor('model_artifacts')
    
    margins = {
        'shots': 5,
        'sot': 2,
        'corners': 3,
        'cards': 1
    }
    
    hits = {'shots': 0, 'sot': 0, 'corners': 0, 'cards': 0}
    total = len(wc26)
    
    for idx, row in wc26.iterrows():
        # Actual total stats
        actual_shots = row['home_cur_sb_shots'] + row['away_cur_sb_shots']
        actual_sot = row['home_cur_sb_shots_on_target'] + row['away_cur_sb_shots_on_target']
        actual_corners = row['home_cur_sb_corners'] + row['away_cur_sb_corners']
        actual_cards = row['home_cur_sb_cards'] + row['away_cur_sb_cards']
        
        # Predictions
        res = p.predict(row['home_team'], row['away_team'], neutral=row['neutral'], tournament=row['tournament'])
        
        # Get estimates
        pred_shots = res.get('chutes', {}).get('estimativa', 0)
        pred_sot = res.get('chutes_a_gol', {}).get('estimativa', 0)
        pred_corners = res.get('escanteios', {}).get('estimativa', 0)
        pred_cards = res.get('cartoes', {}).get('estimativa', 0)
        
        # Evaluate
        if pred_shots - margins['shots'] <= actual_shots <= pred_shots + margins['shots']:
            hits['shots'] += 1
            
        if pred_sot - margins['sot'] <= actual_sot <= pred_sot + margins['sot']:
            hits['sot'] += 1
            
        if pred_corners - margins['corners'] <= actual_corners <= pred_corners + margins['corners']:
            hits['corners'] += 1
            
        if pred_cards - margins['cards'] <= actual_cards <= pred_cards + margins['cards']:
            hits['cards'] += 1
            
    print("Resultados:")
    for k in hits:
        pct = (hits[k] / total) * 100
        print(f"{k}: {hits[k]}/{total} = {pct:.2f}% de acerto")

if __name__ == '__main__':
    main()
