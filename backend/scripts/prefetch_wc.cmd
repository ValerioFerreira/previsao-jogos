@echo off
REM Prefetch diario dos dados de partidas (clubes + selecoes), respeitando o limite
REM diario da API-Football. Agendado no Task Scheduler (\PrevisaoJogos\PrefetchWorldCup).
REM
REM ORDEM (2026-07-14): CLUBES primeiro. Selecoes ja saturou (~24k jogos, so entram
REM poucas dezenas por dia de jogos novos reais) e sempre para sozinha via "FIM (tudo
REM coberto)" bem antes do limite diario -- rodar depois dela nao tira cota de ninguem.
REM Clubes e a frente ativa (Brasil->Europa, backlog grande) e a prioridade do momento,
REM entao ela roda primeiro e pega a fatia grande da cota diaria (~75k).
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\prefetch_wc.log"
echo Coleta Clubes + Selecoes com margem otimizada para usar 75k/dia >> "data\state\prefetch_wc.log"

REM 1) CLUBES (prioridade atual): Brasil->Europa, do mais recente ao mais antigo, cache-first.
echo ----- prefetch Clubes %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_clubs.py" --max 72000 --margin 500 --from 2026 --to 2010 >> "data\state\prefetch_wc.log" 2>&1

REM 2) Selecoes: so falta pegar jogos novos reais (~poucas dezenas/dia); usa o que sobrar.
echo ----- prefetch Selecoes %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --all-nations --max 74000 --margin 300 --floor 2010 >> "data\state\prefetch_wc.log" 2>&1

REM 3) Reconstroi os modelos de jogador (goleador + finalizacoes) com os dados de SELECOES.
echo ----- rebuild scorer model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_scorer_model.py" >> "data\state\prefetch_wc.log" 2>&1
echo ----- rebuild shots-prop model %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\build_shots_prop_model.py" >> "data\state\prefetch_wc.log" 2>&1

REM 4) Precompute dos agregados (arbitro/minutagem/quadrantes) -> tabelas pequenas no Neon.
REM Le o bruto do espelho LOCAL; o site passa a ler bytes em vez de escanear ~44 MB.
echo ----- precompute agregados %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\precompute_aggregates.py" >> "data\state\prefetch_wc.log" 2>&1
