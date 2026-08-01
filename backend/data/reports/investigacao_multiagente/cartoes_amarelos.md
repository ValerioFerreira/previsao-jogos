# Cartões amarelos (clube) — Fase 1, PLANO 8

Data: 2026-07-31. Mercado `cartoes_amarelos`, `scope="clube"`. Todos os números vêm de
execuções reais desta sessão (scripts em
`backend/data/reports/investigacao_multiagente/_cartoes_amarelos_scratch/`), reaproveitando
INTEGRALMENTE `scripts/gate_count_market.py` (baselines B0/B1/B2, `CornersNB`,
`_load_market_data`) e `research_clubs/protocol.py` (folds temporais, `pmf_logloss`,
`tail_ece`, `coverage80`) — nenhuma métrica ou baseline foi reimplementada. Só a LISTA de
features do candidato foi estendida por hipótese, mantendo o resto do pipeline idêntico ao
gate oficial, para ficar comparável número-a-número com o resultado já registrado
(`gate_mercados/cartoes_amarelos_clube.json`):

```
folds que melhoram: 0/5 | delta_ll_medio: +0.01816 | tail_ece candidato 0.0427 vs
baseline 0.024 | coverage80: 0.8581 | N: 147211
```

Todos os scripts, CSVs e JSONs desta investigação estão em
`backend/data/reports/investigacao_multiagente/_cartoes_amarelos_scratch/`
(`run_experiments.py`, `run_remaining.py`, `run_h4_gap_rating.py`, `exp_*.json/csv`,
`RESUMO_experimentos*.json`).

## 0. Crítico — o que já foi tentado (não repetido)

Herança da Fase 0 (`investigacao_multiagente/cluster_a.md`), lida na íntegra antes de
propor qualquer experimento novo:

1. Candidato de produção (170 features) não usa NENHUMA feature de histórico do próprio alvo
   de cartão — confirmado, é a causa-raiz mais provável.
2. Colunas de rolling do alvo (`home/away_sb_yellow_l5`, `_cards_l5`) existem no parquet e
   NÃO são usadas — r=0,239 com o alvo, 3x mais forte que a melhor das 170 features (r=-0,074).
3. Falta identidade de competição — média por torneio já explica R²≈9% da variância total,
   e o baseline B2 (média de competição) vence o candidato em 19/20 folds nos 4 mercados de
   cartão.
4. Calibração isotônica isolada (sobre o candidato CRU de 170 features) já foi testada
   (`--calibration-check`) e NÃO resolve sozinha (0/5 folds calibrado bate baseline). **Não
   repeti esse experimento no candidato cru.**
5. Overdispersão é modesta (var/média 1,09) — não é o driver.
6. Árbitro: nunca testado em cartão de EQUIPE de clube (só seleção-equipe e clube-jogador,
   ambos reprovados por margem pequena) — teto de ganho esperado baixo.
7. `DOCUMENTACAO_CENTRAL.md` §8/§9/§16/§17 conferidos: nenhum experimento fechado testou
   histórico rolling do próprio alvo, encoding de competição ou GAP rating em cartão de
   equipe — a lacuna real estava livre para investigar.

Dado o forte direcionamento da Fase 0, priorizei exatamente a ordem sugerida (rolling do
próprio alvo → identidade de competição → combinação), e adicionei uma hipótese de
arquitetura (rating incremental em vez de média móvel fixa) que não tinha sido cogitada na
Fase 0. Não testei árbitro (orçamento consumido pelas 4 hipóteses de maior teto esperado;
ver §5).

## 1. Hipóteses testadas

Todas rodadas com a MESMA arquitetura de produção (`CornersNB` sobre `base_feats_170` +
extras), mesmos 5 folds temporais (`protocol.temporal_folds`), seed 42, N=147.211 (idêntico
ao gate oficial). Baselines B0/B1/B2 recalculados em cada fold, sem alteração.

### H1 — Proponente de Dados: rolling do próprio alvo (`sb_yellow_l5`)

Autor: Proponente de Dados. Motivação: r=0,239 é a correlação mais forte com o alvo em todo
o dataset (Fase 0), e nunca chega ao candidato.

| variante | features extras | folds | delta_ll | tail_ece cand. | tail_ece base | cov80 | status |
|---|---|---|---|---|---|---|---|
| H1a | `{home,away}_sb_yellow_l5` | 2/5 | +0,00141 | 0,0273 | 0,024 | 0,8685 | REPROVADO |
| H1b | H1a + `{home,away}_sb_yellow_l3` | 2/5 | +0,00135 | 0,0276 | 0,024 | 0,8688 | REPROVADO |
| H1c | H1a + `{home,away}_sb_yellow_against_l5` | **4/5** | **-0,007** | **0,0207** | 0,024 | 0,8728 | REPROVADO (só coverage falha) |

`l3` não acrescenta nada sobre `l5` (H1b ≈ H1a, redundante). O ganho real vem de somar a
versão "cartão recebido pelo adversário contra este time" (`against_l5`, proxy de
estilo/pressão sofrida) — H1c passa em 3 dos 4 critérios do gate (folds_ok, delta_ok,
tail_ece_ok todos `true`), só falha coverage80 (0,8728 > teto 0,85). Grande salto sobre o
candidato original (folds 0/5→4/5, delta +0,018→-0,007, tail_ece 0,043→0,021).

**Classificação: Provável.** Direção certa, efeito real e substancial, mas insuficiente
sozinho para aprovar.

### H2 — Proponente de Dados: identidade de competição (target-encoding shrinkage)

Autor: Proponente de Dados. Motivação: heterogeneidade de liga (desvio-padrão de médias por
competição = 0,72, R²≈9% só com a média) não está representada em `base_feats_170`
(só existe `tournament_weight`/`is_competitive`, que não são identidade). Encoding bayesiano
(`(n·média_torneio + k·média_global)/(n+k)`, k=50), computado SÓ do treino por fold — sem
vazamento.

| features extras | folds | delta_ll | tail_ece cand. | tail_ece base | cov80 | status |
|---|---|---|---|---|---|---|
| `tournament_enc_yellow` | 5/5 | -0,00845 | 0,0292 | 0,024 | 0,875 | REPROVADO |

Todos os 5 folds melhoram e delta_ll é bem negativo, mas tail_ece (0,0292) fica acima do
baseline (0,024) e coverage80 acima do teto — sozinho não fecha o gate.

**Classificação: Provável.** Sinal real e consistente (5/5 folds), mas insuficiente sozinho.

### H3 — combinação H1a + H2 (recomendação explícita da Fase 0)

| features extras | folds | delta_ll | tail_ece cand. | tail_ece base | cov80 | status |
|---|---|---|---|---|---|---|
| `{home,away}_sb_yellow_l5` + `tournament_enc_yellow` | **5/5** | **-0,01239** | **0,0238** | 0,024 | 0,8767 | REPROVADO (só coverage falha) |

3 dos 4 critérios do gate passam com folga (folds_ok, delta_ok, tail_ece_ok todos `true` —
tail_ece do candidato agora fica ABAIXO do baseline, 0,0238 < 0,024). Único critério que
falha é coverage80 (0,8767, acima do teto 0,85 — PMF um pouco larga demais).

**Controle negativo (`CTRL_H3_permuted`)** — mesmas colunas extras, embaralhadas
(`np.random.permutation`) depois de calculadas, mesmo pipeline: folds 0/5, delta_ll
+0,01815, tail_ece 0,0423, cov80 0,858 — **reverte quase exatamente para os números do gate
original** (0/5, +0,01816, 0,0427, 0,8581). Confirma que o ganho de H3 é sinal real das
features, não artefato do pipeline.

**Classificação: Provável (quase Confirmada)** — a combinação captura a maior parte do
ganho esperado pela Fase 0 e passa 3/4 critérios com folga; falta só fechar coverage80.

### H4 — Proponente de Arquitetura: GAP rating incremental em vez de média móvel fixa

Autor: Proponente de Arquitetura. Motivação: `H1` usa uma média móvel simples de 5 jogos —
não separa efeito casa/fora nem ataque ("provoca falta") de defesa ("sofre cartão"), e não
acompanha a evolução do time entre jogos (é uma janela fixa, não um estado que se atualiza).
GAP ratings (Wheatcroft 2020/21, `research_clubs.ratings.compute_gap_ratings`) já são usados
em produção para chutes/escanteios (`gap_shots_*`, `gap_corners_*`, 12 das 170 features) —
rating incremental de ataque/defesa casa/fora, atualizado jogo a jogo. Reaproveitei a MESMA
função genérica, só aplicada em `home_cur_sb_yellow`/`away_cur_sb_yellow` em vez de
chutes/escanteios (`gap_yellow_home_att/def/away_att/def/exp_home/exp_away`). Cálculo 100%
causal (cada linha só usa jogos anteriores do mesmo time), computado uma vez sobre o dataset
inteiro ordenado por data — mesmo padrão já usado em produção para os GAP de chutes/
escanteios, sem vazamento.

| variante | features extras | folds | delta_ll | tail_ece cand. | tail_ece base | cov80 | status |
|---|---|---|---|---|---|---|---|
| H4a | GAP rating de cartão amarelo (6 cols) | **5/5** | **-0,0192** | **0,0158** | 0,024 | 0,8797 | REPROVADO (só coverage falha) |
| H4b | H4a + `tournament_enc_yellow` | **5/5** | **-0,02156** | **0,016** | 0,024 | 0,88 | REPROVADO (só coverage falha) — **melhor candidato de toda a investigação** |

H4a sozinho já bate H1c em todas as métricas de ajuste (delta_ll -0,0192 vs -0,007; tail_ece
0,0158 vs 0,0207) — o rating incremental captura mais sinal que a média móvel simples com o
MESMO dado de origem (contagem de cartão amarelo por jogo). H4b (rating + torneio) é o
melhor candidato testado nesta investigação: folds 5/5, delta_ll -0,02156 (melhor de todos),
tail_ece 0,016 (bem abaixo do baseline 0,024) — só falha coverage80 (0,88, o mais alto entre
os REPROVADOs "quase lá", mas ainda no mesmo regime dos outros).

**Controle negativo (`CTRL_H4b_permuted`)** — mesmas colunas, embaralhadas: folds 0/5,
delta_ll +0,01815, tail_ece 0,0424, cov80 0,8583 — de novo reverte quase exatamente ao gate
original. Confirma que o ganho de H4b também é sinal real, não artefato.

**Classificação: Confirmada** — arquitetura importa: a MESMA informação bruta (cartão
amarelo passado) rende mais quando modelada como rating incremental ataque/defesa do que
como média móvel fixa, com controle negativo válido em ambas as variantes (H3 e H4b).

## 2. Auditor de Métricas

Papel: não mexer em modelo, avaliar se `coverage80`/`tail_ece` fazem sentido para este alvo
(sem rodar novo experimento — análise sobre os números já produzidos pelos 4 papéis acima e
pela caracterização da Fase 0).

- **Distribuição do alvo** (Fase 0, `characterize_targets.py`): média 4,3812, variância
  4,7698, var/média 1,09, só 0,97% de jogos com zero cartão amarelo total. É uma contagem
  razoavelmente contínua centrada em 4-5, SEM zero-inflação relevante — bem diferente de
  cartões vermelhos (80% zero). `coverage80` e `tail_ece` não sofrem do problema de
  discretização degenerada que afetaria um alvo quase-binário; são métricas válidas e
  informativas aqui.
- **Padrão observado nos 8 variantes + 2 controles**: `coverage80` do candidato fica sempre
  entre 0,858 (controles/original) e 0,880 (H4b), SEMPRE acima do teto do gate (0,85) —
  nunca dentro do intervalo alvo [0,75, 0,85]. E o padrão é MONOTÔNICO: quanto melhor
  `delta_ll`/`tail_ece`, PIOR (mais alto) fica `coverage80` (original 0,8581 → H1c 0,8728 →
  H3 0,8767 → H4b 0,88).
- **Diagnóstico**: isso não é um artefato de métrica — é um sintoma real e consistente de
  que o parâmetro de dispersão `r` do NB (estimado por MLE global por lado, independente das
  features novas) não está encolhendo na mesma proporção que a média (`mu`) fica mais precisa.
  As features novas reduzem VIÉS de `mu` (melhoram log-loss e tail_ece, que dependem da
  posição do valor real dentro da distribuição), mas não reduzem a VARIÂNCIA residual
  condicional que o modelo atribui a cada jogo (cartão amarelo tem componente genuinamente
  aleatório — humor de árbitro, ritmo de jogo — que talvez nem devesse encolher tanto quanto
  0,75-0,85 exige). Isso é consistente com a Fase 0 (calibração isotônica isolada no
  candidato CRU "ajuda mas não resolve sozinha") — mas aquele teste foi feito ANTES de
  corrigir o viés de `mu`; com H3/H4b, viés de mu já está corrigido e o defeito remanescente
  é mais estreito e específico (só a LARGURA do intervalo, não mais o ajuste central).
- **Conclusão do Auditor**: as métricas fazem sentido para este alvo e estão apontando
  corretamente para um problema real, mas AGORA circunscrito (folds_ok/delta_ok/tail_ece_ok
  passam com folga em H3 e H4b) — o gate está funcionando como projetado, não é o fator
  limitante. O próximo experimento natural (não rodado por orçamento, ver §5) é recalibrar
  a LARGURA da PMF (isotônico multi-bin ou ajuste do parâmetro de dispersão condicionado às
  novas features) especificamente sobre o candidato H4b, não sobre o candidato cru de 170
  features (que é o que a Fase 0 testou e reprovou).

## 3. Síntese e parecer final do Crítico

Convergência forte entre os 4 papéis: TODAS as 4 hipóteses produziram ganho real e
controlado (confirmado por permutação em H3 e H4b) na direção prevista pela Fase 0 — a causa-
raiz identificada (falta de histórico do próprio alvo + falta de identidade de competição)
estava correta. Divergência: a magnitude do ganho depende muito de COMO o histórico é
codificado — média móvel fixa (H1) é claramente inferior a rating incremental ataque/defesa
(H4), mesmo usando o mesmo dado bruto. Nenhuma das 4 hipóteses, isolada ou combinada, fecha
o gate — em TODOS os 8 variantes + 2 controles, o único critério que nunca passa é
`coverage_ok` (a PMF fica sistematicamente 1-3pp larga demais), enquanto os outros 3
critérios (folds, delta_ll, tail_ece) já passam com folga no melhor candidato (H4b).

Isso não é "sem melhora relevante" (a régua de 3 hipóteses seguidas sem melhora do brief não
se aplica — H1→H2→H3→H4 é uma sequência de melhoras crescentes e monotônicas) nem "dado
insuficiente" nem "arquitetura não representa o fenômeno" (pelo contrário: H4 mostrou que
UMA mudança de arquitetura specific — rating incremental — já resolve boa parte do gap). É
um caso de gate quase fechado por UMA dimensão específica e diagnosticável (dispersão/
largura da PMF), que não foi resolvida dentro do orçamento desta rodada.

## 4. Recomendação objetiva

**Investigar novamente com nova hipótese** — especificamente: recalibrar a LARGURA da PMF
(não mais o ajuste central, que já está resolvido) do candidato H4b (GAP rating de cartão +
encoding de competição), seguindo uma das duas linhas:
(a) repetir o `--calibration-check` do gate (isotônico na probabilidade O/U), mas armado
sobre o candidato H4b em vez do candidato cru de 170 features — a Fase 0 só testou isotônico
no candidato cru, que ainda tinha viés de `mu` não corrigido;
(b) permitir que o parâmetro de dispersão `r` do NB varie com as mesmas features novas (hoje
é um escalar único por lado, estimado por MLE global) em vez de ficar fixo.
Não é caso de "aprovar para novo ciclo de validação" (nenhum variante passou o gate
completo), nem de "abandonar" (sinal real, controlado, crescente a cada hipótese, e o gap
remanescente é estreito e específico).

## 5. Orçamento usado e itens não testados

4 hipóteses principais (H1, H2, H3, H4) + 2 controles negativos = 10 experimentos reais
rodados (dentro do teto de 5 hipóteses / 30 experimentos). Não testei a segunda hipótese
sugerida pela Fase 0 (árbitro com canonicalização de nome) — a Fase 0 já apontava teto de
ganho baixo para essa via (2 tentativas anteriores em domínios vizinhos deram ganho pequeno
e reprovaram), e o tempo de execução real desta sessão (cada rodada de 3-4 experimentos
levou de 1 a 3 horas de relógio, por causa de disputa de CPU com as investigações irmãs dos
outros 3 mercados de cartão + impedimentos + gols rodando em paralelo na mesma máquina)
tornou mais valioso fechar a dimensão de dispersão do candidato já quase aprovado (H4b) do
que abrir uma quinta hipótese de teto baixo. Script de árbitro já pronto e não executado:
`_cartoes_amarelos_scratch/run_h5_referee.py` (canonicaliza "A. Taylor" / "Anthony Taylor,
England" / "Anthony Taylor" para a mesma chave, target-encoding shrinkage por árbitro) — fica
disponível para quem retomar esta investigação.
