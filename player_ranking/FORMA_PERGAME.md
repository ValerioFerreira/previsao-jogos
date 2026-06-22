# Forma recente por jogo (point-in-time) — frente EM ANDAMENTO

> Iniciada 2026-06-22. Documenta a coleta da **única hipótese de melhoria ortogonal ao
> Elo ainda em aberto** (ver `RELATORIO.md` §8-9): a forma recente de clube dos jogadores
> convocados, por jogo, point-in-time. Diferente do agregado-de-temporada (que FALHOU por
> ser redundante com o Elo). **Coleta em curso; teste (gate) só quando ela terminar.**

## Hipótese
A força de uma seleção num jogo não é só o Elo de longo prazo — depende de como os
jogadores **convocados** chegam: forma recente no clube (rating das últimas partidas),
**carga de minutos / fadiga**, ritmo de jogo. Esse sinal **transitório** é o que o
agregado-de-temporada (média da temporada) não captura e o que pode ser ortogonal ao Elo.

## Por que não foi feito antes
É o "caminho caro": exige dados **por jogo de clube**, point-in-time (sem leakage). O
RELATORIO estimou ~30k+ requests; medido na prática é **maior** (~317 req/jogo; ~165k no
total, ver abaixo). Só foi iniciado porque há cota diária ociosa (dezenas de milhares).

## Pipeline (isolado em `player_ranking/`, não toca produção)
1. `build_raw_index.py` — índice local das escalações dos 9.519 fixtures crus (0 req).
2. `build_targets_recent.py` — jogos-alvo de **TODAS as janelas 2023-08+** (inclui meio de
   temporada, onde forma recente diverge do agregado) + elenco-base **leakage-safe**
   (regulares dos 5 jogos internacionais anteriores). ~2.400 jogos, ~13k jogadores (0 req).
3. `collect_player_form_pergame.py` — para cada jogo (data D) e jogador do elenco-base:
   resolve o clube (via `/players`, temporada europeia de D + anterior, robusto a ligas de
   ano-calendário), pega os fixtures de clube em **[D−120d, D)** e extrai **rating+minutos**
   das últimas **K=6** partidas. Agrega por seleção: `form_rating`, `form_minutes` (carga),
   `form_games30` (fadiga), `form_trend` (momentum), `coverage`. Saída:
   `player_ranking/data/processed/pergame_form.parquet` (1 linha/jogo, com `elo_diff` e `result`).
4. **Gate (DEFERIDO até a coleta terminar):** Elo vs forma vs Elo+forma (HGB + LogReg, CV
   5-fold ×3 + temporal, log-loss/ECE) — o mesmo crivo duro do agregado.

## Escala e operação
- **Custo:** ~317 req/jogo sem cache; total limitado pelos *únicos* (cache em disco amortiza
  jogadores/clubes/fixtures compartilhados) ≈ **~165k requests ≈ 3-4 execuções diárias**.
- **Cota é por conta (a chave), compartilhada entre máquinas.** O coletor tem **teto por
  execução** (45k, margem sob a diária) e é **RESUMÁVEL**: re-rodar continua do cache, pulando
  jogos já feitos e chamadas já cacheadas. Ao bater o teto, salva e sai.
- **Resumir:** `api/.venv/Scripts/python player_ranking/src/collect_player_form_pergame.py`
  (re-rodar a cada dia até "faltam ~0"). Pode ser agendado para concluir sem intervenção.

## Caveats honestos (registrados antes de ver o resultado)
- **Cobertura bimodal:** boa para seleções com diáspora europeia; **~3% para minnows**
  (jogadores em ligas amadoras sem dado de clube na API). A feature só existe de fato nos
  jogos entre times fortes — exatamente onde o Elo já é bom.
- **Prior cético:** o agregado-de-temporada foi redundante com o Elo. A aposta aqui é que
  tendência+minutos+fadiga carreguem algo novo. **Resultado desconhecido até o gate.**

## Status
- 2026-06-22: pipeline construído e validado (1 jogo); **run 1 da coleta lançada** (teto 45k,
  resumável). Aguardando completar para rodar o gate.
