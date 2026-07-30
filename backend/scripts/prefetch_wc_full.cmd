@echo off
REM Varredura COMPLETA do historico de selecoes (2010 em diante).
REM Agendado no Task Scheduler (\PrevisaoJogos\PrefetchWorldCupFull), semanal (domingo 03:00).
REM
REM O run diario (prefetch_wc.cmd) usa --floor 2024 para nao gastar ~4.200 chamadas
REM re-listando temporadas antigas ja saturadas. Este aqui fecha a lacuna uma vez por
REM semana. Com o estado em data\state\wc_seasons_done.json, mesmo esta varredura fica
REM barata depois da primeira passada.
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== FULL %DATE% %TIME% ===== >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --all-nations --max 74000 --margin 300 --floor 2010 >> "data\state\prefetch_wc.log" 2>&1
