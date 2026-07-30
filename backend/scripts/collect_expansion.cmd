@echo off
REM Coleta da expansao de competicoes (LEAGUES_EXPANSION_20260730, 67 torneios de clube).
REM Agendado no Task Scheduler (\PrevisaoJogos\CollectExpansion), diario as 14:00.
REM
REM POR QUE UMA TAREFA PROPRIA (2026-07-30):
REM A fila e de ~121 mil fixtures -- nao cabe num dia de cota. O script e cache-first e
REM resumivel, entao a tarefa roda todo dia e o backfill se completa sozinho ao longo de
REM ~3 dias. Isso importa porque a assinatura da API-Football vence em 2026-08-19.
REM
REM --margin 15000 e deliberado: a coleta de ODDS tem prioridade sobre esta. Odd e dado
REM forward e irreversivel (a API nao serve odd retroativa), enquanto historico de partida
REM continua disponivel enquanto a assinatura durar. A margem garante que a tarefa
REM CollectOdds sempre encontre cota sobrando.
REM
REM --local-only: data\MANIFEST.yaml lista club_match_detail_cache em neon_to_migrate,
REM entao os blobs novos vao so para o espelho SQLite, nao engordam o Neon.
setlocal
set "REPO=%~dp0.."
cd /d "%REPO%"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\expansion_collect.log"
".venv\Scripts\python.exe" "scripts\prefetch_clubs_parallel.py" --only-expansion --local-only --max 60000 --margin 15000 --from 2026 --to 2010 --workers 10 --rps 6.5 >> "data\state\expansion_collect.log" 2>&1
endlocal
