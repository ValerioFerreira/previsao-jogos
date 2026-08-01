# Investigação cartões 2º tempo (clube) — Fase 1, PLANO 8

Data: 2026-07-31. Mercado `cartoes_2t`, `scope="clube"`. Estado de entrada (gate original,
`gate_mercados/cartoes_2t_clube.json`): **REPROVADO** — 0/5 folds melhoram, delta_ll médio
+0,01608 (pior candidato dos 4 mercados de cartão), tail_ece candidato 0,0239 vs baseline 0,0111
(2,15x pior), coverage80 0,8545 (teto 0,85), N=147.378. Follow-up já rodado
(`cartoes_2t_clube_calibracao.json`): calibração isotônica isolada não resolve (0/5 folds bate
baseline calibrado).

Todos os experimentos novos desta sessão: seed fixa `20260731`, CV temporal (`temporal_folds`,
5 folds expanding, idêntico ao gate oficial), candidato = `CornersNB` (mesma arquitetura de
produção), baselines B0/B1/B2 reaproveitados de `scripts/gate_count_market.py` (import direto, não
reimplementado). Scripts e CSVs/JSONs brutos em
`backend/data/reports/investigacao_multiagente/_cartoes_2t_scratch/` (checkout principal — dados
locais só existem lá; este worktree é isolado e sem os parquets/sqlite).

## 1. Parecer do Crítico (síntese de `cluster_a.md` + `cluster_b.md` + `..._calibracao.json`)

`cluster_a.md` (comum aos 4 mercados de cartão) já **CONFIRMOU**: (a) o candidato de produção não
usa NENHUMA feature de histórico do próprio alvo (`base_feats_170` não tem coluna "card"/"yellow"/
"red"; a única disciplinar é `style_fouls_suff_ratio`, e é justamente o único mercado disciplinar
que passa o gate — `faltas`, 5/5 folds); (b) nenhuma identidade de competição/liga (só
`tournament_weight`), com R²≈9% explicado por uma simples média-por-liga, que bate o candidato em
19/20 folds nos 4 mercados; (c) calibração isotônica isolada não resolve (testada 3x, inclusive
aqui). `cluster_b.md` (mesmo cluster de investigação, sobre gols_1t/gols_2t/impedimentos — não
cartões, mas o mecanismo é transferível) mostrou que coverage80 tem **teto estrutural** para
mu_total baixo (a métrica mede intervalo central de 80% sobre PMF discreta com poucos bins, e
transborda o alvo [0,75; 0,85] por construção quando mu é baixo) e levantou, como hipótese
**Inconclusiva** (sem dado disponível naquele worktree), que o `tail_ece` residual de `gols_2t`
poderia vir de estado de jogo pós-1T não capturado pela arquitetura (features só pré-jogo).
`cluster_a.md §2` registrou que `cartoes_2t` é, junto com `cartoes_amarelos`, o pior dos 4 (maior
teto de ganho esperado ao corrigir a feature ausente, pela mesma ordem de grandeza de correlação
r=0,239 do rolling de cartão ignorado). Não repeti nenhum teste já feito por essas duas
investigações — as hipóteses abaixo (H1/H2) operacionalizam exatamente as recomendações #1
(rolling+liga) e #5/#priority-transferida (estado pós-1T) de `cluster_a.md`/`cluster_b.md` §6,
aplicadas especificamente a `cartoes_2t`.

## 2. Hipótese H1 (Proponente de Dados) — rolling de cartão + identidade de liga

**Motivação**: `cluster_a.md` recomenda, na ordem de prioridade #1, adicionar
`home/away_sb_cards_l5` (rolling do próprio alvo, r=0,239 com o alvo real, ~3x mais forte que a
melhor das 170 features de produção) e, #2, target-encoding de `tournament` com shrinkage — e
sugere testar os dois juntos primeiro por serem fontes de variância distintas (time vs liga).
`cartoes_2t` foi apontado como um dos dois mercados de maior teto de ganho esperado.

**Experimento**: candidato = `base_feats_170` + `{home_sb_cards_l5, away_sb_cards_l5,
diff_sb_cards_l5}` (rolling do jogo INTEIRO — não existe variante rolling específica de 2T no
parquet, limitação já registrada por `cluster_a.md §2`, usada aqui como proxy e reportada) +
`_tournament_te` (média por competição com shrinkage bayesiano, `m=50` pseudo-jogos, ajustada
SÓ no treino de cada fold, sem vazamento cronológico).

**Resultado** (`_cartoes_2t_scratch/cartoes_2t_h1.{json,csv}`):

| métrica | gate original | H1 |
|---|---|---|
| folds que melhoram | 0/5 | **4/5** |
| delta_ll médio | +0,01608 | **−0,00259** |
| tail_ece candidato | 0,0239 | 0,0135 |
| tail_ece baseline | 0,0111 | 0,0111 |
| coverage80 | 0,8545 | 0,8692 |
| critério (folds/delta/tail_ece/coverage) | F/F/F/F | **V/V**/F/F |

Ganho real e grande em ajuste (delta_ll e folds passam a bater o critério do gate), mas tail_ece
segue pior que o baseline (0,0135 vs 0,0111) e coverage80 segue acima do teto (0,8692 > 0,85) —
**REPROVADO ainda**, porém 2 dos 4 critérios viram de reprovado para aprovado.

**Controle negativo**: mesma receita, mas as 3 colunas de rolling embaralhadas entre linhas
(`h1_control`, `_tournament_te` mantido REAL — isola a contribuição do rolling). Resultado:
3/5 folds, delta_ll médio −0,00103 (menos da metade do ganho de H1), tail_ece 0,0147, coverage
0,868. O ganho de H1 não desaparece completamente no controle (a TE de liga sozinha já contribui
algo — consistente com R²≈9% do `cluster_a.md`), mas o ganho **quase dobra** quando o rolling é
real vs embaralhado (delta −0,00259 vs −0,00103) e o critério `folds_ok` só passa com o rolling
real (4/5 vs 3/5). Isso descarta a hipótese alternativa "o ganho é só de ter mais colunas
numéricas" — o rolling do próprio alvo carrega sinal causal genuíno, como previsto.

**Classificação: Provável** — sinal real e validado por controle negativo, mecanismo consistente
com `cluster_a.md`, mas insuficiente sozinho para aprovar no gate.

## 3. Hipótese H2 (Proponente de Arquitetura) — estado de jogo pós-1T como feature condicional

**Motivação**: hipótese transferida de `cluster_b.md §5` (gols_2t): times mudam postura tática após
saberem o placar do 1º tempo — cartão no 2T por frustração/retaliação pode ser um sinal que só
existe DENTRO do jogo, não capturável por features pré-jogo. `club_halftime_targets.parquet` tem
`home/away_goals_1t` e `home/away_cards_1t` disponíveis por `fixture_id` (dado point-in-time
legítimo para um candidato que já "sabe" o 1T — implica reformular o mercado como condicional/
intervalo, não puramente pré-jogo, ver nota de produto abaixo).

**Experimento**: candidato = `base_feats_170` + `{home_goals_1t, away_goals_1t, home_cards_1t,
away_cards_1t}` (SEM as features de H1 — teste isolado da hipótese de arquitetura). Mesmo
`CornersNB`, mesmo protocolo.

**Resultado** (`_cartoes_2t_scratch/cartoes_2t_h2.json`): **0/5 folds** melhoram, delta_ll médio
**+0,01134** (pior que baseline, embora um pouco menos pior que o gate original +0,01608),
tail_ece candidato **0,0246** (PIOR que o próprio gate original 0,0239), coverage80 0,8564.
Todos os 4 critérios falham — nenhuma melhora em nenhuma dimensão relativa ao gate original.

**Controle negativo**: não aplicável/não executado — não há ganho a validar (resultado já é nulo
ou negativo em toda métrica; a regra do PLANO 8 exige controle só para GANHOS).

**Classificação: Refutada.** Diferente do que `cluster_b.md` levantou (Inconclusiva, sem dado) para
`gols_2t`, aqui HOUVE dado disponível e o teste foi possível: adicionar placar e cartões do 1T como
covariáveis a um `CornersNB` (GBM raso, profundidade 3 — capaz de capturar interações de baixa
ordem como "time perdendo no intervalo toma mais cartão no 2T") não gerou nenhuma melhora
detectável, e piorou levemente o tail_ece. Isso é evidência CONTRA a hipótese específica de que o
estado de jogo pós-1T seja um driver relevante do erro de `cartoes_2t` — pelo menos na forma de
injeção ingênua de covariável testada aqui (uma arquitetura genuinamente condicional/2-estágios
não foi testada e não pode ser descartada pela mesma evidência, mas o sinal não apareceu nem como
covariável simples, o que reduz a plausibilidade de um efeito forte).

**Nota de produto** (não é achado de modelo, é implicação de escopo): usar placar/cartões do 1T
como feature muda o mercado de "pré-jogo" para "ao vivo/meio-tempo" — mesmo que a arquitetura
funcionasse, promover isso mudaria o que o mercado representa (quando a previsão fica disponível
ao usuário). Registrado para quem decidir se vale a pena perseguir essa direção depois.

## 4. Parecer do Auditor de Métricas — coverage80 estrutural vs tail_ece real

Replicei o método de `cluster_b.md §2` (simulação "modelo perfeitamente especificado": gera dados
sintéticos a partir dos PRÓPRIOS `r_H_`/`r_A_`/lambda do artefato `cartoes_2t_nb.joblib`, mede
coverage80 e tail_ece desse processo contra seu próprio PMF) — mas com os `r` REAIS e assimétricos
do artefato de cartões (`cluster_b` usava um grid simétrico genérico) e adicionei a mesma checagem
para tail_ece, que `cluster_b` não tinha feito.

`r_H_=41,58`, `r_A_=677,77` (via `SimpleImputer` já fitado, `X` todo NaN → "jogo mediano"),
λ_home=1,4953, λ_away=1,7200, mu_total≈3,215 (script:
`_cartoes_2t_scratch/sim_coverage_cartoes2t.py`, seed 20260731, N=300.000):

| métrica | teórico (modelo perfeito) | REAL (gate, candidato original) |
|---|---|---|
| coverage80 | **0,9119** | 0,8545 |
| tail_ece | **0,00151** | 0,0239 (baseline: 0,0111) |

**coverage80**: mesmo um modelo PERFEITAMENTE especificado (dado gerado pela mesma NB que o PMF
assume) erra o alvo [0,75; 0,85] por 0,0619 pra cima — o teto estrutural do `cluster_b.md` (mu_total
baixo → poucos bins com massa relevante, 9 no total aqui) se confirma pra cartões também.
Curiosamente, o valor REAL do gate (0,8545) fica ABAIXO do teórico de jogo mediano (0,9119, gap
−0,0574) em vez de igual/acima — isso é esperado: a simulação usa um único λ fixo (o jogo mediano),
enquanto o candidato real tem λ variando jogo a jogo (heterogeneidade populacional), o que
tipicamente ALARGA a cobertura empírica agregada pra baixo do teto de um mu único. Isso é
**consistente com o padrão de `cluster_b.md`** (mu_total∈[2,5; 5,0]: coverage80 alcançável só em
pontos estreitos e frágeis de r) — 0,8545 está bem dentro dessa faixa "frágil", nem no não-alcançável
completo (mu<2) nem no regime confortável (mu>7). **Conclusão: a falha de coverage80 é
predominantemente estrutural/métrica**, não um defeito de ajuste do candidato — reforça a
recomendação de `cluster_b.md §6` de revisar o critério §6-C pra mercados de contagem baixa.

**tail_ece**: aqui a resposta é DIFERENTE do padrão de `cluster_b` para gols_2t. O teórico do
modelo perfeitamente especificado é **0,00151** — quase zero, como esperado (o gerador é o mesmo
processo que o PMF assume, então a calibração da linha central tem que ser quase perfeita por
construção). O candidato REAL do gate erra **0,0239**, 16x o teórico, e pior até que o MELHOR
baseline (0,0111, 7x o teórico). **Isso descarta a hipótese de que o tail_ece ruim seja artefato
de discretização/estrutura da métrica** — ao contrário de coverage80, tail_ece não tem o mesmo viés
estrutural pra cima (o teórico é baixíssimo). O defeito é real, de ajuste/calibração do candidato,
não da métrica. Isso é consistente com o resultado de H1 (§2): quando o ajuste é corrigido
(rolling+liga), tail_ece cai de 0,0239 pra 0,0135 — quase fecha a distância até o baseline (0,0111),
mas não fecha de todo. Ou seja: a MAIOR parte do tail_ece ruim tem a MESMA causa raiz que
delta_ll/folds (feature ausente, `cluster_a.md`), não uma causa separada de estado de jogo (H2,
refutada) nem um artefato de métrica (só coverage80 é estrutural, tail_ece não é).

## 5. Síntese — convergências e divergências

- **Convergência com `cluster_a.md`**: CONFIRMADA de novo, agora com experimento real (não só
  correlação): a falta de rolling de cartão + identidade de liga é a causa dominante do mau ajuste
  de `cartoes_2t` — corrigi-la resolve 2 dos 4 critérios do gate (folds_ok, delta_ok) e reduz o
  tail_ece em 44% (0,0239→0,0135), validado por controle negativo.
- **Divergência parcial de `cluster_b.md`**: a hipótese de estado-de-jogo-pós-1T, plausível por
  analogia com gols_2t, foi **testável aqui** (ao contrário de `gols_2t`, onde ficou Inconclusiva
  por falta de dado) e **refutada** para cartões — placar/cartões do 1T como covariável não ajudou
  em nada, piorou tail_ece. O "problema duplo" que este agente foi instruído a investigar
  (feature ausente + split fixo/dependência intra-jogo) acabou sendo, na prática, **um problema
  dominante só** (feature ausente) — o componente de dependência intra-jogo não se confirmou como
  driver adicional relevante, pelo menos na forma testada.
- **Coverage80 é estrutural** (mesma conclusão de `cluster_b.md` para gols_1t/gols_2t, agora
  confirmada também para cartões com os r/mu reais do artefato) — não é alcançável com recalibração
  de modelo, é limite da métrica na contagem baixa (mu≈3,2).
- **tail_ece NÃO é estrutural** (achado novo desta investigação, não estava em `cluster_b.md`) — é
  defeito real de ajuste, majoritariamente fechado (não 100%) pela mesma correção de dados de H1.

## 6. Recomendação final

**Investigar novamente.**

Justificativa: H1 (Provável, validada por controle negativo) já entrega a maior parte do ganho
possível por dados — resta um experimento barato e não feito ainda: reaplicar a checagem de
calibração isotônica (`--calibration-check`) SOBRE o candidato já corrigido por H1, não sobre o cru
(regra de `cluster_a.md §3`: "só reaplicar calibração DEPOIS que dados melhorarem o ajuste cru" —
essa condição agora está satisfeita e não foi testada nesta sessão por orçamento de tempo). Se essa
calibração fechar o tail_ece residual (0,0135 vs 0,0111, gap pequeno), o único obstáculo restante
seria coverage80 — que o Auditor mostrou ser estrutural, então dependeria de uma decisão de dono
sobre o critério §6-C (mesma pendência mais ampla já registrada em `cluster_b.md §6`, não específica
deste mercado). H2 (arquitetura de estado de jogo) está fechada/Refutada — não vale reabrir sem uma
arquitetura genuinamente condicional (2 estágios), que é um investimento maior e não tem evidência
de sinal suficiente pra justificar agora.

**Próximos passos concretos para quem retomar:**
1. Rodar `--calibration-check` isotônico sobre o candidato H1 (rolling+TE) — não feito aqui por
   orçamento; é o experimento mais barato e a lacuna mais óbvia deixada.
2. Se (1) não fechar tail_ece: considerar Beta-Binomial/Empirical Bayes por time em vez de rolling
   simples (mesma sugestão de `cluster_a.md §3` item 6, originalmente pra vermelhos, mas aplicável
   aqui pelo mesmo racional de suavização).
3. Levar a decisão de coverage80-estrutural para o dono como parte da revisão mais ampla do gate
   §6-C já sinalizada por `cluster_b.md §6` (não abrir uma decisão isolada só para `cartoes_2t`).
4. Se promovido eventualmente, propagar a mesma receita de dados (rolling do próprio alvo + TE de
   liga) para `cartoes_amarelos` (apontado por `cluster_a.md` como o outro mercado de maior teto de
   ganho, mesma ordem de grandeza de correlação).

## 7. Arquivos gerados nesta investigação

Todos em `backend/data/reports/investigacao_multiagente/_cartoes_2t_scratch/` (checkout principal):
- `sim_coverage_cartoes2t.py` / `resultado_coverage_sim.json` — simulação do Auditor (§4).
- `run_variants.py` — script único reaproveitado para H1/H1_control/H2 (import direto de
  `scripts/gate_count_market.py`, sem reimplementar baseline/candidato/métrica).
- `cartoes_2t_h1.{json,csv}`, `cartoes_2t_h1_control.{json,csv}`, `cartoes_2t_h2.{json,csv}` —
  resultados por fold de cada variante (§2, §3).

Nenhum artefato de produção (`model_artifacts_clubes/`), nenhum CSV/JSON oficial do gate em
`gate_mercados/`, nenhum `predictor.py`/frontend foi tocado. Nenhuma chamada à API-Football.
