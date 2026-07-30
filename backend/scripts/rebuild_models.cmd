@echo off
REM Rebuild dos modelos de jogador + precompute dos agregados.
REM Agendado no Task Scheduler (\PrevisaoJogos\RebuildModels), diario as 12:00.
REM
REM POR QUE ISTO E UMA TAREFA SEPARADA (2026-07-30):
REM Estes 3 passos viviam no fim do prefetch_wc.cmd. Como a tarefa PrefetchWorldCup tinha
REM ExecutionTimeLimit=PT3H e o prefetch_wc_data.py --all-nations passou a estourar esse
REM limite, a tarefa era morta ANTES de chegar aqui -- e os 3 passos nao rodavam desde
REM 2026-07-14 (16 dias). Rebuild nao pode depender de coleta terminar: le so o espelho
REM LOCAL, nao gasta cota de API e leva poucos minutos.
cd /d "C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend"
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% ===== >> "data\state\rebuild_models.log"

REM 1) Modelos de prop de jogador (goleador + finalizacoes), a partir de SELECOES.
echo ----- rebuild scorer model %DATE% %TIME% ----- >> "data\state\rebuild_models.log"
".venv\Scripts\python.exe" "scripts\build_scorer_model.py" >> "data\state\rebuild_models.log" 2>&1
echo ----- rebuild shots-prop model %DATE% %TIME% ----- >> "data\state\rebuild_models.log"
".venv\Scripts\python.exe" "scripts\build_shots_prop_model.py" >> "data\state\rebuild_models.log" 2>&1

REM 2) Precompute dos agregados (arbitro/minutagem/quadrantes) -> tabelas pequenas no Neon.
REM Le o bruto do espelho LOCAL; o site passa a ler bytes em vez de escanear ~44 MB.
echo ----- precompute agregados %DATE% %TIME% ----- >> "data\state\rebuild_models.log"
".venv\Scripts\python.exe" "scripts\precompute_aggregates.py" >> "data\state\rebuild_models.log" 2>&1

echo ----- FIM %DATE% %TIME% ----- >> "data\state\rebuild_models.log"
