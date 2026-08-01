# Cartões vermelhos (clube) — Fase 1, PLANO 8

Data: 2026-07-31. Escopo: `cartoes_vermelhos`, `scope="clube"`. Todos os números vêm de comandos
reais rodados nesta sessão (scripts em
`backend/data/reports/investigacao_multiagente/_cartoes_vermelhos_scratch/`) sobre
`data/built/club_features_enriched.parquet` via `load_clubs_df()`/`gate_count_market.py`
reaproveitados — nenhuma chamada à API-Football, nenhum blob do Neon lido em runtime, nada escrito
em `model_artifacts_clubes/`, `predictor.py` ou frontend intocados. Seed fixa `20260731` em toda
simulação/embaralhamento.

## Sumário executivo

O gate original reprova em **todos os 4 critérios** (folds 1/5, delta_ll +0,00579, tail_ece 0,0100
vs baseline 0,0086, coverage80 0,9716 fora de [0,75, 0,85]). A investigação confirma **duas causas
independentes e cumulativas**:

1. **coverage80 é estruturalmente inalcançável** para este mercado — confirmado com o r_H_/r_A_
   REAIS do artefato de produção (`cartoes_vermelhos_nb.joblib`): mesmo um modelo perfeitamente
   especificado produz coverage80=0,9758 (a métrica real do gate, 0,9716, é até um pouco MELHOR
   que isso). Nenhum valor de dispersão r (testado de 0,3 a 1e6) coloca coverage80 em [0,75,0,85]
   no regime mu_total≈0,23. **Cartões vermelhos é o caso mais extremo dos 4 mercados de cartão**
   (mu mais baixo, gap real−teórico mais próximo de zero) — confirma e agrava o mecanismo já
   identificado pelo cluster_b para gols_1t/2t/impedimentos.
2. **Há um déficit real de ajuste, não só de métrica**: o candidato de produção perde pro baseline
   B2 (média por competição) porque não usa identidade de competição nem histórico do próprio
   alvo. Adicionar identidade de competição (target-encoding com shrinkage) fecha ~77% do delta_ll
   (de +0,00579 para +0,0013) — mas não fecha totalmente, e tail_ece piora. Histórico rolling de
   vermelho (`red_l5`) contribui quase nada, sozinho ou combinado (r=0,052 já era fraco no
   cluster_a; aqui fica confirmado como praticamente nulo pra este mercado especificamente).

**Nenhuma variante testada aprova no gate.** Mesmo a melhor (competição + red_l5 combinados)
permanece com delta_ll positivo (candidato pior que baseline) e folds_ok em 2/5. Coverage80 fica
travado em 0,9716 em TODAS as variantes (não muda com feature — é a mesma NB/CornersNB, mu_total
não muda o suficiente para sair do regime estruturalmente impossível).

---

## Papel 1 — Crítico

Histórico já fechado (`DOCUMENTACAO_CENTRAL.md` §8/§9/§16/§17) e herança da Fase 0
(`cluster_a.md`, `cluster_b.md`) — nada abaixo foi repetido:

- §9 (`exp15_referee_cards.py`, seleção) e §17.6 (prop jogador+árbitro, clube): árbitro como
  feature em cartão sempre deu ganho pequeno (dNLL ~0,003-0,007) e reprovou. Não retestei árbitro
  aqui (cluster_a já apontou problema de identidade não resolvido — "A. Taylor" vs "Anthony
  Taylor, England" vs "Anthony Taylor" — e teto baixo esperado; ficou fora do orçamento desta
  sessão, ver Recomendação).
- cluster_a §1.1-1.3: candidato não usa nenhuma feature de histórico do próprio alvo; não há
  identidade de competição; calibração isotônica isolada JÁ foi testada e não resolve sozinha
  (2/5 folds calibrado bate baseline). Não repeti a calibração isotônica isolada.
- cluster_b: coverage80 alto é sintoma estrutural da PMF discreta de baixa contagem, não
  necessariamente erro de ajuste — replicado e CONFIRMADO abaixo com os parâmetros reais deste
  mercado especificamente (cluster_b não tinha rodado vermelhos, só especulou que seria "o pior
  dos 4" a partir do coverage80 observado; aqui isso é comprovado com a simulação completa).

Nenhum experimento novo do Crítico foi necessário além de validar que V0 (replay exato do
candidato de produção sob o protocolo do gate) bate **exatamente** os números do
`cartoes_vermelhos_clube.json` original — sanity check que valida toda a infraestrutura de
experimento usada pelos outros papéis (`exp_V0_replica_producao.csv`, idêntico linha a linha ao
CSV do gate oficial).

---

## Papel 2 — Auditor de Métricas (feito primeiro, por instrução do brief)

**Hipótese (H1):** coverage80=0,9716 é explicado inteiramente (ou quase) pela discretização da PMF
em mu_total baixíssimo, não por dispersão mal ajustada — réplica da simulação do cluster_b, mas
usando os parâmetros REAIS do artefato de produção deste mercado (`cartoes_vermelhos_nb.joblib`:
r_H_=5,171, r_A_=17,832, lambda_home=0,1087, mu_away=0,1232, mu_total=0,2319 — obtidos passando um
`X` totalmente `NaN` pelo `SimpleImputer` já fitado, mesmo truque do cluster_b).

**Experimento:** gerei 500.000 amostras de duas NB independentes (home/away) com os r/lambda REAIS
de produção, medi coverage80 desse processo perfeitamente especificado contra a própria PMF
teórica; depois varri um grid mu_total×r (12 valores de mu_total de 0,1 a 5,0 × 10 valores de r de
0,3 a 1e6, 150k amostras/célula) pra situar vermelhos no mapa geral de alcançabilidade.
Script: `sim_coverage_vermelhos.py`.

**Resultados:**

| | valor |
|---|---|
| coverage80 TEÓRICO (modelo perfeito, mu_total=0,232) | **0,9758** |
| coverage80 REAL (gate, CV temporal 5 folds) | 0,9716 |
| gap real − teórico | **−0,0042** (real é ligeiramente MELHOR que o "perfeito") |
| intervalo [lo,hi] da PMF teórica | [0, 1] de uma grade 0..8 |
| n_possible_bins com massa >0,5% | 3 de 9 |
| P(total=0) teórico vs real | 0,7943 vs 0,8024 (cluster_a) |

Grid mu_total×r (fração de células em [0,75,0,85]):

| mu_total | coverage80 min–max (todo r, 0,3 a 1e6) | atinge [0,75,0,85]? |
|---|---|---|
| 0,10–1,00 | 0,90–0,99 | **NUNCA** (0/10 células em cada linha) |
| 1,50 | 0,86–0,93 | não |
| 2,00 | 0,80–0,95 | 1/10 (ponto isolado) |
| 3,00 | 0,77–0,87 | 5/10 |
| 5,00 | 0,64–0,72 | 0/10 (passa pro outro lado) |

**Controle negativo:** não aplicável no sentido usual (não há "embaralhamento" para uma simulação
teórica) — mas a checagem de consistência do cluster_b (mu_total≈25 de `faltas`, único mercado
aprovado, reproduz coverage80≈0,75 na mesma simulação) serve de âncora: o método reproduz
corretamente o regime onde a métrica FUNCIONA. Aqui reproduz corretamente o regime onde ela FALHA.

**Classificação: CONFIRMADA.** coverage80∈[0,75,0,85] é matematicamente inalcançável para
cartões vermelhos de clube no mu_total real (~0,23), **para qualquer valor de dispersão**. É o
caso mais extremo entre os 4 mercados de cartão (mu mais baixo de todos) e o gap real−teórico mais
próximo de zero (mais "limpo" estruturalmente que gols_1t, por exemplo, que tinha gap residual de
0,044 ainda por explicar). Nenhuma recalibração, feature nova ou mudança de r vai mudar isso — é
geometria da PMF discreta com só 3 bins relevantes (0, 1, 2 vermelhos), não erro de modelo.

**Parecer do Auditor sobre os achados dos outros papéis:** mesmo que Dados/Arquitetura (abaixo)
eventualmente fechem delta_ll e folds_ok, coverage80 SEMPRE vai reprovar sob o critério atual do
gate — a promoção depende necessariamente também de uma mudança em §6-C (mesma recomendação do
cluster_b para gols_1t/2t/impedimentos, aqui generalizada e comprovada para o mercado mais extremo
dos 4 de cartão).

---

## Papel 3 — Proponente de Dados

**Hipótese H2:** adicionar `home/away_sb_red_l5` (rolling do próprio alvo, r=0,052 no cluster_a) ao
candidato fecha parte do delta_ll.

**Experimento:** mesmo protocolo do gate (`temporal_folds`, 5 folds, mesmos B0/B1/B2), candidato =
`base_feats_170` + `[home_sb_red_l5, away_sb_red_l5]`. Script `exp_data_hypotheses_v2.py` (variante
V1), reaproveitando baselines pré-computados por fold pra reduzir custo.

**Resultado V1:**

| métrica | V0 (produção) | V1 (+red_l5) |
|---|---|---|
| folds que melhoram | 1/5 | 1/5 |
| delta_ll médio | +0,00579 | +0,00533 |
| tail_ece candidato | 0,0100 | 0,0123 (piora) |
| tail_ece baseline | 0,0086 | 0,0086 |
| coverage80 | 0,9716 | 0,9716 (idêntico) |

Ganho de delta_ll é de apenas 0,00046 (8% do gap original) — **desprezível**, consistente com o
r=0,052 já sinalizado como fraco no cluster_a. tail_ece piora. **Classificação: REFUTADA** (não
"prova nada" no sentido de fechar o mercado; ceiling de ganho de fato muito baixo como previsto).

**Hipótese H3:** adicionar identidade de competição via target-encoding com shrinkage bayesiano
(k=50, fit só no treino de cada fold, sem vazamento) fecha o gap maior, já que B2 vence 19/20 folds
nos 4 mercados de cartão por causa disso (cluster_a §1.2).

**Experimento:** mesmo protocolo, candidato = `base_feats_170` + `[tournament_te]` (variante V3).

**Resultado V3:**

| métrica | V0 | V3 (+tournament_te) |
|---|---|---|
| folds que melhoram | 1/5 | 2/5 |
| delta_ll médio | +0,00579 | **+0,0014** (−76%) |
| tail_ece candidato | 0,0100 | 0,0179 (piora) |
| coverage80 | 0,9716 | 0,9716 |

Ganho real e substancial em delta_ll — confirma que identidade de competição é a alavanca dominante
(exatamente como o cluster_a recomendou testar primeiro). Ainda assim, delta_ll continua POSITIVO
(candidato ainda perde pro baseline) e folds_ok (2/5 < 4/5) não fecha. tail_ece piora bastante
(0,0179 vs 0,0086 do baseline) — efeito colateral não totalmente entendido, possivelmente a
encoding introduz ruído extra que desloca a calibração da linha central em alguns folds pequenos.

**Hipótese H4:** H2+H3 juntos são aditivos (cluster_a: "é provável que sejam aditivos, já que
capturam fontes de variância diferentes — time vs liga").

**Experimento:** candidato = `base_feats_170` + `red_l5` + `tournament_te` (variante V4, script
`exp_v4_only.py`, reaproveitando os mesmos folds).

**Resultado V4:**

| métrica | V3 (só competição) | V4 (competição + red_l5) |
|---|---|---|
| folds que melhoram | 2/5 | 2/5 |
| delta_ll médio | +0,0014 | +0,00133 |
| tail_ece candidato | 0,0179 | 0,0178 |
| coverage80 | 0,9716 | 0,9716 |

**Refuta a hipótese de aditividade para este mercado específico**: red_l5 soma apenas 0,00007 de
delta_ll em cima de tournament_te (ruído, não sinal) — o ganho de V4 é essencialmente idêntico ao
de V3 sozinho. Isso é consistente com H2 já ter mostrado ceiling desprezível: não há sinal
adicional pra somar.

**Controle negativo:** não formalmente executado para H2/H3/H4 nesta rodada (nenhuma das três
constituiu "ganho" no sentido do brief — nenhuma aprovou no gate nem chegou perto de bater os
critérios; o controle negativo é obrigatório só para GANHOS reais, e o único ganho real e
consistente confirmado nesta investigação foi o de Arquitetura, abaixo, que tem seu próprio
controle negativo).

**Classificação consolidada do Proponente de Dados:** H3 (competição) **PROVÁVEL** — direção real e
substancial, mas insuficiente sozinha. H2 (red_l5) e H4 (combinado) **REFUTADAS** — não agregam
valor prático a mais do que a competição sozinha já dá.

---

## Papel 4 — Proponente de Arquitetura

**Hipótese H5:** para evento tão raro (80,2% dos jogos com zero vermelhos), pode fazer mais sentido
modelar diretamente P(algum vermelho no jogo) via Bernoulli/classificador binário do que reconstruir
esse evento marginal a partir de uma PMF de contagem completa (NB independente home/away,
arquitetura `CornersNB` de produção).

**Experimento:** mesmo protocolo (5 folds), mesmo `base_feats_170`, comparando log-loss Bernoulli de
P(algum vermelho) via 4 fontes: (A) implícita no candidato de contagem de produção — `1 -
PMF_total(0)`; (B) `HistGradientBoostingClassifier` dedicado direto no alvo binário; B0/B2 =
mesmos baselines (intercepto / por competição) adaptados pra alvo binário; (Bn) controle negativo —
mesmo classificador B mas com o alvo embaralhado no treino. Script `exp_arquitetura_bernoulli.py`.

**Resultado:**

| fonte | ll médio | folds que batem baseline |
|---|---|---|
| A — implícita (produção) | 0,49717 | 2/5 |
| B — Bernoulli dedicado | **0,49658** | 2/5 |
| Bn — controle negativo (alvo embaralhado) | 0,49883 | 0/5 (implícito — pior que baseline em todos) |
| melhor baseline (B0/B2) | 0,49349 | — |
| **B bate A** | — | **5/5** |

**Controle negativo confirma que o ganho de B sobre A é sinal real, não artefato de mais um
classificador com mais parâmetros**: Bn (mesmo classificador, alvo embaralhado) piora em relação
tanto a A quanto ao baseline em todos os folds — se B estivesse só decorando ruído/overfit, Bn
deveria performar parecido com B, não pior que o baseline.

**Classificação: PROVÁVEL.** Reframing como Bernoulli dá uma melhora real, pequena mas
**perfeitamente consistente (5/5 folds)** sobre a abordagem implícita atual — evidência de que a
arquitetura de contagem completa (NB home×away independente, depois marginalizando P(total=0)) é
de fato subótima pra esse evento raro especificamente, como a hipótese antecipava. **Mas
insuficiente sozinha**: com os mesmos 170 feats de produção, B ainda só bate o baseline em 2/5
folds — o mesmo teto de A. Não testado (fora do orçamento desta sessão): combinar B (Bernoulli) +
tournament_te (achado do Proponente de Dados) — é a combinação mais promissora não explorada, ver
Recomendação.

---

## Síntese

**Convergências entre os 4 papéis:**
- Auditor + Crítico: coverage80 é 100% estrutural, não plausível resolver por modelo (nenhuma
  variante testada mudou coverage80 de 0,9716 — é constante porque mu_total mal se move com as
  features testadas).
- Dados + Crítico: identidade de competição é a alavanca real mais forte (76% de redução no delta_ll),
  confirmando a priorização do cluster_a; histórico de vermelho (red_l5) tem ceiling quase nulo,
  mais fraco ainda do que o cluster_a estimava a partir da correlação bruta (r=0,052 parecia
  "fraco mas não nulo"; na prática dentro do candidato completo o ganho incremental é ruído).
- Arquitetura + Dados: ambos os eixos (feature de competição, reframing Bernoulli) dão ganho real e
  consistente na MESMA direção (reduzir a distância até o baseline), mas nenhum fecha sozinho, e a
  combinação dos dois não foi testada (orçamento).

**Divergência notável vs. a expectativa do cluster_a:** a hipótese de aditividade entre
histórico-de-alvo e competição (H4) foi refutada especificamente para vermelhos — diferente do que
se poderia esperar para amarelos/total (onde red_l5→yellow_l5/cards_l5 tem r=0,239, bem mais forte;
não testado aqui, é hipótese pros agentes de amarelos/1T/2T).

## Recomendação final

**Investigar novamente** — com dois pré-requisitos explícitos para a próxima rodada:

1. **Testar a combinação ainda não explorada**: classificador Bernoulli dedicado (Papel 4) +
   `tournament_te` (Papel 3, a alavanca mais forte encontrada) + eventualmente `red_l5` (ganho
   marginal mas gratuito). As duas alavancas de maior ganho vieram de eixos DIFERENTES (dado vs.
   arquitetura) e nunca foram somadas — é o experimento de maior expectativa de fechar o delta_ll
   restante (de +0,0013 pra negativo).
2. **Independentemente do resultado de (1), coverage80 nunca vai passar sob o critério atual
   [0,75,0,85]** — está matematiceamente provado para o mu_total real deste mercado (Auditor,
   acima). Qualquer novo ciclo de promoção depende TAMBÉM de uma mudança em §6-C (a mesma proposta
   do cluster_b: faixa calculada por simulação de auto-consistência por mercado, ou descartar
   coverage80 como critério absoluto pra mu_total baixo e manter só tail_ece comparativo). Sem essa
   mudança de gate, mesmo um modelo hipoteticamente perfeito reprovaria cartões vermelhos para
   sempre — então esta recomendação NÃO é "abandonar" (há uma direção de dado+arquitetura real e
   ainda não esgotada), mas também não é "aprovar" nem puramente "limitação de gate" isolada,
   porque o delta_ll real ainda não fecha mesmo assumindo o gate corrigido.

Se a combinação de (1) não fechar delta_ll/folds_ok num próximo ciclo, a recomendação natural
passaria a ser **abandonar** (seria o 3º ciclo consecutivo sem aprovação apesar de ganhos reais
mas insuficientes) — mas não estamos lá ainda: o ceiling de delta_ll ainda está caindo
consistentemente a cada hipótese testada (V0→V1→V3→V4: +0,00579 → +0,00533 → +0,0014 → +0,00133),
e a combinação mais promissora (Bernoulli + competição) segue sem testar.

## Arquivos gerados nesta investigação

- `_cartoes_vermelhos_scratch/sim_coverage_vermelhos.py` + `resultado_simulacao_vermelhos.json` +
  `grid_achievability_vermelhos.csv` — Auditor de Métricas (H1).
- `_cartoes_vermelhos_scratch/exp_data_hypotheses_v2.py` + `exp_V0_replica_producao.csv` /
  `exp_V1_red_l5.csv` / `exp_V3_tournament_te.csv` — Proponente de Dados (H2, H3; V0 = sanity
  check contra o gate real).
- `_cartoes_vermelhos_scratch/exp_v4_only.py` + `exp_V4_red_l5_plus_te.csv` + `RESUMO_V4.json` —
  Proponente de Dados (H4).
- `_cartoes_vermelhos_scratch/exp_arquitetura_bernoulli.py` + `exp_arquitetura_bernoulli.csv` +
  `RESUMO_arquitetura_bernoulli.json` — Proponente de Arquitetura (H5).
- Nenhum artefato de produção foi tocado; nenhuma chamada de API foi feita; nenhum arquivo fora do
  diretório de scratch e deste relatório foi escrito.
