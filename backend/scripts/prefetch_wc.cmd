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
REM --floor 2024 no run DIARIO: o historico profundo ja esta saturado e re-lista-lo todo
REM dia custava ~4.200 chamadas e estourava o tempo da tarefa. A varredura completa
REM (--floor 2010) roda semanalmente em \PrevisaoJogos\PrefetchWorldCupFull.
echo ----- prefetch Selecoes %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\prefetch_wc_data.py" --all-nations --max 74000 --margin 300 --floor 2024 >> "data\state\prefetch_wc.log" 2>&1

REM 2.5) Odds futuras de CLUBES (novo 2026-07-15, preenche a lacuna do backtest de valor --
REM ver PESQUISA_CLUBES.md Fase 8). Janela curta e barata, roda depois da coleta grande.
echo ----- odds de clubes %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\collect_club_odds_forward.py" --days 10 >> "data\state\prefetch_wc.log" 2>&1

REM 3) Lesoes: /injuries por liga+temporada, 1 chamada cobre a liga inteira (retroativo,
REM cada registro vem amarrado a um fixture_id). Temporada corrente so -- a varredura
REM historica completa e manual (--seasons 2020-2026).
echo ----- coleta injuries %DATE% %TIME% ----- >> "data\state\prefetch_wc.log"
".venv\Scripts\python.exe" "scripts\collect_injuries.py" --current-only >> "data\state\prefetch_wc.log" 2>&1

REM NOTA (2026-07-30): build_scorer_model / build_shots_prop_model / precompute_aggregates
REM SAIRAM daqui e viraram a tarefa separada \PrevisaoJogos\RebuildModels
REM (scripts\rebuild_models.cmd). Motivo: esta tarefa era morta pelo ExecutionTimeLimit
REM antes de chegar neles, e os 3 nao rodavam desde 2026-07-14. Rebuild nao pode depender
REM de coleta terminar.
