@echo off
REM Executa a coleta de forma-por-jogo (resumivel). Agendada para rodar diariamente
REM no primeiro minuto do dia. Loga em data/state/player_form_cron.log.
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos"
set PYTHONIOENCODING=utf-8
"C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\api\.venv\Scripts\python.exe" player_ranking\src\collect_player_form_pergame.py >> "data\state\player_form_cron.log" 2>&1
