# gols_1t (clube) — Fase 1 do PLANO 8

**Status no gate cru:** REPROVADO só por `coverage_ok=false` (`coverage80_medio=0.9472`, fora de
`[0.75,0.85]`). `folds_ok`, `delta_ok` e `tail_ece_ok` todos `true` — `delta_ll_medio=-0.00455`
(5/5 folds melhoram) e `tail_ece` candidato 0.0064 já é **melhor** que o baseline (0.0120). Fonte:
`backend/data/reports/gate_mercados/gols_1t_clube.json`. Follow-up de calibração isotônica de 1
linha (`gols_1t_clube_calibracao.json`): 4/5 folds batem o baseline na Bernoulli-LL da linha
mediana, mas isso não recalcula `coverage80`/`tail_ece` completos (ver H3 abaixo — por quê isso
não resolve o critério que reprovou).

**Herança da Fase 0** (`backend/data/reports/investigacao_multiagente/cluster_b.md`): coverage80
é estruturalmente inalcançável para `mu_total≈1,08` — simulação com os parâmetros REAIS de
produção (`model_artifacts_clubes/gols_1t_nb.joblib`: `r_H_=1000.0`, `r_A_=396.14`, teto do MLE)
já dá `coverage80=0,9034` mesmo com dados gerados pelo modelo perfeitamente especificado.
Recomendação herdada: propor emenda ao gate §6-C. Meu papel aqui era **validar isso com rigor
adicional** (não só aceitar), fechando as duas lacunas que o cluster_b deixou explicitamente
abertas: (1) se algum r/reparametrização escapa do teto no `mu` real e exato de `gols_1t`
(o cluster_b usou grid genérico, simétrico); (2) se o gap residual (0,9034 teórico vs 0,9472 real,
0,044) é heterogeneidade de `mu` entre jogos ou algo não explicado.

**Ambiente:** este ambiente não tem `data/built/club_halftime_targets.parquet` /
`club_features_enriched.parquet` nem `data/club_raw_cache.sqlite` disponíveis para este agente
(mesma limitação já registrada pelo cluster_b). Todo experimento abaixo é simulação a partir dos
parâmetros REAIS do artefato de produção (`model_artifacts_clubes/gols_1t_nb.joblib`, leitura),
reaproveitando `research_clubs.protocol.coverage80` sem reimplementar. Script único:
`backend/data/reports/investigacao_multiagente/_gols_1t_scratch/gols_1t_investigacao.py`
(seed fixa `20260731`, igual ao cluster_b, para comparabilidade). Saídas brutas:
`h1_r_grid_fino.csv`, `h2_heterogeneidade_mu.csv`, `h5_curva_fina_mu.csv`,
`resultado_gols_1t.json`, todos na mesma pasta `_gols_1t_scratch/`.

---

## Parecer do Crítico (primeiro, antes de qualquer experimento novo)

Revisão de `DOCUMENTACAO_CENTRAL.md` §8/§9/§13/§16/§17/§19/§25 + `cluster_b.md` +
`gols_1t_clube_calibracao.json`: **não há histórico de teste específico de gols_1t antes do
cluster_b** — o mercado só nasceu no §16 (2026-07-19, 1º/2º tempo pra clube) e foi ao gate §6-C
pela primeira vez nesta bateria. Dois testes já feitos e que **não devem ser repetidos**:
(a) dispersão do `r` — já no teto do MLE (1000.0), refutando "modelo superestima dispersão";
(b) calibração isotônica pontual da linha mediana — melhora a Bernoulli-LL de 1 corte, mas não
recalcula `coverage80`/`tail_ece` completos (o próprio JSON do calibration-check reconhece isso
implicitamente: só testa 1 `line`, não a PMF inteira). Não repeti nenhum dos dois. Direcionei o
orçamento para os dois pontos que o cluster_b deixou como "Provável, não testável" ou
"Inconclusiva" por falta do parquet: teto estrutural no `mu` EXATO (não genérico) e a origem do
gap residual.

---

## H1 (Auditor de Métricas) — r-grid fino no `mu_total` exato de gols_1t

**Motivação:** o cluster_b testou um grid genérico e SIMÉTRICO (`r_H=r_A`) em pontos de `mu_total`
redondos (0.5, 1.0, 1.5, 2.0...). `gols_1t` tem `mu_total=1,0845` exato e `r` fortemente
ASSIMÉTRICO na produção (`r_H_=1000,0` vs `r_A_=396,14`, razão ≈2,52). Precisava confirmar que o
teto estrutural se sustenta especificamente nesse ponto e nessa assimetria — não é óbvio que a
assimetria não abra uma janela que o grid simétrico não veria.

**Experimento:** 23 valores de `r` (0,1 a 1e6) aplicados simetricamente (`r_H=r_A=r`) no
`mu_total` real (split home/away 57,3%/42,7%, igual à produção); mais 13 valores de um
multiplicador `alpha` (0,001 a 1000) aplicado à assimetria REAL (`r_H=1000·alpha`,
`r_A=396,14·alpha`) — preserva a razão real entre os dois lados. 200k amostras/ponto, PMF exata
via `nbinom` + convolução (replica `CornersNB._marginal_pmf`/`predict_distributions`
byte-a-byte). `coverage80` chamado direto de `research_clubs.protocol`.

**Resultado:**

| modo | min coverage80 | max coverage80 | algum r no alvo [0,75,0,85]? |
|---|---|---|---|
| simétrico no r (23 pontos) | 0,9006 | 0,9710 | **não** |
| assimetria real escalada (13 pontos) | 0,9019 | 0,9697 | **não** |
| ponto exato de produção (r_H=1000, r_A=396,14, N=1e6) | 0,9039 | — | — |

**Controle negativo:** o ponto exato de produção (0,9039) reproduz o número do cluster_b (0,9034)
dentro do ruído de Monte Carlo (diff=0,0005) — confirma que a reimplementação está correta antes
de generalizar.

**Classificação: Confirmada.** Do `r=0,1` (super-disperso) ao `r=1e6` (quase-determinístico),
**nenhum** ponto do espectro de dispersão entra em `[0,75,0,85]` no `mu_total` real — nem na
assimetria observada de fato na produção. O teto estrutural do cluster_b se sustenta com rigor
adicional (grid mais fino, ponto exato, assimetria real preservada).

---

## H2 (Auditor de Métricas) — heterogeneidade de `mu` entre jogos explica o gap residual?

**Motivação:** o cluster_b§4 ficou **Inconclusiva** sobre por que o real observado (0,9472) é
0,044 MAIOR que o teórico de `mu` fixo (0,9034) — falta do parquet bloqueou testar a correlação
1T×2T e a heterogeneidade real de `mu` entre partidas. Esse resíduo é exatamente o tipo de coisa
que, se não explicado, deixaria a porta aberta pra "então talvez SEJA erro de ajuste depois de
tudo". Reformulei o teste de um jeito que não depende do parquet: simular heterogeneidade
diretamente, com a MESMA arquitetura da produção (`r_H`, `r_A` GLOBAIS e fixos — é assim que
`CornersNB` funciona de verdade, só `lambda` varia por linha via GBM).

**Experimento:** cada "jogo" sorteia seu próprio `mu_total_i` de uma log-normal com média igual ao
`mu_total` real de produção (1,0845) e CV alvo variando de 0 a 1,3; split home/away fixo na
proporção real (57,3%/42,7%); `y_i` gerado da NB verdadeira daquele jogo (`r_H`, `r_A` fixos,
`mu_h_i`/`mu_a_i` variando); `coverage80` calculado com a **PMF condicional corretamente
especificada por linha** (convolução por jogo, vetorizada via `scipy.signal.fftconvolve` —
150k jogos/ponto) — ou seja, um modelo "oráculo heterogêneo": tão bem especificado quanto o
oráculo de `mu` fixo do cluster_b, mas agora respeitando que jogos reais têm `mu` diferentes entre
si (times diferentes, mandantes diferentes).

**Resultado:**

| CV de mu_total entre jogos | coverage80 |
|---|---|
| 0,00 (degenerado = mu fixo) | 0,9039 |
| 0,15 | 0,9405 |
| 0,30 | 0,9448 |
| 0,45 | 0,9448 |
| 0,60 | 0,9422 |
| 0,80 | 0,9413 |
| 1,00 | 0,9427 |
| 1,30 | 0,9444 |

**Controle negativo:** CV=0 reproduz o número de H1/cluster_b (0,9039 vs 0,9034, diff=0,0005) —
confirma que a implementação da versão heterogênea colapsa corretamente no caso degenerado.

**Classificação: Provável (forte).** Introduzir QUALQUER heterogeneidade realista de `mu` entre
jogos (CV de 15% a 130%, faixa ampla e plausível para gols esperados por partida — times de forças
muito diferentes, mandante/visitante) já explica praticamente todo o gap residual: salta de 0,9039
(mu fixo) para ~0,94-0,945 (heterogêneo), a **0,0024-0,0033 de distância** do real observado
(0,9472) — contra 0,044 sem heterogeneidade. O efeito satura rápido (já em CV=0,15 quase todo o
gap fecha) e é **insensível ao CV exato** (0,9405 a 0,9448 do CV=0,15 ao CV=1,30) — não é um
ajuste fino frágil, é um patamar estável. **Não pude confirmar com 100% de certeza porque não há
o parquet real pra medir o CV verdadeiro de `mu_total` entre partidas de gols_1t** (fica
"Provável", não "Confirmada" formal) — mas o mecanismo é o candidato muito mais forte que
qualquer hipótese de erro de ajuste: o resíduo desaparece assim que se modela heterogeneidade
genuína de `mu`, com um modelo que continua sendo "perfeitamente especificado" (candidato==gerador
por jogo). Isso fecha, na prática, a lacuna que o cluster_b§4 deixou aberta — **sem precisar do
`club_halftime_targets.parquet`.**

---

## H3 (Proponente de Arquitetura + Proponente de Dados) — reparametrização da NB / feature de
## redução de variância / recalibração multi-quantil: algum ajuda?

**Motivação (tarefa pedia testar os três):** (a) reparametrização da NB — já respondida
numericamente por H1: o r-grid cobre de determinístico a super-disperso e nunca escapa do teto;
(b) feature nova que reduza a variância prevista (ex.: "jogo decidido cedo", H2H de gols-1T do
confronto) — **não testável neste ambiente: exigiria `club_halftime_targets.parquet` (ausente)
para treinar/avaliar qualquer feature nova.** Não fabriquei dado sintético fingindo ser feature
real — seria inventar sinal, contra a regra de nunca fabricar evidência. Mas o argumento
estrutural de H1 já a torna irrelevante mesmo se existisse: o extremo `r→1e6`
(quase-determinístico, equivalente ao limite teórico de uma feature de redução de variância
PERFEITA) ainda fica em ~0,90-0,97 de coverage80, não em [0,75,0,85] — reduzir variância ainda
mais não muda a ordem de grandeza do problema, que é a granularidade discreta da PMF em si, não a
variância mal estimada; (c) recalibração isotônica multi-quantil + gate §6-C completo —
argumento formal: o cenário de "calibração perfeita" já FOI simulado em H1/cluster_b como o caso
`candidato==gerador verdadeiro` (a simulação gera dados da MESMA distribuição que a PMF assume,
que é estritamente melhor do que qualquer calibração pode alcançar — nenhum calibrador pode tornar
o modelo mais preciso que o próprio processo gerador dos dados). Como esse "melhor caso possível"
já fica em 0,9034-0,9039 (fora do alvo), nenhuma calibração — de 1 linha ou de todos os quantis
simultaneamente — pode fazer melhor. Não precisei re-rodar o gate completo com o parquet ausente
para provar isso: é uma consequência lógica direta do resultado numérico de H1.

**Classificação:**
- Reparametrização de NB: **Refutada** (H1, numérico).
- Feature de redução de variância: **Depende de nova coleta** para teste empírico direto, mas
  **Refutada por argumento estrutural** (dominada pelo limite `r→1e6` de H1) — não vale a pena
  gastar orçamento de coleta nisso.
- Recalibração multi-quantil: **Refutada** (argumento lógico apoiado em H1 — o teto do "melhor
  caso possível" já reprova).

---

## H5 (Auditor de Métricas) — curva fina de coverage80-alcançável por `mu_total` (para o gate §6-C)

**Motivação:** a tarefa pede uma curva completa (não só um ponto) que o dono possa avaliar como
critério substituto. O cluster_b já tinha uma tabela grossa (mu redondos, 0,5 a 30); refinei ao
redor da faixa relevante (0,5 a 10, com o ponto exato 1,0845 incluído) usando o mesmo r-sweep
(16 valores, 0,3 a 1e6) em cada `mu_total`, 80k amostras/combinação (272 simulações).

**Resultado** (`h5_curva_fina_mu.csv`; tabela completa lá — resumo abaixo):

| mu_total | min | mediana | max | algum r no alvo? |
|---|---|---|---|---|
| 0,50 | 0,9009 | 0,9087 | 0,9739 | não |
| 1,00 | 0,9016 | 0,9186 | 0,9541 | não |
| **1,08 (gols_1t real)** | **0,9000** | **0,9047** | **0,9711** | **não** |
| 2,00 | 0,9118 | 0,9420 | 0,9483 | não |
| 2,50 | 0,8476 | 0,8768 | 0,9381 | sim (pontos frágeis) |
| 4,00 | 0,8438 | 0,8596 | 0,9241 | sim (pontos frágeis) |
| 7,00 | 0,8187 | 0,8566 | 0,8959 | sim (mediana quase no alvo) |
| 10,00 | 0,8061 | 0,8400 | 0,8931 | sim (mediana robusta) |

Primeiro `mu_total` com ALGUM `r` no alvo: **2,5** (mas frágil — só pontos isolados de `r`, não a
maioria do grid, mesmo padrão já visto pelo cluster_b). Primeiro `mu_total` com a MEDIANA do
r-sweep dentro do alvo (critério mais robusto, menos sensível a um `r` de sorte): **10,0** — com
`mu=7` já perto (mediana 0,8566, marginalmente acima de 0,85). Isso é consistente com a âncora
externa do cluster_b (`faltas`, `mu_total≈25`, `coverage80` real=0,8017, ÚNICO mercado de contagem
aprovado no gate) e com o padrão qualitativo reportado lá (2,5-5 frágil, 7-30 robusto) — meu grid
mais fino não muda o veredito, só aperta a margem de erro.

**Nota de ruído:** a "mediana" por `mu_total` usa um r-sweep de 16 pontos discretos — não é uma
estatística populacional contínua, é sensível a exatamente quais `r` caem no grid (por isso a
leve não-monotonicidade entre `mu=1,5` e `mu=2,0`, por exemplo). Suficiente para uma proposta de
LIMIAR aproximado, não para uma fórmula fechada com casas decimais de confiança.

---

## Parecer do Auditor de Métricas — proposta concreta para o gate §6-C

Baseado em H1+H5 (e na âncora `faltas` herdada do cluster_b), proponho uma tabela de decisão por
faixa de `mu_total` para substituir o teto fixo `coverage80 ∈ [0,75,0,85]` universal:

| faixa de `mu_total` | coverage80 é critério válido? | recomendação |
|---|---|---|
| `< 2,5` (gols_1t está aqui: 1,08) | **Não — estruturalmente inalcançável** (H1: nenhum r no espectro inteiro escapa de ~[0,90,0,97]) | descartar coverage80, aprovar só com `folds_ok`+`delta_ok`+`tail_ece_ok` |
| `2,5` a `~7` | Alcançável só em pontos frágeis e isolados de r — não confiável como gate binário | manter como **informativo**, não eliminatório; ou usar a faixa auto-consistente por simulação (opção já sugerida pelo cluster_b) em vez do teto fixo |
| `≥ ~7-10` | Funciona como pretendido (mediana do r-sweep entra no alvo; validado externamente por `faltas`, mu≈25, aprovado) | manter o teto fixo `[0,75,0,85]` como está hoje |

Sob essa tabela, **gols_1t (mu=1,08) seria APROVADO hoje** — bate os outros 3 critérios
(`folds_ok`, `delta_ok`, `tail_ece_ok`) com folga (tail_ece candidato 0,0064 é praticamente metade
do baseline 0,0120).

---

## Síntese e recomendação final

**Convergência:** todos os quatro papéis chegam à mesma conclusão — o cluster_b estava certo, e
o rigor adicional (grid fino no `mu` e assimetria exatos, heterogeneidade simulada, argumento
lógico de teto sob calibração perfeita) só reforça o achado, sem contradizê-lo em nenhum ponto.
Não houve divergência entre papéis nesta investigação.

**Achados novos desta Fase 1** (além de confirmar a Fase 0):
1. O teto estrutural se sustenta especificamente no `mu_total` e na assimetria REAIS de `gols_1t`
   (H1) — não é um artefato do grid genérico simétrico do cluster_b.
2. O gap residual de 0,044 entre teórico-mu-fixo e real observado é **praticamente todo explicado
   por heterogeneidade de `mu` entre jogos** (H2: ~0,94-0,945 com heterogeneidade realista vs
   0,9472 real, gap residual final ~0,003) — sem precisar do parquet, fechando a lacuna que o
   cluster_b§4 deixou como Inconclusiva.
3. Nem reparametrização de dispersão, nem uma hipotética feature de redução de variância, nem
   recalibração isotônica multi-quantil podem resolver o problema — todos os três são dominados
   pelo mesmo teto estrutural (H1/H3).
4. Proposta concreta de tabela de limiar por `mu_total` para o gate §6-C (H5 + Auditor), com
   `gols_1t` claramente na faixa "coverage80 não é critério válido".

**Classificação geral do mercado gols_1t: limitação do gate, não do modelo.** O candidato já bate
3 dos 4 critérios com folga, e o 4º (coverage80) reprova por um viés matemático da própria métrica
em contagens de média baixa (~1 gol/tempo) que nenhuma mudança de modelo, feature ou recalibração
pode corrigir.

**Recomendação final: limitação do gate §6-C** (não "investigar novamente", não "depende de nova
coleta", não "depende de mudança arquitetural", não "abandonar"). Concretamente: o dono deveria
adotar a tabela de limiar por `mu_total` (ou a alternativa mais simples do cluster_b — descartar
coverage80 abaixo de `mu≈2,5-5` e manter só `tail_ece`) e, sob essa emenda, **aprovar gols_1t para
produção** — o modelo já passa em tudo que é testável de fato neste `mu`.
