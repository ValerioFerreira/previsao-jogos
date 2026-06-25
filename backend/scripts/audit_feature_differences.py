import pandas as pd
import numpy as np
from pathlib import Path

def audit():
    old_path = Path("api/international_features_enriched.csv")
    new_path = Path("international_features_enriched_apifootball.csv")
    report_path = Path(r"C:\Users\10341953440\.gemini\antigravity\brain\38bd63cd-c1e9-4756-9d77-8346dce6bac3\audit_report.md")
    
    if not old_path.exists() or not new_path.exists():
        print("Erro: Um dos datasets está ausente.")
        return
        
    df_old = pd.read_csv(old_path)
    df_new = pd.read_csv(new_path)
    
    # 1. Verificar diferenças de colunas
    cols_old = set(df_old.columns)
    cols_new = set(df_new.columns)
    
    only_old = cols_old - cols_new
    only_new = cols_new - cols_old
    common = cols_old & cols_new
    
    # 2. Comparar distribuições de colunas numéricas comuns
    mismatches = []
    
    exclude = {
        "match_id", "date", "home_team", "away_team", "city", "country", "tournament",
        "home_score", "away_score", "goal_diff", "total_goals", "result",
        "home_win", "away_win", "draw", "btts", "over_2_5",
        "has_advanced_stats", "year", "month", "decade", "goals_for", "goals_against"
    }
    
    numeric_cols = []
    for col in sorted(list(common)):
        if col in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df_old[col]) and pd.api.types.is_numeric_dtype(df_new[col]):
            numeric_cols.append(col)
            
    for col in numeric_cols:
        mean_old = df_old[col].mean()
        mean_new = df_new[col].mean()
        min_old = df_old[col].min()
        min_new = df_new[col].min()
        max_old = df_old[col].max()
        max_new = df_new[col].max()
        
        nans_old = df_old[col].isna().sum() / len(df_old)
        nans_new = df_new[col].isna().sum() / len(df_new)
        
        mean_diff = abs(mean_old - mean_new)
        min_diff = abs(min_old - min_new)
        max_diff = abs(max_old - max_new)
        nan_diff = abs(nans_old - nans_new)
        
        # Flag if there is a non-trivial difference
        if mean_diff > 0.001 or min_diff > 0.01 or max_diff > 0.01 or nan_diff > 0.01:
            mismatches.append({
                "feature": col,
                "mean_old": mean_old, "mean_new": mean_new, "mean_diff": mean_diff,
                "min_old": min_old, "min_new": min_new, "min_diff": min_diff,
                "max_old": max_old, "max_new": max_new, "max_diff": max_diff,
                "nans_old": nans_old, "nans_new": nans_new, "nan_diff": nan_diff
            })
            
    # Sort mismatches by mean difference descending, then by nan difference
    mismatches.sort(key=lambda x: (x["mean_diff"], x["nan_diff"]), reverse=True)
    
    # Generate Markdown Report
    lines = []
    lines.append("# Relatório de Auditoria de Features (Dataset Antigo vs Novo)")
    lines.append(f"\n- **Dataset Antigo (Produção):** {len(df_old)} linhas, {len(df_old.columns)} colunas")
    lines.append(f"- **Dataset Novo (APIFootball):** {len(df_new)} linhas, {len(df_new.columns)} colunas")
    
    if only_old:
        lines.append(f"\n### Colunas APENAS no Dataset Antigo ({len(only_old)}):")
        lines.append("```python")
        lines.append(str(sorted(list(only_old))))
        lines.append("```")
    if only_new:
        lines.append(f"\n### Colunas APENAS no Dataset Novo ({len(only_new)}):")
        lines.append("```python")
        lines.append(str(sorted(list(only_new))))
        lines.append("```")
        
    lines.append(f"\n### Mismatches de Features Comuns ({len(mismatches)} colunas com diferenças):")
    lines.append("\n| Feature | Métrica | Antigo (Produção) | Novo (APIFootball) | Diferença Absoluta | Status |")
    lines.append("|---|---|---|---|---|---|")
    
    for m in mismatches:
        col = m["feature"]
        status = "⚠️ Diferença" if m["mean_diff"] > 0.05 or m["nan_diff"] > 0.1 else "✅ Aceitável"
        if "shootout_winrate" in col:
            status = "🚨 CRÍTICO"
            
        lines.append(f"| `{col}` | Média | {m['mean_old']:.6f} | {m['mean_new']:.6f} | {m['mean_diff']:.6f} | {status} |")
        lines.append(f"| | Mín | {m['min_old']:.6f} | {m['min_new']:.6f} | {m['min_diff']:.6f} | |")
        lines.append(f"| | Máx | {m['max_old']:.6f} | {m['max_new']:.6f} | {m['max_diff']:.6f} | |")
        lines.append(f"| | NaNs | {m['nans_old']*100:.2f}% | {m['nans_new']*100:.2f}% | {m['nan_diff']*100:.2f}% | |")
        lines.append("|---|---|---|---|---|---|")
        
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f">> Relatório completo salvo em: {report_path}")
    print(f">> Resumo: Comparadas {len(numeric_cols)} colunas comuns. {len(mismatches)} apresentaram alguma diferença.")
    
    print("\nTOP 10 FEATURES COM MAIORES DIFERENÇAS DE MÉDIA:")
    print("="*80)
    for m in mismatches[:10]:
        print(f"  {m['feature']:<30} | Antigo Mean={m['mean_old']:.4f} | Novo Mean={m['mean_new']:.4f} | Diff={m['mean_diff']:.4f}")
        
    print("\nTOP 5 FEATURES COM MAIORES DIFERENÇAS DE NaNs %:")
    print("="*80)
    nan_sorted = sorted(mismatches, key=lambda x: x["nan_diff"], reverse=True)
    for m in nan_sorted[:5]:
        print(f"  {m['feature']:<30} | Antigo NaNs={m['nans_old']*100:.2f}% | Novo NaNs={m['nans_new']*100:.2f}% | Diff={m['nan_diff']*100:.2f}%")

if __name__ == "__main__":
    audit()
