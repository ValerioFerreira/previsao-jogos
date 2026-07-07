@echo off
REM Prefetch diario dos dados de partidas da Copa do Mundo (detalhe completo -> cache Neon),
REM do mais recente ao mais antigo, respeitando o limite diario da API-Football.
REM Agendado no Task Scheduler (\PrevisaoJogos\PrefetchWorldCup).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --max 20000 --margin 100 --floor 2010 >> "data\state\prefetch_wc.log" 2>&1
REM Reconstroi o modelo de goleador com os dados recem-baixados (estado por jogador atualizado).
echo ----- rebuild scorer model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_scorer_model.py" >> "data\state\prefetch_wc.log" 2>&1
