import shutil
import os
from pathlib import Path

def promote():
    src_dir = Path("api/model_artifacts_apifootball")
    dst_dir = Path("api/model_artifacts")
    
    files_to_copy = [
        "clf_btts.joblib",
        "clf_over25.joblib",
        "clf_result.joblib",
        "quantile_models.joblib",
        "meta.json",
        "results_slim.csv"
    ]
    
    print("================================================================================")
    print("PROMOVENDO MODELOS E METADADOS DA API-FOOTBALL PARA PRODUÇÃO")
    print("================================================================================")
    
    for filename in files_to_copy:
        src = src_dir / filename
        dst = dst_dir / filename
        
        if not src.exists():
            print(f"[ERRO] Arquivo de origem não encontrado: {src}")
            return
            
        shutil.copy2(src, dst)
        print(f"  - Copiado: {filename} ({src.stat().st_size} bytes)")
        
    print("\n>> Promoção concluída com sucesso! Todos os arquivos foram unificados em api/model_artifacts/")
    print(f"   Arquivos na pasta de produção: {len(os.listdir(dst_dir))}")

if __name__ == "__main__":
    promote()
