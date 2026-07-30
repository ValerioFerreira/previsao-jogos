@echo off
REM Wrapper para o Windows Task Scheduler: coleta forward de odds a cada 3h.
REM Resolve a raiz do repo a partir da pasta deste .cmd (scripts\..), garante que
REM o .env (chave APIFOOTBALL_KEY) seja encontrado e registra a saida num log.
setlocal
set "REPO=%~dp0.."
cd /d "%REPO%"
if not exist "data\odds" mkdir "data\odds"
echo ===== %DATE% %TIME% ===== >> "data\odds\collect.log"
".venv\Scripts\python.exe" "scripts\collect_odds_forward.py" --days 12 >> "data\odds\collect.log" 2>&1
REM coleta forward de odds de CLUBE (achado 2026-07-21/22: faltava aqui, so rodava manual)
".venv\Scripts\python.exe" "scripts\collect_club_odds_forward.py" --days 12 >> "data\odds\collect.log" 2>&1
REM fecha o loop: resolve os jogos que ja terminaram (barato ate haver jogos resolvidos)
".venv\Scripts\python.exe" "scripts\resolve_results.py" >> "data\odds\collect.log" 2>&1
REM backfill duravel de TODAS as odds da janela (7d passados + futuro) em odds_history.sqlite,
REM p/ acumular dataset rotulavel dos mercados novos (btts/escanteios/cartoes). Idempotente.
REM 2026-07-30: --scope ambos passa a incluir as 83 ligas de CLUBE (antes so selecao, por um
REM filtro que lia data\raw\fixtures\ -- ver docstring do script). Buffer subiu de 300 p/ 2000
REM porque o volume por execucao cresceu ~1000x; o pre-filtro de dia deixa as execucoes
REM seguintes quase gratuitas.
".venv\Scripts\python.exe" "scripts\collect_odds_backfill.py" --past 7 --future 14 --buffer 2000 --scope ambos >> "data\odds\collect.log" 2>&1
endlocal
