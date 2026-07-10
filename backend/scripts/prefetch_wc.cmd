@echo off
REM Prefetch diario dos dados de partidas da Copa do Mundo (detalhe completo -> cache Neon),
REM do mais recente ao mais antigo, respeitando o limite diario da API-Football.
REM Agendado no Task Scheduler (\PrevisaoJogos\PrefetchWorldCup).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --all-nations --max 40000 --margin 100 --floor 2010 >> "data\state\prefetch_wc.log" 2>&1
REM Reconstroi os modelos de jogador (goleador + finalizacoes) com os dados recem-baixados.
echo ----- rebuild scorer model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_scorer_model.py" >> "data\state\prefetch_wc.log" 2>&1
echo ----- rebuild shots-prop model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_shots_prop_model.py" >> "data\state\prefetch_wc.log" 2>&1
REM Cota OCIOSA -> comeca a baixar a Serie A (proxima adicao), em tabela separada.
REM O prefetch de selecoes ja saturou; isto exaure a cota restante com proposito.
echo ----- prefetch Serie A %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_serie_a.py" --max 60000 --margin 150 --from 2026 --to 2015 >> "data\state\prefetch_wc.log" 2>&1
