# Cluster A — investigação compartilhada dos 4 mercados de cartão de clube (Fase 0, PLANO 8)

Data: 2026-07-31. Escopo: `cartoes_amarelos`, `cartoes_vermelhos`, `cartoes_1t`, `cartoes_2t` — todos
`scope="clube"`. Todos os números abaixo vêm de comandos reais rodados nesta sessão (scripts em
`backend/data/reports/investigacao_multiagente/_cluster_a_scratch/`: `characterize_targets.py`,
`referee_coverage.py`, `inspect_folds.py`) ou de arquivos já existentes em
`backend/data/reports/gate_mercados/`. Nenhuma chamada à API-Football, nenhum blob do Neon lido em
runtime, nada escrito em `model_artifacts_clubes/`.

**Nota de execução**: esta sessão rodou isolada num worktree git; os dados locais
(`backend/data/*`, gitignored) e o venv só existem no checkout principal
(`C:\Users\operadorsge\Desktop\Projetos\previsao-jogos`), então todos os comandos abaixo apontaram
pra lá via caminho absoluto (leitura apenas). Este relatório e os scripts de diagnóstico foram
gravados nos DOIS lugares — no checkout principal (onde os agentes de mercado provavelmente vão
rodar) e neste worktree (por exigência de isolamento da ferramenta de escrita).

## 0. Checagem de histórico (regra de ouro — não repetir teste já feito)

`DOCUMENTACAO_CENTRAL.md` já tem 3 experimentos relevantes fechados, todos REPROVADOS:

1. **§9, linha 506-507** — `exp15_referee_cards.py`: `ref_strictness` (rigor médio do árbitro) como
   feature extra num modelo de TOTAL de cartões, mas em **escopo SELEÇÃO**. dNLL +0,007, 3/7 folds —
   REPROVADO, "cartão idiossincrático".
2. **§8, linha 333-335** — prop "jogador a levar cartão" (seleção): AUC 0,62 (base 0,59), abaixo do
   padrão de props ofensivos (~0,74). Não promovido.
3. **§17.6, linha 1334-1338** — combinação #3, prop de jogador + árbitro, **escopo CLUBE** (amostra
   maior): AUC com-árbitro 0,6328 vs sem-árbitro 0,6301 (ganho +0,0026, 4/4 folds) — ainda abaixo do
   piso de promoção (AUC≥0,68). REPROVADO.

**Lacuna real que restava**: nenhum desses testou árbitro num modelo de **TOTAL de cartões por
equipe** (o alvo dos 4 mercados atuais) em **escopo CLUBE**. Essa lacuna foi investigada abaixo
(§1.5). Fora isso, não repeti nenhum experimento já feito.

## 1. Causas COMUNS aos 4 mercados

### 1.1 — CONFIRMADA: o candidato não usa NENHUMA feature de histórico de cartão

`base_feats_170()` (as mesmas 170 features de produção usadas por `CornersNB` nos 4 mercados, lidas
de `model_artifacts_clubes/meta.json`) **não contém nenhuma coluna com "card", "yellow" ou "red" no
nome**. A única coisa relacionada a disciplina são 6 colunas de FALTAS
(`home/away/diff_style_fouls_suff_ratio_l5/l10`).

Só que as colunas de rolling de cartão **existem no parquet de treino**
(`data/built/club_features_enriched.parquet`) e não são usadas:

| coluna (não está em base_feats_170) | cobertura | corr. de Pearson com o alvo real do próximo jogo |
|---|---|---|
| `home/away_sb_yellow_l5` (soma) | 54,6-54,7% | **r = 0,239** |
| `home/away_sb_cards_l5` (soma) | 54,6-54,7% | **r = 0,239** |
| `home/away_sb_red_l5` (soma) | 54,6-54,7% | r = 0,052 |

Em contraste, a correlação média das 170 features de produção com `cards_total` é **|r| = 0,019**, e
a MAIOR correlação individual entre as 170 é `pace_total` com **r = -0,074** — quase 3x mais fraca
que a feature de histórico de cartão que está sendo ignorada. Rodei correlação de todas as 170
contra o alvo (`characterize_targets.py`); nenhuma passa de 0,074.

**Caso de contraste dentro do próprio gate**: o mercado `faltas` (mesma arquitetura `CornersNB`,
mesmo `base_feats_170`) **PASSOU o gate 5/5 folds** (`RESUMO_clube.json`) — e é o único mercado de
contagem "disciplinar" cujo histórico relevante (`style_fouls_suff_ratio`) **está** dentro de
`base_feats_170`. Isso é evidência direta de que a arquitetura funciona quando a feature histórica
do próprio alvo está presente, e falha quando não está.

### 1.2 — CONFIRMADA: nenhuma feature de identidade de competição/liga

`base_feats_170` só tem `tournament_weight` (peso de amostragem, não identidade) e `is_competitive`
(flag) — nenhum dummy ou target-encoding de `tournament`. A heterogeneidade real entre ligas é
grande:

- Média global de `cards_total`: 4,61. Desvio-padrão das médias POR competição (61 competições com
  ≥200 jogos): **0,72** (~16% da média).
  - Menos cartões: J1 League 2,69 / Eliteserien 3,27 / FA Cup 3,29 / Eredivisie 3,44.
  - Mais cartões: Primera A 6,07 / Segunda Liga 5,57 / Primera División 5,52 / Primera División
    (Apertura) 6,30.
- Um modelo ingênuo "preveja a média da competição" já explica **R² = 0,0902** da variância total —
  mais do que qualquer combinação das 170 features de produção consegue capturar implicitamente via
  Elo/GAP ratings.

Isso explica diretamente por que o baseline **B2** (NB por média de competição) é o "melhor
baseline" em **19 dos 20 folds** across os 4 mercados (`inspect_folds.py` sobre os CSVs de
`gate_mercados/`) — B2 não tem NENHUM sinal específico de time, só a média da liga, e ainda assim
bate o candidato de 170 features quase sempre.

### 1.3 — CONFIRMADA: calibração isotônica sozinha NÃO resolve

O próprio gate já testa isso (`--calibration-check`, reaproveitado, não é experimento novo desta
sessão — mas vale reportar porque descarta uma hipótese alternativa): calibrar o candidato cru com
isotônico (80% fit / 20% calibração, cronológico) e comparar contra o baseline:

| mercado | folds calibrado bate baseline |
|---|---|
| cartões amarelos | 0/5 |
| cartões vermelhos | 2/5 |
| cartões 1º tempo | 0/5 |
| cartões 2º tempo | não rodado (falta o `.json`; ver §2) |

Conclusão nos 3 rodados: "calibração ajuda mas não resolve sozinha — o candidato cru realmente perde
em ajuste, não só em calibração". Isso é consistente com §1.1/§1.2: o problema é FEATURE ausente,
não miscalibração de dispersão.

### 1.4 — PROVÁVEL REFUTAÇÃO: overdispersão extrema não é o driver

Caracterizando o alvo diretamente (`characterize_targets.py`, `load_clubs_df(min_matches=5)`):

| mercado | n | média | variância | var/média | % jogos com 0 |
|---|---|---|---|---|---|
| amarelos (total) | 144.295 | 4,3812 | 4,7698 | 1,0887 | 0,97% |
| vermelhos (total) | 144.295 | 0,2312 | 0,2567 | 1,1107 | **80,24%** |
| cartões total | 144.295 | 4,6124 | 5,5801 | 1,2098 | 0,79% |
| cartões 1º tempo | 143.848 | 1,6347 | 1,8621 | 1,1391 | 21,72% |
| cartões 2º tempo | 143.848 | 3,0532 | 3,6865 | 1,2074 | 5,32% |

Razão var/média entre 1,09 e 1,21 — sobredispersão real, mas **modesta**, do tipo que o
method-of-moments do NB (usado tanto pelo candidato quanto pelos 3 baselines) já lida bem. Não é
"sobredispersão extrema não capturada" — os baselines, que usam a MESMA família NB, vencem o
candidato de qualquer forma. Isso aponta o problema pra falta de covariável preditiva (§1.1/§1.2),
não pra má especificação da distribuição de contagem.

### 1.5 — INCONCLUSIVA / PROVÁVEL TETO BAIXO: identidade de árbitro

Achado do CLAUDE.md (`_build_referee_table` em `predictor_service.py` degrada vazio p/ clube) está
CONFIRMADO, mas é um gap de **endpoint de exibição** (`/api/referees/{name}/stats`, sem parâmetro de
`scope`, só lê `match_detail_cache` de seleção) — não afeta o treino do modelo, já que nenhum dos
dois escopos usa árbitro como feature de treino em `base_feats_170` hoje.

Investigação nova desta sessão sobre o DADO BRUTO (`club_raw_cache.sqlite`, tabela `raw`, campo
`fixture.referee`):

- Cobertura no cache bruto inteiro (385.109 linhas): 64,68% não-nulo.
- Cobertura **nas linhas efetivamente usadas no gate de cartões** (join por `fixture_id` com o
  dataset de treino, n=144.295): **98,39%** — bem mais alta, porque essas linhas já passam pelo
  filtro de `has_advanced_stats`-like que também favorece jogos com dado completo.
- **Problema real de identidade confirmado**: mesmo árbitro (Anthony Taylor) aparece sob 3 strings
  diferentes no cache: `"A. Taylor"` (246 jogos), `"Anthony Taylor, England"` (213 jogos),
  `"Anthony Taylor"` (3 jogos). A normalização já usada em produção
  (`predictor_service.py:1056`, `ref.split(",")[0].strip()`) resolve só o sufixo de país
  ("Anthony Taylor, England" → "Anthony Taylor"), mas **não** funde "A. Taylor" com "Anthony
  Taylor" — seriam tratados como árbitros diferentes se usados hoje como feature categórica.
- 5.314 nomes distintos (após normalização por vírgula) em 144.295 jogos → **mediana de 10 jogos por
  árbitro** (amostra rasa pra maioria — mesmo padrão "amostra rasa" citado no doc-mestre §9 pra
  seleção), mas os árbitros mais frequentes (majoritariamente brasileiros, ex.: Anderson Daronco 329
  jogos, Wilton Pereira Sampaio 302) têm amostra bem mais funda.

Não dá pra concluir "árbitro não ajuda em cartão de EQUIPE de clube" porque **isso nunca foi
testado** (só foi testado em seleção-equipe e clube-jogador, ambos reprovados por margem pequena).
Mas as 2 evidências anteriores + o problema de identidade não resolvido tornam razoável esperar um
teto de ganho baixo, não um "sinal forte esperando pra ser capturado".

## 2. Causas que PARECEM específicas de um mercado só

- **Vermelhos**: 80,2% dos jogos têm zero cartão vermelho — evento genuinamente raro/quase
  degenerado. A correlação da feature de histórico rolling (`red_l5`) com o alvo real é muito mais
  fraca (r=0,052) que a de amarelos/total (r=0,239) — rolling mean simples captura menos sinal em
  eventos raros. É o único mercado com 1/5 fold "melhora" (não 0/5) e com tail_ece absoluto pequeno
  em ambos candidato/baseline (0,0100 vs 0,0086) — a reprovação é real mas de magnitude menor que
  nos outros 3. Não espere que adicionar `red_l5` sozinho resolva tão bem quanto em amarelos.
- **Amarelos e 2º tempo**: pior desempenho relativo (0/5 folds melhoram, delta_ll médio +0,018 e
  +0,016 — os 2 piores dos 4). Como a feature de histórico ausente (`yellow_l5`/`cards_l5`, r=0,239)
  é a mesma ordem de grandeza pros dois, isso sugere que o teto de ganho ao corrigir §1.1/§1.2 é
  proporcionalmente MAIOR nesses dois do que em vermelhos.
- **1º e 2º tempo (halftime)**: o próprio GATE tem uma lacuna estrutural só nesses dois — a função
  `_roll_cols()` em `gate_count_market.py` (regex `home_cur_sb_(\w+)`) não casa com os nomes dos
  alvos de meio-tempo (`home_cards_1t`/`home_cards_2t`), então o baseline **B1 nunca é calculado**
  pra esses dois mercados (confirmado: `cartoes_1t_clube.csv`/`cartoes_2t_clube.csv` só têm colunas
  `ll_B0`/`ll_B2`, sem `ll_B1`; `cartoes_amarelos_clube.csv`/`cartoes_vermelhos_clube.csv` têm as
  três). Isso não muda o veredito (B2 já reprova o candidato de qualquer forma), mas significa que
  não sabemos se um baseline "rolling por tempo" também bateria o candidato — registrado como
  **Inconclusiva, falta dado**: não confirmei se existe uma coluna de rolling de cartão específica
  de 1T/2T no parquet (a investigação desta sessão olhou só o rolling do jogo inteiro).
- **1º tempo** também tem fração de zero bem mais alta (21,7%) que 2º tempo (5,3%) — mais massa
  perto de zero, mercado potencialmente mais sensível a erro de especificação de cauda perto do
  zero do que os outros.
- **Gate `cartoes_2t_clube_calibracao.json` não existe** (só `1t`/`amarelos`/`vermelhos` têm o
  check de calibração rodado) — lacuna de execução, não de causa; um agente de mercado de 2T deveria
  rodar `python -m scripts.gate_count_market --market cartoes_2t --scope clube
  --calibration-check` antes de mais nada, só pra fechar essa mesma checagem que os outros 3 já têm.

## 3. Recomendação concreta pros 4 agentes de mercado (Fase 1)

**Ordem de prioridade, do maior pro menor teto de ganho esperado (evidência numérica acima):**

1. **Adicionar histórico rolling do PRÓPRIO alvo ao candidato** (`home/away_sb_yellow_l5` pra
   amarelos, `home/away_sb_cards_l5` pra total/1T/2T, `home/away_sb_red_l5` pra vermelhos — já
   existem no parquet, nunca foram passadas ao `CornersNB`). É o teste #1 pros 4 agentes, na ordem:
   amarelos e 2T primeiro (r=0,239, maior teto), depois total, depois 1T (checar se falta variante
   "por tempo" da coluna — se não existir, usar o rolling do jogo inteiro como proxy e registrar a
   limitação), por último vermelhos (r=0,052 — esperar ganho bem menor, é o mercado onde a correção
   tem menos chance de sozinha aprovar no gate).
2. **Adicionar identidade de competição** (target-encoding de `tournament` com shrinkage bayesiano
   — a média crua por liga já dá R²≈9% e bate o candidato em 19/20 folds; um encoding regularizado
   deve capturar isso sem overfit nas ligas com poucos jogos). Testar 1+2 juntos primeiro (é
   provável que sejam aditivos, já que capturam fontes de variância diferentes — time vs liga).
3. **Só depois de 1+2**, testar árbitro — E só nos mercados amarelos/vermelhos/total (cobertura
   98,4% nas linhas do gate). Pré-requisito: resolver a duplicidade de identidade (normalizar além
   do split por vírgula — ex. casar por sobrenome + iniciais, ou fuzzy-match) antes de usar como
   categórica, senão o mesmo árbitro conta como 2+ árbitros diferentes e dilui o pouco sinal que
   existe. Gerenciar expectativa: as 2 tentativas anteriores (seleção-equipe e clube-jogador) deram
   ganho pequeno e reprovaram — não é o item de maior ROI esperado.
4. **Não repetir calibração isotônica isolada como solução** — já testado 3x nesta rodada, não
   resolve sozinho. Só reaplicar calibração DEPOIS que 1+2 melhorarem o ajuste cru (delta_ll
   negativo e consistente).
5. **1T/2T**: antes de mais nada, rodar um B1 justo (rolling por tempo, se o dado existir) pra saber
   se o "REPROVADO" atual seria robusto contra um baseline mais forte — hoje só foi comparado contra
   B0/B2.
6. **Vermelhos**: dado o teto baixo de r=0,052 pro histórico rolling simples, se 1+2 não bastarem
   pra aprovar, vale considerar (fora do escopo desta investigação, é decisão de produto/modelagem
   do agente de mercado) um approach diferente de "rolling mean" pra evento raro — ex. taxa
   suavizada por Beta-Binomial/Empirical Bayes por time, já que média rolante simples é ruim pra
   eventos com 80% de zero.

## 4. Arquivos gerados nesta investigação

- `backend/data/reports/investigacao_multiagente/_cluster_a_scratch/characterize_targets.py` —
  estatística do alvo, correlação features-histórico vs alvo, correlação das 170 features de
  produção vs alvo, heterogeneidade por competição (R²).
- `backend/data/reports/investigacao_multiagente/_cluster_a_scratch/referee_coverage.py` —
  cobertura de árbitro no cache bruto vs nas linhas do gate, duplicidade de identidade (caso
  "A. Taylor" / "Anthony Taylor, England" / "Anthony Taylor").
- `backend/data/reports/investigacao_multiagente/_cluster_a_scratch/inspect_folds.py` — replay dos
  CSVs por fold já existentes em `gate_mercados/`, extraindo qual baseline (B0/B1/B2) vence em cada
  fold dos 4 mercados.
- Nenhum artefato de produção foi tocado; nenhuma chamada de API foi feita.
