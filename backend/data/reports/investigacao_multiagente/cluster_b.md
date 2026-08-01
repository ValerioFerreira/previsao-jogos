# Cluster B — coverage80 em gols_1t / gols_2t / impedimentos: modelo ou métrica?

**Fase 0 do PLANO 8.** Investigação de cluster (antes de dividir por mercado). Seed fixa
`20260731` em toda simulação. Scripts e saídas brutas em
`backend/data/reports/investigacao_multiagente/_cluster_b_scratch/`
(`inspect_models.py`, `get_median_lambdas.py`, `inspect_goal_timing.py`,
`sim_coverage_achievability.py`, `production_r_values.json`,
`production_median_lambdas.json`, `grid_achievability.csv`, `achievable_by_mu.csv`,
`impedimentos_sensibilidade.csv`, `resultado_simulacao.json`).

**Limitação de ambiente, registrada com honestidade:** este agente rodou num worktree
isolado onde `backend/data/built/*.parquet` (features, `club_halftime_targets.parquet`)
**não existe** (gitignorado, não copiado ao worktree). Não há acesso ao dataset bruto real,
só aos artefatos versionados em `model_artifacts_clubes/` (que SÃO trackeados no git) e aos
relatórios já gerados em `backend/data/reports/gate_mercados/`. Isso bloqueou o passo 4
(correlação empírica 1T×2T) — ver seção correspondente, marcado Inconclusiva. Todo o resto
foi possível com o que estava disponível, incluindo um truque legítimo para obter
lambda_home/away representativos sem o parquet (ver §2).

---

## 1. Histórico já registrado (não é o mesmo achado)

`[[escanteios-por-tempo-2026-07-23]]` (memória do projeto) e `PESQUISA_CLUBES.md` §7 cobrem
**escanteios** por tempo, não gols/impedimentos: concluíram que nenhum modelo condicional de
fração 1T/2T bate um split fixo (0.53) para escanteios, com StatsBomb como única fonte de
rótulo real (nunca em produção). **Esse achado é específico de escanteios** — o mecanismo é
"a fração do total que cai em cada tempo não é previsível com as features disponíveis", uma
pergunta de **viés/ajuste da fração**. O problema investigado aqui é outro: mesmo que a
fração/expectativa esteja bem ajustada (delta_ll favorável em 5/5 folds nos 3 mercados),
**a métrica coverage80 reprova por excesso de cobertura**, uma pergunta de **dispersão/
granularidade da PMF discreta**, não de viés de fração. Não são o mesmo problema; a lição de
escanteios (não perseguir modelo condicional de fração sem dado minuto-a-minuto) continua
válida, mas não explica o coverage80 alto observado aqui.

---

## 2. Simulação de alcançabilidade — o núcleo da investigação

`research_clubs/protocol.py::coverage80` mede: para cada linha, acha o menor `k` com
CDF≥0.10 (`lo`) e o maior `k` com CDF≤0.90 (`hi`), e testa se o valor real cai em `[lo,hi]`.
Como a PMF é discreta e o passo de probabilidade entre `k` e `k+1` fica grosso quando a
contagem é baixa, o intervalo construído assim **sempre transborda** o alvo nominal de 80% —
por definição matemática, não por erro de ajuste.

**Teste decisivo:** gerei dados sintéticos a partir da PRÓPRIA NB assumida pela arquitetura de
produção (`CornersNB`: home e away NB independentes com `r_H_`/`r_A_` reais dos artefatos
`model_artifacts_clubes/gols_{1,2}t_nb.joblib`, total = convolução) e medi o coverage80 desse
processo **perfeitamente especificado** (dado gerado pela mesma distribuição que o PMF
assume) contra o próprio PMF. `lambda_home`/`lambda_away` foram obtidos passando um `X`
totalmente `NaN` pelo pipeline de produção — o `SimpleImputer(strategy="median")` já fitado
nos dados reais de treino devolve o "jogo mediano" real, sem precisar do parquet bruto.

| mercado | r_H_ / r_A_ reais (produção) | mu_total (mediano real) | **coverage80 teórico (modelo perfeito)** | coverage80 REAL (gate) | gap real − teórico |
|---|---|---|---|---|---|
| gols_1t | 1000.0 / 396.1 | 1.0845 | **0.9034** | 0.9472 | 0.044 |
| gols_2t | 408.2 / 1000.0 | 1.3853 | **0.9480** | 0.9466 | **−0.001 (idêntico, dentro do ruído)** |

`r_H_`/`r_A_` bateram no teto do MLE (`bounds=[(0.1, 1000.0)]` em `CornersNB._optimize_r`) —
ou seja, o otimizador queria dispersão **menor ainda** (mais perto de determinístico), travado
só pelo limite artificial de 1000. Isso já é evidência direta contra a hipótese "r mal
estimado/dispersão excessiva" (§3).

**Grid de alcançabilidade geral** (mu_total × r, home=away simétrico, 150k amostras/célula):

| mu_total | coverage80 (min~max sobre TODO o grid de r, de r=0.3 a r=1e6) | algum r acerta [0.75,0.85]? |
|---|---|---|
| 0.5 – 2.0 | 0.90 – 0.97 | **NUNCA** (impossível estruturalmente) |
| 2.5 – 5.0 | 0.78 – 0.94 | só em pontos estreitos e frágeis de r |
| 7.0 – 30.0 | 0.78 – 0.90 (mediana ~0.82–0.86) | sim, de forma robusta |

**Âncora de validação:** `faltas` (único mercado de contagem aprovado, coverage80 real =
0.8017) tem mu_total documentado no próprio código (`gate_count_market.py` linha ~128,
comentário "faltas, max_k=22 vs total~25"). Simulando mu_total≈25 com r moderado (r=8) a
simulação devolve coverage80=0.7508 — no mesmo regime da faixa-alvo, confirmando que o método
reproduz corretamente o regime onde a métrica **funciona** (contagem alta).

**Veredito:** coverage80 em [0.75,0.85] **não é alcançável** para mu_total abaixo de ~2 —
nenhum valor de dispersão resolve, é limite estrutural da discretização. Entre ~2.5 e 5 é
alcançável só em pontos isolados e instáveis de r (não é algo em que dá pra confiar via
recalibração). Acima de ~7-10 a métrica passa a funcionar como pretendido. **gols_1t
(mu≈1.08) e gols_2t (mu≈1.39) estão os dois na faixa estruturalmente impossível.**
Impedimentos (sem artefato salvo — ver §4) provavelmente também, dependendo do mu_total real.

---

## 3. Causa: dispersão mal estimada (r) vs. limite estrutural da métrica

**Refutada (gols_1t, gols_2t).** O r ajustado por MLE não está subestimado — está no **teto**
do bound (1000, quase-Poisson/quase-determinístico), o oposto de "dispersão excessiva
assumida". Mesmo usando esse r "enxuto" (o mínimo de variância que a NB consegue expressar
perto do limite Poisson) num processo gerador perfeitamente especificado, o coverage80 sai em
0.90–0.95 — a métrica falha mesmo sem excesso de dispersão nenhum. **Confirmada** a causa
alternativa: é a construção do intervalo central de 80% sobre uma PMF de poucos valores
possíveis (10-11 bins com massa não-desprezível, ver `n_possible_bins_in_support` na
simulação) que estrutura o viés pra cima.

**Impedimentos:** sem artefato salvo (nunca foi promovido, `offsides_nb.joblib` não existe —
consistente com CLAUDE.md, que lista `offsides_nb` como opcional ausente). Não dá pra
confirmar o r real. Sensibilidade num grid mu_total=2–5 mostra o mesmo padrão qualitativo
(impossível ou frágil). **Provável** (mesmo mecanismo, mas o r real não foi verificado — ver
§4 para o que falta).

---

## 4. Correlação 1T × 2T (mesma partida)

**Inconclusiva — falta dado.** `data/built/club_halftime_targets.parquet` não existe neste
worktree (gitignorado). Os únicos parquets versionados em `model_artifacts_clubes/`
(`club_goal_timing.parquet`, `club_matches_long.parquet`) não têm split por tempo — o
primeiro é agregado por faixas de gols marcados/sofridos na temporada, o segundo é
partida-completa sem 1T/2T. Não deu pra testar empiricamente a correlação.

**O que É verificável por código (Confirmada, não depende do dado):** `gols_1t` e `gols_2t`
são dois fits **inteiramente independentes** de `CornersNB` — `train_clubs_halftime_markets.py`
(linhas 42-72) itera sobre os 4 mercados por-tempo num loop `for name, th, ta, ... in MARKETS`
sem nenhum termo compartilhado ou condicionamento de um tempo no outro. A arquitetura não
modela (nem tenta modelar) a correlação intra-jogo entre metades — isso é fato de código, não
hipótese. Se essa independência é o que causa o gap RESIDUAL de gols_1t (0.044, não explicado
pela simulação homogênea — ver §2) fica **Inconclusiva**: precisaria do parquet real para
testar se a correlação 1T-2T explica esse resíduo, ou se é só heterogeneidade populacional
(mu variando por jogo/time) não capturada pela simulação de mu fixo.

---

## 5. Por que gols_2t é pior que gols_1t e impedimentos em tail_ece

| mercado | tail_ece candidato vs baseline | coverage80 REAL vs TEÓRICO (perfeito) |
|---|---|---|
| gols_1t | 0.0064 vs 0.0120 (**melhor**) | 0.9472 vs 0.9034 (gap residual 0.044) |
| gols_2t | 0.0096 vs 0.0054 (**pior**) | 0.9466 vs 0.9480 (gap ≈ 0, **idêntico ao teórico**) |
| impedimentos | 0.0505 vs 0.0668 (**melhor**) | 0.9412 vs faixa 0.85-0.94 (grid, mu incerto) |

Achado central desta seção: **coverage80 de gols_2t é 100% explicado pela simulação de
"modelo perfeito"** — não sobra nada de dispersão real mal ajustada para explicar. Isso
significa que o problema de gols_2t **não está** na dispersão nem na média central (aliás
delta_ll é o melhor dos três: −0.00433 em 5/5 folds). O problema está especificamente na
calibração da probabilidade O/U na linha central (`tail_ece`), que é uma métrica DIFERENTE
(ECE binário de `P(total > mediana)`, não a PMF inteira) — e essa métrica não foi replicada
pela simulação de coverage80 (que usa a PMF inteira). **Inconclusiva** sobre a causa raiz
exata do tail_ece de gols_2t: a hipótese mais plausível (Provável, não testável sem o dado
real) é heterogeneidade de estado de jogo pós-intervalo — times mudam postura tática
condicionados no placar do 1T (efeito bem documentado na literatura de futebol), e a
arquitetura atual (NB independente por feature pré-jogo, sem nenhuma feature de placar do 1T)
não tem como capturar isso. gols_1t não sofre desse problema porque não há "meio-tempo
anterior" que mude o comportamento dos times. Testar essa hipótese exige
`club_halftime_targets.parquet` com o placar do 1T como feature condicional para o modelo de
2T — não disponível neste ambiente.

---

## 6. Recomendação para os 3 agentes de mercado (Fase 1)

1. **gols_1t e impedimentos — não investir em recalibração isotônica para resolver
   coverage80.** O teto de 0.9034 (gols_1t) e a faixa 0.85-0.94 (impedimentos, mu baixo) do
   "modelo perfeito" já mostram que nenhuma recalibração de PMF vai colocar coverage80 em
   [0.75,0.85] com esse mu_total — é limite estrutural, não erro de ajuste. O
   `calib_check_all.log` já mostrado no contexto testou calibração isotônica de UMA linha
   (a mediana O/U) e viu log-loss Bernoulli melhorar — mas isso recalibra só **um ponto de
   corte**, não a PMF inteira que `coverage80` precisa (ele usa os cortes em 10% e 90% da
   massa, não a mediana). Recalibrar 1 linha não resolve um problema estrutural que precisa
   de TODOS os quantis simultaneamente bem calibrados — a matemática não fecha.
   **Recomendação concreta: propor mudar o próprio gate §6-C**, não o modelo. Duas opções
   defensáveis: (a) substituir o teto fixo `coverage80 ∈ [0.75,0.85]` por uma faixa
   **calculada por mercado** via esta mesma simulação de auto-consistência (rodar a
   simulação com os r/mu do próprio candidato e usar esse valor teórico ± tolerância como
   alvo, em vez de um número universal que pressupõe contagem alta); (b) para mercados com
   mu_total abaixo de ~5, **descartar coverage80 como critério de aprovação** e manter só
   `tail_ece` (que já é comparativo contra baseline, não um alvo absoluto, e por isso não
   sofre do mesmo viés de discretização) — que aliás é exatamente onde gols_1t e impedimentos
   JÁ PASSAM. Sob essa proposta, os dois seriam APROVADOS hoje.

2. **gols_2t — caso diferente, não fechar com mudança de gate isolada.** Coverage80 também é
   estrutural aqui (evidência ainda mais forte que gols_1t: gap real−teórico ≈ 0), então a
   mesma recomendação de mudar o gate se aplica. MAS o tail_ece pior que o baseline é um
   problema real e distinto, não resolvido nem pela simulação nem pela calibração isotônica
   de 1 linha (`calib_check`: só 3/5 folds bateram o baseline, "ajuda mas não resolve
   sozinha"). Não gastar mais tempo em recalibração pós-hoc para gols_2t — a hipótese mais
   promissora (efeito de estado de jogo pós-1T, não capturado pela arquitetura atual de
   features pré-jogo) exige dado real (`club_halftime_targets.parquet` com placar do 1T como
   feature) e possivelmente uma arquitetura condicional (2T | placar do 1T), fora do escopo
   de recalibração. Se o agente de mercado de gols_2t tiver acesso ao parquet, o primeiro
   teste barato é: `corr(goals_1t_total, goals_2t_total)` por partida e
   `corr(|placar_1T_diff|, var(goals_2t))` — se houver correlação real de estado, é sinal de
   que vale a pena testar a feature "placar do 1T" no modelo de 2T (não recalibração, mudança
   de feature).

3. **Recomendação geral para o gate:** o padrão observado (`faltas` com mu~25 passa;
   `cartoes_vermelhos` mu baixíssimo tem coverage80=0.9716, pior de todos; `cartoes_1t/2t`
   ficam no meio, 0.92/0.85) é consistente com o mesmo mecanismo estrutural em TODOS os
   mercados de contagem baixa já reprovados no `RESUMO_clube.json`, não só nos 3 deste
   cluster. Vale a pena o dono considerar isso como achado de escopo maior que os 3 mercados
   originais — o critério de coverage80 fixo provavelmente também está reprovando
   `cartoes_vermelhos`/`cartoes_1t`/`cartoes_2t` pelo mesmo motivo estrutural, misturado com
   causas reais nesses casos (`cartoes_2t` também falha `folds_ok`/`delta_ok`, então lá tem
   problema real de ajuste ALÉM do estrutural — não é só métrica).
