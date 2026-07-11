@echo off
REM Prefetch diario dos dados de partidas da Copa do Mundo (detalhe completo -> cache Neon),
REM do mais recente ao mais antigo, respeitando o limite diario da API-Football.
REM Agendado no Task Scheduler (\PrevisaoJogos\PrefetchWorldCup).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\prefetch_wc.log"
echo Coleta WC + Clubes com margem otimizada para usar 75k/dia >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --all-nations --max 70000 --margin 1000 --floor 2010 >> "data\state\prefetch_wc.log" 2>&1
REM Reconstroi os modelos de jogador (goleador + finalizacoes) com os dados recem-baixados.
echo ----- rebuild scorer model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_scorer_model.py" >> "data\state\prefetch_wc.log" 2>&1
echo ----- rebuild shots-prop model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_shots_prop_model.py" >> "data\state\prefetch_wc.log" 2>&1
REM Precompute dos agregados (arbitro/minutagem/quadrantes) -> tabelas pequenas no Neon.
REM Le o bruto do espelho LOCAL; o site passa a ler bytes em vez de escanear ~44 MB.
echo ----- precompute agregados %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\precompute_aggregates.py" >> "data\state\prefetch_wc.log" 2>&1
REM Cota OCIOSA -> baixa os CLUBES (proxima adicao), em tabela separada, na ordem de
REM prioridade Brasil->Europa. As selecoes ja saturaram; isto exaure a cota com proposito.
REM OTIMIZADO: --max 65000 --margin 1000 para garantir uso de ~75k/dia completo
echo ----- prefetch Clubes %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_clubs.py" --max 65000 --margin 1000 --from 2026 --to 2015 >> "data\state\prefetch_wc.log" 2>&1
