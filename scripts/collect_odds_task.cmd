@echo off
REM Wrapper para o Windows Task Scheduler: coleta forward de odds a cada 3h.
REM Resolve a raiz do repo a partir da pasta deste .cmd (scripts\..), garante que
REM o .env (chave APIFOOTBALL_KEY) seja encontrado e registra a saida num log.
setlocal
set "REPO=%~dp0.."
cd /d "%REPO%"
if not exist "data\odds" mkdir "data\odds"
echo ===== %DATE% %TIME% ===== >> "data\odds\collect.log"
"api\.venv\Scripts\python.exe" "scripts\collect_odds_forward.py" --days 12 >> "data\odds\collect.log" 2>&1
REM fecha o loop: resolve os jogos que ja terminaram (barato ate haver jogos resolvidos)
"api\.venv\Scripts\python.exe" "scripts\resolve_results.py" >> "data\odds\collect.log" 2>&1
endlocal
