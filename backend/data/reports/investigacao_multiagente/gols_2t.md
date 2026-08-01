# gols_2t (clube) — Fase 1, investigação de mercado (PLANO 8)

**Status herdado da Fase 0** (`cluster_b.md`): coverage80 estrutural (gap real−teórico ≈ 0,
confirmado com r/mu reais de produção mesmo sem o parquet). tail_ece pior que baseline
(0,0096 vs 0,0054) ficou **Inconclusiva** por falta de `club_halftime_targets.parquet` no
worktree da Fase 0. Hipótese de trabalho herdada: efeito de estado de jogo pós-intervalo não
capturado por features pré-jogo.

**Achado de ambiente (Fase 1):** `club_halftime_targets.parquet` **já existe** em
`data/built/` (191.392 jogos, gerado em 2026-07-19 por `build_clubs_halftime_targets.py` para
o treino de produção) — não precisou ser reconstruído, só localizado. `club_features_enriched.parquet`
também presente. Nenhum bloqueio de dado nesta fase.

Scripts e saídas brutas em `backend/data/reports/investigacao_multiagente/_gols_2t_scratch/`
(`01_correlacao_1t_2t.py/.json`, `02_gate_with_1t_feature.py`, `02b_gate_with_1t_feature_BC.py`
+ `02b_*_partial.csv`, `03_gate_arquitetura_condicional.py` — saída completa só no log do
processo, não sobrou CSV pela forma como o job foi interrompido — números abaixo replicados a
partir do stdout, `04_auditor_heterogeneidade_mistura.py/.json`). Seed fixa `20260731` em toda
simulação/embaralhamento.

**Nota operacional:** esta máquina teve *outro(s) agente(s) do PLANO 8 rodando em paralelo*
(investigação de `cartoes_1t`, confirmada via `_cartoes_1t_scratch/` no mesmo diretório de
tasks) durante boa parte desta sessão, causando SIGKILL (exit 137, "Killed") repetido nos jobs
de treino mais pesados (CornersNB com 170+ features em até 191k linhas, 5 folds × 2 lados).
Efeito prático: as variantes-controle "C" e "F" (embaralhadas) completaram 4/5 folds (faltou
o maior, `fold_0.85`, N=162.683) — todas as outras variantes (A, B, E) completaram 5/5. Todas
as conclusões abaixo usam os folds **efetivamente comparáveis** entre variante e controle (4
ou 5, sempre pareado) — não há folds faltando em um lado só de uma comparação.

---

## Papel 1 — Crítico (primeiro, evidência revisada antes de gastar orçamento)

Revisado: `DOCUMENTACAO_CENTRAL.md` §8/§9 (item 2: calibração isotônica de **uma linha** O/U já
promovida pra seleção em 2026-07-06, incluindo `gols_2t-total`; não é o mesmo problema — aqui é
a PMF inteira, escopo clube, gate §6-C), §13/§16/§17/§19/§25 (nada sobre gols_2t de clube
especificamente), `cluster_b.md` (Fase 0, resumido acima), `gols_2t_clube_calibracao.json`
(isotônico de 1 linha: "ajuda mas não resolve sozinha", 3/5 folds bate baseline) e a memória
`[[escanteios-por-tempo-2026-07-23]]`. **Conclusão do Crítico:** nenhum teste anterior usou o
placar real do 1º tempo como *feature* do modelo de 2º tempo — a lição de escanteios-por-tempo
(fração 1T/2T não é previsível a partir de Elo/GAP) é sobre **prever a fração antes do jogo**,
mecanismo diferente do testado aqui (**usar o resultado do 1T, já ocorrido**, como covariável
do 2T). Nenhuma duplicação de trabalho. Via livre para gastar orçamento nas hipóteses de dado/
arquitetura.

---

## Hipótese 1 (Proponente de Dados) — placar do 1T agregado (diff + total) como feature

**Motivação:** cluster_b.md §6.2 recomendava testar `corr(goals_1t_total, goals_2t_total)` e
`corr(|diff_1t|, var(goals_2t))` como passo barato antes de qualquer mudança de arquitetura.

**Experimento (`01_correlacao_1t_2t.py`, N=191.392):**
- corr(goals_1t_total, goals_2t_total) = **0,058** (Pearson e Spearman quase idênticos)
- corr(|diff_1t|, goals_2t_total) = **0,061**
- **Controle negativo** (|diff_1t| embaralhado vs goals_2t_total): corr = 0,0002 → confirma que
  a correlação real não é artefato de construção.
- Time que **lidera** no intervalo marca mais no 2T (média 0,822) que o time **atrás** (0,722)
  que por sua vez marca mais que times **empatados** (0,705) — gap aumenta com a vantagem
  (lidera por ≥2: 0,931 vs 0,684 de quem está atrás). Interpretação mais consistente: seleção
  (o time líder tende a ser genuinamente melhor, e essa força persiste no 2T), não "postura
  defensiva pura" — mas para o objetivo do gate (TOTAL de gols, não quem marca) o que importa é
  que a média/variância do TOTAL de gols no 2T cresce com `abs_diff_1t` (1,41→1,67 na média;
  1,40→1,61 na variância entre abs_diff_1t=0 e =3), um sinal de heterogeneidade real,
  estatisticamente detectável.

**Experimento de gate (`02_gate_with_1t_feature.py` + `02b_gate_with_1t_feature_BC.py`,
mesmos folds/baselines/CornersNB do `gate_count_market.py`, candidato B = 170 feats de
produção + `[diff_1t, goals_1t_total]`, controle C = mesmas colunas embaralhadas):

| variante | folds | delta_ll médio | tail_ece candidato | tail_ece baseline | coverage80 |
|---|---|---|---|---|---|
| A — controle/produção (replicação) | 5/5 | −0,00433 | 0,0096 | 0,0054 | 0,9466 |
| B — + placar_1T agregado | 5/5 | **−0,00545** | 0,0096 | 0,0054 | 0,9469 |
| C — controle negativo (embaralhado) | 4/5* | −0,00406 | 0,0104 | 0,0052 | 0,9469 |

*A replicação de A bateu o gate original exatamente (delta −0,00433, tail_ece 0,0096/0,0054,
cov80 0,9466) — valida a metodologia.* C usa os mesmos 4 folds de A para comparação pareada.

**Resultado:** delta_ll melhora em **5/5 folds** de B sobre A/C pareados (ganho consistente,
~0,0012 a mais de log-loss favorável) — o controle negativo C fica estatisticamente igual a A
(diferença ≈0,00003, ruído). **tail_ece não muda** (0,0096 em A e B, idêntico) — o candidato
continua **pior que o baseline** em ambas. **coverage80 não muda** (0,9466→0,9469, dentro do
ruído).

**Controle negativo:** passou — C não reproduz o ganho de B, confirmando que o sinal de B é
real (placar-1T), não artefato do pipeline.

**Classificação: Provável para delta_ll (achado real, mas não resolve o motivo da reprovação).
Refutada como solução para tail_ece e coverage80.**

---

## Hipótese 2 (Proponente de Arquitetura) — placar do 1T por lado (cru, não agregado)

**Motivação:** testar dependência entre metades de forma mais granular que o estado agregado
(diff/total) — se o próprio ataque do time no 1T ("time quente") carrega mais sinal pro 2T do
que o placar relativo.

**Experimento (`03_gate_arquitetura_condicional.py`, candidato E = 170 feats + `[home_goals_1t,
away_goals_1t]` crus, controle F = mesmas colunas embaralhadas):**

| variante | folds | delta_ll médio | tail_ece candidato | tail_ece baseline | coverage80 |
|---|---|---|---|---|---|
| E — + placar_1T por lado | 5/5 | **−0,00508** | **0,0089** | 0,0054 | 0,9469 |
| F — controle negativo (embaralhado) | 4/5* | −0,00409 | 0,0105 | 0,0053 | 0,9469 |

*comparação pareada com A nos mesmos 4 folds: A=−0,00407/0,01045, F=−0,00409/0,01045
(diferença ≈0, controle negativo limpo); E nesses 4 folds = −0,00482/0,00948.*

**Resultado:** delta_ll melhora em 5/5 folds sobre o controle (ganho ~0,0008, um pouco menor
que a versão agregada da Hipótese 1). **tail_ece melhora de forma real e distinguível de
ruído**: E=0,00948 vs F=0,01045 nos mesmos 4 folds (~9% de redução) — o controle negativo F
fica idêntico a A (0,01045 = 0,01045), confirmando que a redução de E não é artefato. **Mas a
melhora é insuficiente**: mesmo reduzido, tail_ece do candidato (0,0089 médio) continua
**~1,6× pior que o baseline** (0,0054) — não vira o critério do gate (`tece_media <=
tece_base_media`).

**Controle negativo:** passou.

**Classificação: Provável — sinal real e replicável (melhor que a Hipótese 1 em tail_ece), mas
insuficiente em magnitude para aprovar. Achado de produto (placar por lado > placar agregado
para esse efeito específico), não solução para o gate.**

---

## Hipótese 3 (Auditor de Métricas) — heterogeneidade de média (por estado de jogo) explica o tail_ece?

**Motivação:** testar se a heterogeneidade de médias observada na Hipótese 1 (mu variando de
1,41 a 1,67 conforme `abs_diff_1t`), não vista pelo modelo pré-jogo, já é suficiente para
explicar o gap de tail_ece — análogo ao que a Fase 0 fez para coverage80 (simulação de
alcançabilidade).

**Experimento (`04_auditor_heterogeneidade_mistura.py`, 200k amostras, seed 20260731):**
simulei uma mistura de NBs usando as médias/variâncias REAIS por grupo `abs_diff_1t` (0 a 4,
pesos = proporção real de cada grupo) e medi tail_ece/coverage80 de um candidato "cego" (usa
só a NB marginal da mistura, análogo ao modelo pré-jogo) contra um "oráculo" (usa a NB certa de
cada grupo, teto do que informação de estado poderia entregar).

**Resultado:** tail_ece CEGO = 0,00035 vs ORÁCULO = 0,00031 — **praticamente idênticos**, ambos
minúsculos. coverage80 idêntico nos dois (0,9363). **A heterogeneidade de média medida
empiricamente é real, mas pequena demais para explicar o gap observado no gate real (candidato
0,0096 vs baseline 0,0054 — um gap de 0,0042, dez vezes maior que qualquer coisa que essa
heterogeneidade de média produza).**

**Classificação: Refutada** — heterogeneidade de média por estado de jogo (via `abs_diff_1t`)
NÃO é o mecanismo dominante do tail_ece ruim. É consistente com o resultado empírico das
Hipóteses 1/2: mesmo entregando o placar real do 1T como feature (que deveria, por construção,
deixar o modelo "ver" esse estado), o tail_ece não se resolve — porque o problema não estava
(majoritariamente) na média não vista, e sim provavelmente na variância/dispersão condicional
mal especificada (a CornersNB ajusta `r_H_`/`r_A_` por MLE global, único por lado, independente
de X — nenhuma das features testadas, incluindo a nova, alimenta a dispersão, só os
regressores de média `lambda`/`mu`).

**Parecer sobre coverage80:** replicado em TODAS as 5 variantes testadas (A, B, C, E, F) —
0,9401 a 0,9469, sempre no mesmo intervalo estreito, **inalterado por qualquer feature nova**.
Confirma robustamente o achado estrutural da Fase 0 (nenhuma informação adicional — real ou
embaralhada — move essa métrica), independentemente do parquet real agora disponível.

---

## Parecer do Crítico (final)

3 hipóteses testadas seguidas, todas com controle negativo válido (embaralhamento nulo,
diferenciável do sinal real), nenhuma resolve o critério que reprovou o mercado (`tail_ece <=
baseline`). Regra do orçamento ("parar quando 3 hipóteses seguidas sem ganho") atingida. O
achado é honesto e não é nulo — placar do 1T é sinal real (delta_ll melhora, tail_ece do
candidato reduz ~9% com a versão por lado) — mas a magnitude fica muito aquém do necessário, e
a simulação do Auditor explica por quê: o mecanismo hipotetizado (heterogeneidade de média por
estado de jogo) não é grande o suficiente. Não vale gastar mais orçamento em variações de
feature de placar-1T (interação com elo_diff, magnitude vs sinal, etc.) — o teto está próximo
do observado em E, não vai fechar um gap de 10×.

## Parecer do Auditor de Métricas (final)

Dois problemas distintos e de naturezas diferentes coexistem em gols_2t, confirmados
independentemente nesta fase:
1. **coverage80** — estrutural, herdado da Fase 0, reconfirmado aqui em 5 variantes diferentes
   (nenhuma muda o número). Não é um problema de modelo, é limite de discretização da PMF em
   contagem baixa (mu_total≈1,4-1,7). Recomendação inalterada da Fase 0: mudar o critério do
   gate (§6-C), não o modelo.
2. **tail_ece** — real, não é artefato de coverage80 nem de heterogeneidade de média não
   observada (Hipótese 3 refutada). O candidato de produção genuinamente perde calibração na
   cauda O/U central. Placar do 1T ajuda um pouco (Hipótese 2) mas não fecha o gap. Hipótese
   mais provável remanescente, não testada aqui por estar fora do escopo de "adicionar feature
   a um regressor de média" (exigiria mexer na estimação de `r_H_`/`r_A_`, hoje MLE global
   único por lado, para condicioná-la a X ou a um subconjunto de features, ex.: fazer a
   dispersão variar com o próprio placar do 1T): dispersão condicional mal especificada.

---

## Recomendação final

**Depende de mudança arquitetural.**

Justificativa: o problema que reprovou este mercado além do estrutural (coverage80, que é
limitação de gate — ver Fase 0) é o `tail_ece`, e as três hipóteses testadas nesta fase
(placar-1T agregado, placar-1T por lado, heterogeneidade de média) demonstram de forma
consistente que **o sinal disponível via feature de média não é suficiente** — mesmo o melhor
candidato testado (E) fica 1,6× pior que o baseline. A CornersNB atual estima a dispersão
(`r_H_`, `r_A_`) por MLE global único por lado, sem condicionar em nenhuma feature — inclusive
as novas testadas aqui só entram nos regressores de média (`lambda`/`mu`), nunca na dispersão.
Um passo arquitetural genuíno (fora do escopo desta fase) seria testar `r` condicional (ex.:
por bucket de `abs_diff_1t`, ou um segundo regressor pequeno pra dispersão), o que é uma
mudança de classe de modelo, não uma feature nova. Em paralelo — mas como recomendação
secundária, já registrada e não redecidida aqui — o problema de coverage80 continua sendo,
para o dono do gate, uma questão de **limitação do gate §6-C** (calibrar o alvo por
mu_total/r ao invés de um teto fixo [0,75, 0,85]), igual à recomendação da Fase 0 para
gols_1t/impedimentos.
