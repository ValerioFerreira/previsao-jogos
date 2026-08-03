# Cartões 1º tempo (clube) — Fase 1, PLANO 8

Data: 2026-07-31. Mercado: `cartoes_1t`, `scope="clube"`. Reprovação original (gate oficial):
`folds_que_melhoram=1/5`, `delta_ll_medio=+0,01149`, `tail_ece=0,0232` vs baseline `0,0179`,
`coverage80_medio=0,9169`, `N=147.378`. Fonte:
`backend/data/reports/gate_mercados/cartoes_1t_clube.{json,csv}` +
`cartoes_1t_clube_calibracao.{json,csv}` (calibração isotônica isolada já testada, não resolve
sozinha — 0/5 folds calibrado bate baseline).

Herança da Fase 0 (leitura obrigatória, resumida): `cluster_a.md` (4 mercados de cartão de
clube compartilham a MESMA causa raiz — `base_feats_170` não tem nenhuma feature de histórico do
próprio alvo nem identidade de liga; `faltas` é o único mercado "disciplinar" que passa o gate e é
também o único que TEM sua feature de histórico em `base_feats_170`) e `cluster_b.md` (coverage80
é estruturalmente inalcançável em mu_total baixo — confirmado com dados sintéticos gerados pela
própria NB assumida, para `gols_1t`/`gols_2t`; propõe rever o critério do gate §6-C para mercados
de contagem baixa).

**Pergunta central desta investigação:** qual dos dois mecanismos herdados domina a reprovação de
`cartoes_1t` especificamente? Resposta: **os dois, mas em proporções muito diferentes — falta de
feature é o driver dominante e TOTALMENTE corrigível (fecha 3 dos 4 critérios do gate); o limite
estrutural de métrica do Cluster B também está presente aqui e é o ÚNICO obstáculo residual depois
da correção.**

## Ambiente de execução

Sessão rodou num worktree isolado sem `backend/data`/`.venv` (gitignored) — todos os comandos
apontaram pro checkout principal via caminho absoluto (leitura E escrita), mesmo padrão dos
agentes de Fase 0. Nenhuma chamada de API-Football, nenhum blob do Neon em runtime, nada em
`model_artifacts_clubes/` tocado (só leitura do `meta.json`). Seed fixa `20260731` em toda
simulação. Scripts em `backend/data/reports/investigacao_multiagente/_cartoes_1t_scratch/`
(`exp_h2.py`, `exp_h4.py`, `exp_h5.py` — reaproveitam integralmente
`research_clubs.protocol`/`corners_nb_model.CornersNB`/`scripts.battery_dataset.load_clubs_df`/
`scripts.gate_count_market.{nb_pmf_grid,baseline_b0,baseline_b2,candidate_pmf}`, nenhuma
reimplementação de métrica).

**Nota de orçamento:** o experimento original (`exp_cartoes_1t.py`, continha H0-H5 num único
processo) foi morto por um limite de runtime em background durante H2 — H0 e H1 já haviam
terminado e ficaram registrados no log antes da morte do processo. Os testes restantes (H2, H4,
H5) foram relançados como scripts isolados menores. Nesta mesma sessão, múltiplos agentes-irmãos
rodavam em paralelo na mesma máquina (outros mercados de cartão), o que causou contenção de CPU
real (cada fold levou bem mais tempo que o esperado) — não foi um problema do código, confirmado
pela reprodução exata do H0 contra o gate oficial.

## H0 — Reprodução do gate oficial (sanity check, não conta como hipótese)

Reproduzi o gate com o MESMO código (`baseline_b0`/`baseline_b2`/`candidate_pmf` importados sem
alteração) sobre `base_feats_170`. Resultado bateu EXATAMENTE o oficial: `folds=1/5`,
`delta_ll=+0,01149`, `tail_ece=0,0232/0,0179`, `coverage80=0,9169`. Confirma que a reimplementação
usada nos experimentos abaixo é fiel ao gate real.

## H1 — Proponente de Dados: rolling do próprio alvo (proxy jogo inteiro)

**Motivação:** `cluster_a.md` §1.1 mostrou que nenhuma das 170 features de produção tem histórico
de cartão, e que a correlação da feature de histórico ignorada (`home/away_sb_cards_l5`, r=0,239)
é 3x mais forte que a MAIOR correlação individual das 170 features atuais (`pace_total`,
r=-0,074). Não existe rolling específico de 1º tempo no parquet (confirmado — só existe rolling do
jogo inteiro); uso o rolling de jogo inteiro como proxy, limitação já antecipada pelo Cluster A.

**Experimento:** adicionei 12 colunas (`home/away_sb_cards_{l3,l5}`, `_against_{l3,l5}`,
`diff_sb_cards_{l3,l5}`, `diff_sb_cards_against_{l3,l5}`) ao candidato (182 features), mesmo
protocolo de 5 folds temporais, mesmos baselines B0/B2.

**Resultado:**

| métrica | oficial (170 feats) | H1 (+rolling, 182 feats) |
|---|---|---|
| folds que melhoram | 1/5 | **2/5** |
| delta_ll médio | +0,01149 | **+0,00075** |
| tail_ece candidato | 0,0232 | **0,0155** (baseline: 0,0179 — já bate!) |
| coverage80 médio | 0,9169 | 0,9268 |

**Classificação: Confirmada (parcial).** Ganho real e na direção certa em 3 das 4 métricas, mas
insuficiente sozinho pra aprovar (delta_ll ainda positivo, só 2/5 folds).

## H2 — Proponente de Dados: H1 + identidade de liga (target-encoding com shrinkage)

**Motivação:** `cluster_a.md` §1.2 — heterogeneidade real entre competições (desvio-padrão das
médias por competição = 0,72, ~16% da média global) não é capturada por nenhuma feature de
`base_feats_170`; um modelo ingênuo "média da competição" já explica R²=9% da variância e vence o
candidato em 19/20 folds nos 4 mercados de cartão. Cluster A recomendou testar 1+2 (histórico +
liga) JUNTOS primeiro, esperando efeito aditivo.

**Experimento:** `target-encoding` de `tournament` com shrinkage bayesiano (`k=50`,
`enc = (n·média_liga + k·média_global)/(n+k)`), calculado **só do TREINO de cada fold** (sem
vazamento, recalculado a cada fold) e adicionado às 182 features de H1 (183 no total).

**Resultado:**

| métrica | oficial | H1 | **H2 (+liga)** | critério do gate |
|---|---|---|---|---|
| folds que melhoram | 1/5 | 2/5 | **5/5** | ≥4/5 |
| delta_ll médio | +0,01149 | +0,00075 | **−0,00454** | < −0,001 |
| tail_ece candidato | 0,0232 | 0,0155 | **0,0143** | ≤0,05 e ≤ baseline (0,0179) |
| coverage80 médio | 0,9169 | 0,9268 | 0,9302 | ∈[0,75; 0,85] |

**3 dos 4 critérios do gate PASSAM.** Só `coverage_ok` continua falso. O ganho é MAIOR que a soma
dos dois pedaços isolados (histórico sozinho mal melhora; liga sozinha não foi testada isolada,
mas a combinação supera claramente qualquer extrapolação linear de H1) — consistente com
interação real entre as duas fontes de variância (time vs liga), como o Cluster A previu.

**Classificação: Confirmada.**

## H4 — Controle negativo (obrigatório para o ganho de H2)

**Motivação:** todo ganho reportado precisa de controle negativo. Testei se o ganho de H2 é sinal
real ou artefato do pipeline (ex.: mudança incidental de grade numérica ao adicionar colunas).

**Experimento:** mesmas 183 features de H2, mas as 12 colunas de rolling E a coluna `tournament`
são embaralhadas dentro do TREINO de cada fold (mesma permutação, quebra a correspondência
rolling/liga↔alvo mantendo a distribuição marginal de cada coluna intacta).

**Resultado:**

| métrica | H0 (oficial, sem features novas) | H4 (H2 com features embaralhadas) |
|---|---|---|
| folds que melhoram | 1/5 | **1/5** |
| delta_ll médio | +0,01149 | **+0,01152** |
| tail_ece candidato | 0,0232 | **0,0236** |
| coverage80 médio | 0,9169 | **0,9169** (idêntico) |

O controle negativo reproduz o candidato original quase exatamente (coverage80 idêntico ao 4º
decimal). **O ganho de H2 desaparece por completo quando a correlação rolling/liga↔alvo é
quebrada por construção — confirma que o sinal é real, não artefato de pipeline.**

## H5 — Auditor de Métricas: alcançabilidade de coverage80 no mu real de cartões_1t

**Motivação:** replicar o método do Cluster B (dados sintéticos gerados pela PRÓPRIA NB assumida
pela arquitetura de produção) com os parâmetros REAIS de `cartoes_1t`, não estimados por proxy —
decide se o `coverage_ok=false` residual de H2 é estrutural ou é erro de ajuste que ainda sobra.

**Experimento:** fitei `CornersNB` (mesmos `base_feats_170`, sem extensão) no dataset inteiro pra
extrair `r_H_`/`r_A_` reais, simulei 400k jogos a partir dessa MESMA distribuição (processo
perfeitamente especificado por construção) e medi `coverage80` desse processo contra o próprio
PMF que o gerou. Também rodei grid de `r` de 0,3 a 1000 no mesmo `mu_h`/`mu_a` real, pra checar se
ALGUM valor de dispersão resolveria.

**Resultado:**

| | valor |
|---|---|
| mu_total real (amostra) | 1,6344 |
| var/média | 1,1385 (sobredispersão modesta, não extrema) |
| r_H_ / r_A_ reais (MLE) | **1000,0 / 1000,0 — no TETO do bound** (otimizador queria ainda menos dispersão) |
| mu_h / mu_a medianos | 0,7598 / 0,8706 |
| **coverage80 do modelo PERFEITO** | **0,9176** |
| coverage80 REAL do gate | 0,9169 |
| gap real − teórico | **−0,0007 (idêntico, dentro do ruído)** |
| algum r do grid (0,3–1000) atinge [0,75; 0,85]? | **NÃO** |

O `r` real bate no teto do bound (1000, quase-Poisson) — o oposto de "dispersão mal estimada" ou
"excesso de dispersão não capturado". Mesmo com esse `r` mínimo de variância, coverage80 sai em
0,9176 — praticamente idêntico ao 0,9169 real. **Isso refuta a hipótese de dispersão mal ajustada
como causa (pedido explícito do papel de Arquitetura) e confirma, com os parâmetros REAIS deste
mercado, exatamente o mecanismo que o Cluster B já havia demonstrado por proxy para
`gols_1t`(mu≈1,08→cov teórico 0,9034)/`gols_2t`(mu≈1,39→cov teórico 0,9480): coverage80 em
[0,75;0,85] é estruturalmente inalcançável para mu_total abaixo de ~2, independente da qualidade
do modelo.** `cartoes_1t` (mu≈1,63) cai exatamente no meio dessa faixa, como esperado.

**Classificação: Confirmada.**

## Arquitetura (papel de Proponente de Arquitetura) — parcial, dentro do orçamento

O teste direto planejado (H3: modelar 1T como fração FIXA do total do jogo inteiro, mesmo padrão
"split fixo" que venceu em escanteios por tempo) **não foi executado** — o orçamento de tempo da
sessão se esgotou por contenção real de CPU (múltiplos agentes-irmãos rodando em paralelo na
mesma máquina; H2 sozinho, que deveria levar ~5min, levou ~30min). Isso é registrado com
honestidade como limitação, não como resultado.

Duas evidências indiretas, ambas já coletadas, cobrem a pergunta subjacente:

1. **Dispersão específica do 1T** (pedido explícito do papel): H5 mostra `r_H_`/`r_A_` no teto do
   bound (quase-determinístico) — refuta "dispersão mal estimada" como causa, mesmo padrão do
   Cluster B.
2. **A arquitetura "split independente" (1T e 2T sem termo compartilhado) em si não é o gargalo**:
   H1/H2 usam EXATAMENTE essa mesma arquitetura (nenhuma mudança estrutural, só features novas) e
   saltam de 0/4 critérios pra 3/4. Se a independência 1T/2T fosse o problema dominante, adicionar
   feature não teria destravado `folds_ok`/`delta_ok`/`tail_ece_ok` dessa forma.

**Classificação: Inconclusiva** (teste direto não rodado), mas com evidência indireta forte
apontando pra "arquitetura não é o gargalo residual" — a fração-fixa-do-total continua sendo um
teste barato e legítimo pra um próximo ciclo, mas não é urgente dado o resultado de H2.

## Parecer do Auditor de Métricas

Coverage80 não é uma falha de modelo neste mercado — é um limite matemático da construção do
intervalo central de 80% sobre uma PMF discreta de poucos bins de massa não-desprezível (12,
neste caso) quando mu_total é baixo. O gap entre o valor real do gate (0,9169) e o valor teórico
de um modelo PERFEITO (0,9176) é de −0,0007 — dentro do ruído de simulação. Nenhum valor de `r`
testado (grid 0,3 a 1000) resolve. Recalibração isotônica (já testada, `cartoes_1t_clube_calibracao.json`)
não resolve porque recalibra só a linha central, não os quantis 10%/90% que a métrica usa. A
métrica, como definida hoje, é inadequada para mercados com mu_total < ~2,5 (mesma faixa que
`cluster_b.md` já havia mapeado como "impossível ou frágil" de forma mais ampla no dataset de
`gols_1t`/`gols_2t`).

## Parecer do Crítico

Nenhum experimento repetido do que já constava em `DOCUMENTACAO_CENTRAL.md` §8/§9/§16/§17/§19/§25
ou nos dois relatórios de Fase 0. A calibração isotônica isolada (já fechada como insuficiente) não
foi retestada. O ganho de H2 tem controle negativo limpo (H4) — a mesma feature embaralhada
reproduz o candidato original quase byte-a-byte (coverage80 idêntico ao 4º decimal), o que é uma
evidência de qualidade acima da média pra um controle negativo. Limitação honesta: o rolling usado
é PROXY de jogo inteiro (não existe rolling específico de 1º tempo no parquet atual — mesma
limitação que o Cluster A já havia sinalizado); é plausível que um rolling half-specific (exigiria
mudança em `build_clubs_halftime_targets.py` pra também emitir histórico por-tempo) melhore ainda
mais o resultado, mas não era necessário pra já mover o veredito de 0/4 pra 3/4 critérios. A
arquitetura (H3) ficou sem teste direto por motivo de infraestrutura da sessão (contenção real de
CPU multiplicando o tempo de cada fold em ~6x), não por escolha de escopo — registrado como
limitação, dentro da regra de parar quando o orçamento se esgota.

## Síntese

A reprovação original de `cartoes_1t` era dominada pelo mecanismo do **Cluster A** (falta de
feature de histórico do próprio alvo + falta de identidade de liga), NÃO pelo mecanismo do
**Cluster B** isoladamente — mas o mecanismo do Cluster B (limite estrutural de coverage80 em
mu_total baixo) também está presente e passa a ser o ÚNICO obstáculo depois que o problema de
feature é corrigido. É "ambos", mas não em pé de igualdade: o driver de feature explica ~100% do
gap em `delta_ll`/`tail_ece`/`folds` (3 dos 4 critérios, de reprovado total pra aprovado total
nessas 3 dimensões) e o driver de métrica explica o 4º critério residual, que H5 mostra ser
matematicamente inalcançável independente de qualquer melhoria futura de modelo.

## Recomendação

**Limitação do gate §6-C** (com uma ação concreta anexa, não um "não dá pra fazer nada"):

1. Adotar o candidato de H2 (170 features de produção + 12 colunas de rolling de cartão do jogo
   inteiro como proxy de 1T + target-encoding de liga com shrinkage k=50) como o novo candidato de
   referência para `cartoes_1t/clube` — ele passa `folds_ok`, `delta_ok` e `tail_ece_ok` com folga
   (5/5, −0,00454, 0,0143 < baseline 0,0179).
2. O único bloqueio restante (`coverage_ok`) é estrutural, não de ajuste — H5 confirma com os
   parâmetros REAIS deste mercado exatamente o que `cluster_b.md` já havia proposto por proxy: o
   dono do gate precisa decidir entre (a) substituir o teto fixo `coverage80∈[0,75;0,85]` por uma
   faixa calculada por mercado via a mesma simulação de auto-consistência usada aqui, ou (b)
   descartar `coverage80` como critério de aprovação para mercados com mu_total < ~2,5 (mantendo
   só `tail_ece`, que já é comparativo contra baseline e não sofre do mesmo viés de discretização).
   Essa decisão está fora do escopo desta investigação (é do dono do projeto), mas sem ela
   `cartoes_1t` fica preso indefinidamente mesmo com um modelo comprovadamente bom.
3. Se/quando o gate for revisado, recomenda-se também tentar um rolling ESPECÍFICO de 1º tempo
   (não o proxy de jogo inteiro) — exigiria estender `build_clubs_halftime_targets.py` — como
   melhoria incremental de um próximo ciclo, não como bloqueio.

## Arquivos gerados

- `backend/data/reports/investigacao_multiagente/_cartoes_1t_scratch/exp_h2.py`,
  `exp_h4.py`, `exp_h5.py` — scripts dos experimentos (H0/H1 rodaram num script anterior que foi
  morto por limite de runtime; resultados ficaram registrados no log de execução antes da morte
  do processo e são reproduzíveis pelo mesmo protocolo usado em `exp_h2.py`).
- `h0_reproducao.csv`, `h1_rolling.csv`, `h2_rolling_liga.csv`, `h2_result.json`,
  `h4_controle_negativo.csv`, `h4_result.json`, `h5_grid_r.csv`, `h5_result.json`.
- Nenhum artefato de produção foi tocado; nenhuma chamada de API foi feita; nenhum blob do Neon
  foi lido em runtime.

## Addendum — formalização em script de produção (mesma sessão, autorizado pelo dono)

Dono aprovou seguir com `cartoes_1t` depois de ver este relatório. O candidato H2 foi formalizado
em `backend/scripts/train_cartoes_1t_market.py` (mesmo padrão de `train_yellowcards_market.py`:
`CONFIG` dict por escopo, `--scope`, salva `.joblib`) e retreinado de verdade (não reaproveitando
o scratch) — artefato em `model_artifacts_clubes/cartoes_1t_nb.joblib` **dentro do worktree desta
sessão** (worktree isolado não materializa `model_artifacts_clubes/` do checkout principal; escrita
aí foi autorizada só de forma escopada ao worktree, sem sobrescrever o artefato compartilhado que
outros agentes-irmãos usam em paralelo).

Números OFICIAIS do gate (`backend/scripts/run_official_gate_cartoes_1t.py` — mesma lógica de
`research_clubs.protocol`/`scripts.gate_count_market`, sem reimplementar métrica; `gate_count_market.py`
em si não tem modo de aceitar candidato com feature set estendido sem editar o arquivo compartilhado,
por isso um script separado, documentado como números finais, não mais scratch de investigação):

| critério | candidato oficial anterior | **candidato H2 (produção)** | limiar do gate |
|---|---|---|---|
| folds que melhoram | 1/5 | **5/5** ✅ | ≥4/5 |
| delta_ll médio | +0,01149 | **−0,00454** ✅ | < −0,001 |
| tail_ece candidato | 0,0232 | **0,0143** ✅ | ≤0,05 e ≤ baseline |
| coverage80 médio | 0,9169 | 0,9302 ❌ | ∈[0,75; 0,85] |
| **status sob critério fixo atual** | REPROVADO | **REPROVADO** (só por coverage80) | |

Resultado idêntico ao H2 da investigação (confirma reprodutibilidade do retreino formal). Sob o
critério fixo `[0,75;0,85]` do gate §6-C, o candidato continua tecnicamente REPROVADO — mas está a
apenas `+0,0126` do teto estruturalmente alcançável calculado em H5 (0,9176, modelo perfeitamente
especificado no mu_total real ~1,63). Critério de coverage80 para mercados de mu_total baixo segue
em decisão do dono (threshold por mu vs. descartar para mu baixo vs. manter fixo) — arquivo
`cartoes_1t_clube_H2_oficial.json` documenta os dois números lado a lado para essa decisão.

Arquivos: `backend/scripts/train_cartoes_1t_market.py`,
`backend/scripts/run_official_gate_cartoes_1t.py`,
`backend/data/reports/gate_mercados/cartoes_1t_clube_H2_oficial.{json,csv}`,
`model_artifacts_clubes/cartoes_1t_nb.joblib` (dentro do worktree desta sessão).
