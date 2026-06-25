@echo off
REM Coleta diaria de jogos resolvidos (Copa do Mundo) que ainda nao estao na base
REM 'matches' do Neon. Agendada no Task Scheduler (\PrevisaoJogos\CollectResolved).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\collect_resolved.log"
".venv\Scripts\python.exe" "scripts\collect_resolved.py" >> "data\state\collect_resolved.log" 2>&1
