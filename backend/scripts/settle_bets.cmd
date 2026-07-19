@echo off
REM Liquidacao periodica das apostas (consome/estorna credito reservado apos o jogo
REM terminar + delay de seguranca). Agendado no Task Scheduler (\PrevisaoJogos\SettleBets).
REM Sem isso, apostas ficam presas em "Aguardando inicio" para sempre e o credito nunca
REM e liberado -- bug encontrado em 2026-07-19 (cron nunca tinha sido configurado).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\settle_bets.log"
".venv\Scripts\python.exe" "scripts\settle_bets.py" >> "data\state\settle_bets.log" 2>&1
