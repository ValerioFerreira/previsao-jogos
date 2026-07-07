@echo off
REM Prefetch diario dos dados de partidas da Copa do Mundo (detalhe completo -> cache Neon),
REM do mais recente ao mais antigo, respeitando o limite diario da API-Football.
REM Agendado no Task Scheduler (\PrevisaoJogos\PrefetchWorldCup).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --max 3000 --margin 50 --recent 10 >> "data\state\prefetch_wc.log" 2>&1
