# 04 — Documentação de Ferramentas e Mercados (base de conhecimento)

> **Propósito.** Este documento é uma base de consulta técnica para agentes Claude trabalhando no
> projeto ApostaInfo (previsão probabilística de partidas de futebol). Cobre, na **Parte A**, as
> bibliotecas/ferramentas de ciência de dados relevantes para o pipeline atual (scikit-learn,
> gradient boosting, interpretabilidade, modelagem bayesiana, fontes de dados, visualização) e, na
> **Parte B**, a documentação conceitual completa dos mercados de apostas de futebol que o produto
> precifica (1X2, handicaps, BTTS, escanteios, cartões, finalizações, over/under, HT/FT).
>
> Todo o conteúdo foi resumido com palavras próprias a partir de documentação oficial e fontes
> públicas confiáveis (ver seção "Fontes" ao final). Não há reprodução de parágrafos inteiros de
> nenhuma fonte, e citações diretas — quando existem — têm menos de 15 palavras e atribuição
> explícita. Nenhum PDF pirata de livro foi acessado.
>
> Gerado em 2026-07-20.

---

## Sumário

**Parte A — Bibliotecas e ferramentas**
1. [Scikit-Learn](#a1-scikit-learn)
2. [SHAP](#a2-shap)
3. [XGBoost](#a3-xgboost)
4. [LightGBM](#a4-lightgbm)
5. [CatBoost](#a5-catboost)
6. [PyMC](#a6-pymc)
7. [API-Football](#a7-api-football)
8. [StatsBomb Open Data](#a8-statsbomb-open-data)
9. [socceraction (VAEP / Atomic-VAEP)](#a9-socceraction-vaep--atomic-vaep)
10. [mplsoccer](#a10-mplsoccer)
11. [Kloppy](#a11-kloppy)
12. [Livros e relatórios de football analytics](#a12-livros-e-relatórios-de-football-analytics)

**Parte B — Mercados de apostas de futebol**
1. [Resultado (1X2 / Moneyline)](#b1-resultado-1x2--moneyline)
2. [Handicap Asiático e Handicap Europeu](#b2-handicap-asiático-e-handicap-europeu)
3. [BTTS (Ambas Marcam)](#b3-btts-ambas-marcam)
4. [Escanteios (total, handicap, over/under)](#b4-escanteios-total-handicap-overunder)
5. [Cartões (amarelos, vermelhos, total, handicap)](#b5-cartões-amarelos-vermelhos-total-handicap)
6. [Finalizações (total de chutes, por time)](#b6-finalizações-total-de-chutes-por-time)
7. [Chutes no Alvo (Shots on Target)](#b7-chutes-no-alvo-shots-on-target)
8. [Over/Under (gols) e generalização para outras métricas](#b8-overunder-gols-e-generalização-para-outras-métricas)
9. [HT (mercados de primeiro tempo)](#b9-ht-mercados-de-primeiro-tempo)
10. [FT (tempo total) e a relação/correlação HT/FT](#b10-ft-tempo-total-e-a-relaçãocorrelação-htft)

[Fontes](#fontes)

---

# Parte A — Bibliotecas e ferramentas

## A1. Scikit-Learn

Scikit-Learn oferece a base estatística mais direta para modelar contagens de gols/eventos e para
transformar saídas de qualquer classificador em probabilidades confiáveis — os dois blocos centrais
de um pipeline Dixon-Coles/Negative Binomial como o do projeto.

**Modelos lineares generalizados (GLM).** O módulo `sklearn.linear_model` expõe `PoissonRegressor` e
`TweedieRegressor` para regressão de variáveis de contagem (gols, escanteios, cartões). O
`TweedieRegressor` é o mais flexível: o parâmetro `power` escolhe a distribuição da família
exponencial — `power=0` é Normal, `power=1` é Poisson (equivalente a `PoissonRegressor` com
`link='log'`), `power=2` é Gama (equivalente a `GammaRegressor`) e `power=3` é Gaussiana Inversa.
Valores entre 1 e 2 correspondem à própria distribuição Tweedie composta Poisson-Gama, útil para
variáveis com excesso de zeros e cauda longa. A função de ligação (`link`) é tipicamente `'log'`,
garantindo que a predição linear seja transformada em `exp(Xw)`, sempre não negativa — essencial
para modelar taxas de gols esperados (λ). Para modelar frequências relativas (contagens por
exposição), a documentação recomenda passar `y = contagem/exposição` como alvo e a exposição como
`sample_weight`.

**Calibração de probabilidade.** O módulo `sklearn.calibration` resolve um problema comum em
classificadores de resultado (vitória/empate/derrota): muitos modelos — sobretudo árvores, florestas
e SVM — produzem `predict_proba` mal calibrado (Random Forest tende a empurrar probabilidades para o
centro; SVM de margem máxima mostra curvas sigmoides acentuadas). A classe `CalibratedClassifierCV`
recalibra qualquer classificador ajustando um "calibrador" que mapeia a saída bruta para uma
probabilidade em [0,1], usando validação cruzada para evitar viés de reaproveitar dados de treino.
Dois métodos são suportados: `method="sigmoid"` (Platt scaling, ajuste logístico de 2 parâmetros,
melhor para poucos dados) e `method="isotonic"` (regressão isotônica não paramétrica, mais poderosa
mas mais sujeita a overfitting em bases pequenas — recomendada só acima de ~1000 amostras). A
calibração isotônica introduz empates nas probabilidades preditas, podendo alterar métricas de
ranking (AUC); se a ordenação importa, `"sigmoid"` preserva o ranking por ser estritamente monotônica.

**Métricas de avaliação probabilística.** `sklearn.metrics.log_loss` e
`sklearn.metrics.brier_score_loss` são as métricas de referência para avaliar previsões
probabilísticas — essenciais para o "gate" de validação de qualquer modelo de mercado neste projeto.
`log_loss` é a log-verossimilhança negativa média (cross-entropy); `brier_score_loss` é o erro
quadrático médio entre probabilidade prevista e resultado binário observado, uma *strictly proper
scoring rule*. A documentação oficial destaca um ponto sutil: como o texto original registra, escores
mais baixos "does not necessarily mean a better calibrated model, it could also mean a worse
calibrated model with much more discriminatory power" — ou seja, log-loss/Brier caindo não prova
isoladamente melhor calibração; é preciso olhar também curvas de calibração (`CalibrationDisplay`).

**Fontes:** https://scikit-learn.org/stable/modules/calibration.html ·
https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html ·
https://scikit-learn.org/stable/modules/linear_model.html#generalized-linear-models ·
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.log_loss.html ·
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html ·
https://scikit-learn.org/stable/modules/model_evaluation.html

---

## A2. SHAP

SHAP (SHapley Additive exPlanations) é a biblioteca padrão para interpretar modelos "caixa-preta" —
relevante quando se troca um Dixon-Coles interpretável por gradient boosting (XGBoost/LightGBM) para
prever gols, cartões ou props de jogador, e é preciso justificar por que o modelo previu determinada
probabilidade para uma partida específica. A biblioteca formaliza a contribuição de cada feature
usando valores de Shapley da teoria dos jogos: cada previsão é decomposta na soma de um "valor base"
(a previsão média sobre um dataset de referência) mais a contribuição aditiva de cada feature, de
forma que essas contribuições somem exatamente à saída do modelo para aquela amostra — a
"aditividade local" que distingue SHAP de outras técnicas de importância de features.

**Explainers principais.** `shap.TreeExplainer` é o mais relevante para modelagem esportiva baseada em
ensembles de árvores (XGBoost, LightGBM, CatBoost, Random Forest, GBM do scikit-learn): usa o
algoritmo Tree SHAP, que explora a estrutura interna das árvores para calcular valores de Shapley
exatos (não aproximados) em tempo polinomial. Já `shap.KernelExplainer` é agnóstico ao modelo —
funciona com qualquer `predict`/`predict_proba`, inclusive SVM ou redes neurais — mas paga o preço de
ser uma aproximação, ajustando uma regressão linear local ponderada (Kernel SHAP) sobre amostras
perturbadas de um `background dataset`; por isso é mais lento e só costuma ser usado quando
`TreeExplainer` não se aplica. A API moderna unifica isso em `shap.Explainer(model)`, que detecta
automaticamente o tipo de modelo e escolhe o algoritmo mais eficiente.

**Visualizações principais.** `shap.summary_plot` (ou `shap.plots.beeswarm`) agrega os valores SHAP de
todas as amostras de teste, ordenando features pela soma das magnitudes de impacto e mostrando a
distribuição do efeito de cada uma (cor indicando valor alto/baixo da própria feature) — a visão
"global" de quais variáveis (Elo, forma recente, GAP ratings etc.) mais pesam no modelo, e em que
direção. `shap.force_plot` (ou `shap.plots.waterfall`) oferece a visão "local": para uma única
previsão, mostra como cada feature empurrou a probabilidade prevista para cima ou para baixo a partir
do valor base — útil para depurar por que o modelo achou um confronto mais ou menos provável do que o
esperado. `shap.dependence_plot` cruza o valor de uma feature com seu valor SHAP correspondente para
revelar não linearidades (ex.: se a vantagem de Elo tem retornos decrescentes).

**Fontes:** https://shap.readthedocs.io/en/latest/ ·
https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html ·
https://shap.readthedocs.io/en/latest/api.html · https://github.com/shap/shap

---

## A3. XGBoost

XGBoost é uma implementação otimizada de gradient boosting em árvores, usada como alternativa (ou
complemento) aos GLMs para modelar contagens de gols, cartões e escanteios quando se suspeita de não
linearidades ou interações entre features que um Dixon-Coles não captura. A documentação organiza os
parâmetros em três grupos: gerais (booster a usar), de booster (dependem do tipo escolhido) e de
tarefa de aprendizado (objetivo e métricas).

**Parâmetros centrais de árvore.** `eta` (alias `learning_rate`, padrão 0.3) controla o encolhimento
dos pesos após cada rodada de boosting — valores menores tornam o treino mais conservador e exigem
mais árvores. `max_depth` (padrão 6) limita a profundidade de cada árvore. `subsample` (padrão 1) é a
fração de instâncias amostrada antes de cada árvore, e a família `colsample_bytree`/`colsample_bylevel`/
`colsample_bynode` controla a fração de colunas amostradas por árvore/nível/nó, de forma cumulativa.
Para regularização, `lambda` (alias `reg_lambda`, padrão 1) aplica penalização L2 sobre pesos das
folhas e `alpha` (alias `reg_alpha`, padrão 0) aplica L1. `gamma` (alias `min_split_loss`) exige uma
redução mínima de perda para permitir nova divisão em um nó — poda adicional.

**Objetivos para contagens.** Para variáveis de contagem como gols ou cartões,
`objective="count:poisson"` ajusta uma regressão de Poisson (`max_delta_step=0.7` por padrão como
salvaguarda). `objective="reg:tweedie"` cobre distribuições Tweedie mais gerais
(`tweedie_variance_power` entre 1 e 2), úteis para alvos com excesso de zeros.
`objective="reg:squarederror"` é o padrão para regressão contínua e `objective="reg:gamma"` serve
alvos estritamente positivos e assimétricos. Métricas correspondentes incluem `poisson-nloglik` e
`tweedie-nloglik`, além de `logloss` para classificação binária (vitória/BTTS/over-under).

**Early stopping e tuning.** O treino aceita um conjunto de validação e `early_stopping_rounds` para
interromper o boosting quando a métrica para de melhorar. `tree_method="hist"` é o algoritmo de
construção de árvores recomendado atualmente, e `grow_policy` (`depthwise` vs `lossguide`) determina
se o crescimento prioriza proximidade da raiz ou maior redução de perda — este último se aproxima da
filosofia leaf-wise do LightGBM.

**Fontes:** https://xgboost.readthedocs.io/en/stable/parameter.html ·
https://xgboosting.com/configure-xgboost-countpoisson-objective/

---

## A4. LightGBM

LightGBM é outra implementação de gradient boosting em árvores, criada pela Microsoft com foco em
velocidade e uso de memória em datasets grandes — relevante para retreinos frequentes sobre dezenas de
competições e centenas de milhares de partidas, como no dataset de clubes deste projeto.

**Diferenças-chave frente ao XGBoost.** A diferença mais citada é a estratégia de crescimento de
árvore: a maioria das implementações cresce nível a nível (*level/depth-wise*, árvore simétrica),
enquanto o LightGBM cresce *leaf-wise* (*best-first*) — a cada passo escolhe a folha com maior redução
de perda potencial, independentemente do nível. Converge mais rápido e atinge menor perda para um
número fixo de folhas, mas pode gerar árvores mais profundas/assimétricas com maior risco de
overfitting em datasets pequenos; por isso `max_depth` existe como limitador mesmo crescendo
leaf-wise, e recomenda-se manter `num_leaves` (padrão 31) menor que `2^max_depth`. Outra diferença
central é o uso de **algoritmos baseados em histograma**: valores contínuos são discretizados em bins
antes de calcular ganhos de split, reduzindo complexidade e permitindo "subtração de histograma"
(obter o histograma de um filho por diferença do pai e do irmão) para acelerar o treino. O LightGBM
também introduz **GOSS** (Gradient-based One-Side Sampling): mantém todas as instâncias com gradientes
grandes e amostra aleatoriamente entre as de gradiente pequeno (`top_rate`/`other_rate`, via
`data_sample_strategy="goss"`). Tem ainda suporte **nativo a features categóricas**
(`categorical_feature`) sem exigir one-hot: para uma categórica com k categorias, ordena o histograma
por `sum_gradient/sum_hessian` acumulado e encontra o split ótimo nessa ordenação — evitando árvores
desbalanceadas que o one-hot tende a produzir em alta cardinalidade (times, ligas, árbitros).

**Parâmetros centrais.** `objective` (padrão `regression`, ou seja, L2) inclui `poisson`, `gamma` e
`tweedie` como opções diretas para contagens. `learning_rate` controla o encolhimento por iteração; a
documentação recomenda taxa pequena combinada com `num_iterations` grande. Para overfitting/velocidade:
`feature_fraction` (alias `colsample_bytree`), `bagging_fraction`/`bagging_freq` (alias `subsample`),
`lambda_l1`/`lambda_l2` (aliases `reg_alpha`/`reg_lambda`). `min_data_in_leaf` (padrão 20) e
`min_sum_hessian_in_leaf` limitam o tamanho mínimo de folhas para conter o overfitting típico do
crescimento leaf-wise. `early_stopping_round` (default 0) interrompe o treino se a métrica de
validação não melhorar por N rodadas.

**Fontes:** https://lightgbm.readthedocs.io/en/latest/Parameters.html ·
https://lightgbm.readthedocs.io/en/latest/Features.html ·
https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html

---

## A5. CatBoost

CatBoost é uma biblioteca de gradient boosting em árvores da Yandex, com dois diferenciais centrais
frente a XGBoost/LightGBM: **ordered boosting** e **tratamento nativo de variáveis categóricas**.

Em gradient boosting clássico, cada árvore é ajustada sobre resíduos calculados com o próprio conjunto
de dados que a árvore "vê", gerando um viés sutil chamado *prediction shift*. O ordered boosting
resolve isso simulando, para cada exemplo, um modelo treinado apenas com exemplos "anteriores" numa
permutação aleatória — o gradiente usado nunca usa a própria label do exemplo no cálculo da estatística
que o descreve. A documentação descreve a escolha da estrutura da árvore como um método guloso, com
candidatos feature-split avaliados folha a folha após permutação aleatória dos objetos antes de cada
nova árvore.

Para categóricas, o CatBoost evita one-hot tradicional convertendo categorias em estatísticas
numéricas — **CTRs** (*categorical target statistics*) — calculadas de forma "ordenada" (usando apenas
histórico de exemplos anteriores na permutação), evitando vazamento de informação do alvo. Por padrão,
categorias com poucos valores distintos usam one-hot (`one_hot_max_size`, default 2 na CPU); as demais
passam pela transformação estatística. Relevante para dados de futebol com muitas categóricas de alta
cardinalidade (times, ligas, árbitros, técnicos) que no pipeline atual do projeto são tratadas via
engenharia manual de features — o CatBoost permite passar `cat_features` diretamente.

O terceiro pilar é a **árvore simétrica (oblivious tree)**: todos os nós de um mesmo nível usam o mesmo
par feature-split, produzindo árvores balanceadas, mais rápidas em inferência e com menor tendência a
overfitting comparado ao crescimento leaf-wise do LightGBM.

Parâmetros centrais: `loss_function` (`RMSE`, `Logloss`, `Poisson`, `Tweedie`, `MultiClass` — CatBoost
tem `Poisson`/`Tweedie` nativos, relevantes para gols), `iterations`, `learning_rate`, `depth`
(tipicamente 4-10), `l2_leaf_reg`, `random_seed`, `eval_metric` e overfitting detector/
`early_stopping_rounds`. Comparado aos concorrentes: XGBoost cresce nível-a-nível (mais lento, robusto);
LightGBM cresce leaf-wise (mais rápido, mais propenso a overfit em dados pequenos); CatBoost tende a
exigir menos tuning, lidar melhor com poucos dados e categóricas nativas, ao custo de treino geralmente
mais lento em datasets muito grandes.

**Fontes:** https://catboost.ai/docs/en/concepts/algorithm-main-stages_choose-tree-structure ·
https://catboost.ai/docs/en/features/categorical-features ·
https://catboost.ai/docs/en/concepts/algorithm-main-stages_cat-to-numberic ·
https://catboost.ai/docs/en/references/training-parameters/common

---

## A6. PyMC

PyMC é a biblioteca de referência em Python para modelagem bayesiana, construída sobre PyTensor para
diferenciação automática e amostragem eficiente. Seu caso de uso mais direto para futebol é a
modelagem hierárquica de forças de ataque/defesa por time — o padrão **Baio & Blangiardo (2010)**, que
a própria galeria oficial de exemplos do PyMC reproduz no notebook "A Hierarchical model for Rugby
prediction" (adaptado para rúgbi, mesma estrutura usada para futebol).

A ideia central é o **partial pooling**: em vez de estimar a força de cada time de forma totalmente
independente (superajusta em ligas com poucos jogos por time) ou assumir times iguais, o modelo
hierárquico assume que os parâmetros de ataque (`atts`) e defesa (`defs`) vêm de uma distribuição
comum — `Normal(mu_att, sigma_att)` e `Normal(mu_def, sigma_def)` — cujos hiperparâmetros também são
estimados dos dados. Isso "encolhe" estimativas de times com poucos dados em direção à média da liga,
produzindo estimativas mais estáveis e com quantificação de incerteza (intervalos de credibilidade),
algo que um modelo pontual como o DC-NB atual não expõe diretamente.

O modelo estrutural do exemplo oficial especifica: `log(θ_home) = intercept + home_advantage +
att[casa] + def[visitante]` e `log(θ_away) = intercept + att[visitante] + def[casa]`, com
`home_points ~ Poisson(θ_home)` e `away_points ~ Poisson(θ_away)` — a mesma estrutura conceitual do
Dixon-Coles do projeto, mas estimada via inferência bayesiana completa em vez de máxima
verossimilhança penalizada.

A amostragem usa o **NUTS** (No-U-Turn Sampler), variante de Monte Carlo Hamiltoniano auto-ajustável,
sampler default do PyMC para variáveis contínuas (`pm.sample()`). Diagnósticos de convergência
(`r_hat`, `ess_bulk`/`ess_tail`) são feitos via ArviZ, biblioteca companheira para análise posterior.
Para comparação de modelos, o ecossistema oferece **WAIC** e **LOO** (`arviz.loo`/`arviz.compare`),
permitindo comparar especificações (ex.: com/sem efeito de mando de campo) sem re-treinar via
validação cruzada completa. Após o ajuste, é possível fazer amostragem da **posterior preditiva**
(`pm.sample_posterior_predictive`) para simular resultados de todos os jogos restantes de um
campeonato milhares de vezes e estimar probabilidades de título/classificação — técnica diretamente
aplicável ao mata-mata agregado e simulações de tabela já expostos em produção neste projeto.

**Fontes:** https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html ·
https://www.pymc.io/projects/examples/en/latest/ · https://www.pymc.io/

---

## A7. API-Football

API-Football (mantida pela API-Sports) é uma API REST comercial cobrindo mais de 1.200 ligas e copas
de futebol, com dados de partidas em tempo real, histórico, estatísticas, odds e previsões próprias —
a mesma família de produto já usada no projeto (`prefetch_wc_data.py`/`prefetch_clubs.py`).

A hierarquia dos dados segue: país → liga → temporada → fixture (partida) → tipo de dado específico.
Endpoints mais relevantes para modelagem preditiva:

- **`/fixtures`** — o mais versátil: filtros por `league`+`season`, `date`, `live`, `next`/`last`
  (N próximos/últimos jogos), `h2h` (confrontos diretos entre dois times), `timezone`.
- **`/fixtures/statistics`** — estatísticas por time e partida (chutes a gol, chutes fora, posse de
  bola, escanteios, faltas, impedimentos, cartões), durante e após a partida.
- **`/fixtures/players`** — notas e estatísticas individuais por partida (base dos modelos de props do
  projeto).
- **`/odds`** — odds pré-jogo de múltiplas casas, paginadas em 10 por página, com **histórico limitado
  a 7 dias**, atualizando a cada ~3 horas; `/odds/live` cobre odds ao vivo. IDs de bookmakers/tipos de
  aposta vêm de `/odds/bookmakers`, `/odds/bets` e `/odds/live/bets` (sistemas de ID separados entre
  pré-jogo e ao vivo).
- **`/predictions`** — previsão algorítmica própria da API para uma fixture (vencedor, boolean
  `win_or_draw`, sugestão over/under, "advice", percentuais), atualizada a cada hora — útil como
  baseline de comparação externo ao modelo do projeto.

Planos e limites: o plano gratuito oferece **100 requisições/dia** com acesso a todos os endpoints (a
diferença entre planos pagos é volume e profundidade histórica, não funcionalidade). Planos pagos
citados: Pro (US$19/mês, 7.500 req/dia), Ultra (US$29/mês, 75.000 req/dia) e Mega (US$39/mês, 150.000
req/dia) — números que batem com a cota de 75k/dia já referenciada na documentação interna do projeto.
Há **dois limites simultâneos** (cota diária total e limite por minuto), reportados nos headers de
resposta (`x-ratelimit-requests-remaining` etc.); estourar o limite por minuto repetidamente pode
suspender temporariamente o acesso — daí a recomendação de monitorar headers e recuar (*backoff*) em
vez de repetir em loop apertado, já contemplado no runbook de coleta do projeto (`ARCHITECTURE.md §7.2`).

**Fontes:** https://www.api-football.com/documentation-v3 ·
https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide ·
https://api-sports.io/documentation/football/v3

---

## A8. StatsBomb Open Data

StatsBomb é um provedor de dados de futebol conhecido pelo nível de detalhe em **dados de eventos**
(event data) — muito mais granulares que estatísticas agregadas como as da API-Football. A empresa
disponibiliza gratuitamente, no repositório GitHub `statsbomb/open-data`, um subconjunto de
competições (Copas do Mundo masculina e feminina, temporadas selecionadas de grandes ligas europeias,
NWSL/Champions League feminina, entre outras) "para projetos de pesquisa e interesse genuíno em
analytics de futebol", nas palavras do próprio README do repositório.

A estrutura é hierárquica e espelha a API interna da StatsBomb:
- **`competitions.json`** — índice global de pares competição-temporada (com IDs), ponto de entrada
  para navegar o resto do dataset.
- **`matches/{competition_id}/{season_id}.json`** — lista de partidas de uma competição-temporada.
- **`events/{match_id}.json`** — núcleo do dataset: sequência de eventos de uma partida (passes,
  chutes, duelos, pressões, dribles etc.), cada um com timestamp, minuto/segundo, período, coordenadas
  espaciais (`location`), jogador, time e qualificadores específicos por tipo de evento.
- **`lineups/{match_id}.json`** — escalações completas por partida.
- **`three-sixty/{match_id}.json`** — dados de rastreamento StatsBomb 360 (posicionamento de todos os
  jogadores em momentos-chave), disponível apenas para partidas selecionadas.

O nível de detalhe permite construir métricas avançadas como xG (expected goals) próprio, xT
(expected threat) e ratings de ataque/defesa por jogador — um patamar acima do que dados apenas de
placar/estatísticas agregadas permitem, exigindo processamento mais pesado (um jogo pode ter milhares
de eventos). O uso está sujeito a licença/termos (`LICENSE.pdf` no repositório) restringindo a fins de
pesquisa/análise não comercial, exigindo atribuição e proibindo redistribuição/exploração comercial —
importante verificar antes de qualquer uso em produto comercial (diferente da licença comercial paga
da API-Football).

Para consumir os dados em Python sem lidar manualmente com os JSONs, existe o pacote oficial
**statsbombpy** (`github.com/statsbomb/statsbombpy`), com funções como `sb.competitions()`,
`sb.matches()`, `sb.events()` e `sb.competition_events()` retornando diretamente DataFrames do pandas,
já achatando a estrutura aninhada dos eventos (incluindo suporte a métricas 360 via
`include_360_metrics=True`). O pacote também acessa a API paga da StatsBomb, bastando trocar as
credenciais.

**Fontes:** https://github.com/statsbomb/open-data · https://github.com/statsbomb/statsbombpy ·
https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf

---

## A9. socceraction (VAEP / Atomic-VAEP)

**socceraction** é um pacote Python mantido pelo grupo de Machine Learning da KU Leuven
(`ML-KULeuven/socceraction` no GitHub, documentação em socceraction.readthedocs.io) cujo objetivo é
converter dados de eventos de futebol em formatos padronizados e atribuir um valor numérico a cada
ação individual de um jogador em campo. É usado como base de pesquisa acadêmica (originou o artigo
"Actions Speak Louder than Goals", KDD 2019, de Decroos, Bransen, Van Haaren e Davis) e não é mais
ativamente estendido com novas features — os mantenedores priorizam a reprodutibilidade da pesquisa já
publicada.

O núcleo conceitual é o **SPADL** (Soccer Player Action Description Language) e sua variante
**atomic-SPADL**: uma linguagem unificada para descrever ações on-the-ball (passe, drible, chute,
desarme etc.), com localização em coordenadas de campo, resultado e parte do corpo usada. O pacote
inclui conversores de SPADL a partir dos formatos proprietários dos principais provedores (StatsBomb,
Opta, Wyscout, Stats Perform, WhoScored), permitindo comparar ações entre fontes diferentes com uma
representação única.

Sobre esse formato comum, o socceraction implementa dois frameworks de valorização de ações:

- **Expected Threat (xT)** — framework baseado em grid do campo dividido em zonas, proposto por Karun
  Singh em 2019, que estima a probabilidade de gol a partir de cada zona via cadeia de Markov.
- **VAEP (Valuing Actions by Estimating Probabilities)** — o framework mais elaborado. A ideia central
  é que jogadores executam ações com duas intenções possíveis: aumentar a probabilidade de o próprio
  time marcar no curto prazo, ou reduzir a probabilidade de sofrer gol. O valor de um estado de jogo Si
  é V(Si) = Pscore(Si,t) − Pconcede(Si,t), com Pscore/Pconcede estimadas por dois classificadores de
  gradient boosting treinados separadamente, usando como entrada uma janela de contexto de três ações
  consecutivas (game state). O valor VAEP de uma ação é a diferença entre "valor ofensivo" e "valor
  defensivo": VVAEP(ai) = ΔPscore(ai,t) − ΔPconcede(ai,t).

A **Atomic-VAEP** opera sobre atomic-SPADL, decomposição ainda mais granular das ações (separando,
por exemplo, início e fim de um passe em eventos atômicos distintos), permitindo modelar de forma mais
direta ações sem resultado explícito de sucesso/falha. Estruturalmente, o pacote se organiza em
`socceraction.spadl` (conversão/representação), `socceraction.vaep.features` (engenharia de features
sobre game states), `socceraction.vaep.labels` (rotulagem scores/concedes) e
`socceraction.vaep.formula` (cálculo final do valor).

**Fontes:** https://github.com/ML-KULeuven/socceraction ·
https://socceraction.readthedocs.io/en/latest/documentation/valuing_actions/vaep.html

---

## A10. mplsoccer

**mplsoccer** é uma biblioteca Python (mantida por Andrew Rowlinson, documentação em
mplsoccer.readthedocs.io) dedicada a visualização de dados de futebol construída sobre o Matplotlib.
Seu propósito é permitir gráficos consistentes mais rápido, sem montar tudo do zero — componentes
prontos para os tipos de visualização mais comuns em análise de futebol.

Funcionalidades centrais:
- **Pitch / VerticalPitch** — classes para desenhar campos em nove tipos diferentes (StatsBomb, Opta,
  Wyscout, Tracab, custom etc.), orientação horizontal ou vertical, meio-campo (`half=True`), quatro
  orientações básicas, customização de cor de grama/listras/linhas. Ponto de entrada típico:
  `Pitch(pitch_color=..., line_color=..., stripe=...)` seguido de `.draw()`.
- **Radar charts** — comparação de múltiplas métricas de um jogador/time simultaneamente, usado em
  scouting para perfis multidimensionais.
- **Nightingale / pizza charts** — variante circular popular em relatórios de scouting.
- **Bumpy charts** — posição ao longo do tempo (ex.: evolução na tabela do campeonato).
- **Camadas sobre o campo** — setas (passes/dribles), heatmaps, hexbins, scatter e linhas "comet"
  (gradiente de espessura/opacidade sugerindo direção de movimento).
- **Carregamento de dados StatsBomb** — utilitários para ler o open-data e transformá-lo em dataframes
  "tidy" (formato longo), facilitando integração com pandas.
- **Standardizer** — padronização de coordenadas de campo entre convenções de tamanho/escala de
  provedores diferentes, permitindo sobrepor/comparar eventos de fontes distintas num mesmo sistema de
  referência.

A biblioteca cita influências da comunidade de football analytics: design de API inspirado por Peter
McKeever, o pacote R `ggsoccer` influenciou o Standardizer, e as visualizações de expected threat de
Karun Singh e o open-data da StatsBomb são citados como motivadores do projeto — evidenciando o
ecossistema compartilhado com socceraction e kloppy. Licenciada sob MIT, desenvolvimento aberto via
GitHub (`andrewRowlinson/mplsoccer`).

**Fontes:** https://mplsoccer.readthedocs.io/

---

## A11. Kloppy

**Kloppy** é uma biblioteca Python mantida pela organização sem fins lucrativos **PySport**
(documentação em kloppy.pysport.org, código em github.com/PySport/kloppy) cujo propósito é resolver um
problema estrutural da análise de futebol com dados de tracking/eventos: cada provedor usa formato
proprietário, definição de eventos e sistema de coordenadas próprios, dificultando construir análises
que combinem múltiplas fontes.

A solução é um **modelo de dados vendor-independent** (unificado) tanto para dados de eventos quanto
de tracking (posição contínua de jogadores/bola). Em vez de escrever um parser específico por
provedor, o kloppy carrega dados brutos de qualquer fonte suportada para essa representação comum,
permitindo que o resto do pipeline (filtragem, transformação, exportação) seja escrito uma única vez.

Provedores suportados incluem **StatsBomb** (com freeze-frame 360), **Opta/Stats Perform** (feeds
F7/F24/F73 e MA1/MA3/MA25), **Wyscout** (v2/v3), **Metrica Sports** (eventos e tracking, com dataset
público), **Sportec** (usado em ligas como a Bundesliga, com dados públicos), **SkillCorner**, **Second
Spectrum**, **Tracab**, **Hawkeye**, **Signality**, **DataFactory**, **PFF** e **Impect**.

Quatro capacidades principais:
1. **Load** — importar dados de qualquer provedor suportado para o modelo padronizado.
2. **Filter** — busca baseada em expressões sobre sequências de eventos, pensada para localizar
   padrões táticos (ex.: passe-passe-finalização) sem varrer o jogo manualmente.
3. **Transform** — conversão entre sistemas de coordenadas de provedores diferentes, mudança de
   orientação (sempre esquerda→direita relativo ao time com posse), normalização de dimensões de campo.
4. **Export** — converter para dataframes Polars ou Pandas, ou para SportsCode XML (fluxos de análise
   de vídeo), com compatibilidade com outras bibliotecas do ecossistema (incluindo o socceraction).

Licenciado sob BSD-3-Clause, com desenvolvimento ativo — mais um bloco de infraestrutura para quem
trabalha com dados de futebol do que uma ferramenta de modelagem pronta (diferente do socceraction, que
já entrega valorização de ações).

**Fontes:** https://kloppy.pysport.org/ · https://github.com/PySport/kloppy

---

## A12. Livros e relatórios de football analytics

**Football Analytics 101.** Não foi encontrado um relatório oficial com esse título exato publicado
pela StatsBomb ou por David Sumpter (autor de *Soccermatics*). O que existe é um recurso independente
de código aberto — `football-analytics-101.readthedocs.io` (repositório GitHub
`Ericonaldo/Football-Analytics-101`), mantido por um pesquisador individual, inspirado no site
"NBAStuffer Analytics 101" (equivalente para basquete). É uma coletânea curada de fontes de dados
públicas, competições/desafios de sports analytics, artigos acadêmicos (incluindo trabalhos da MIT
Sloan Sports Analytics Conference) e um catálogo de empresas do setor — um índice de referência
comunitário, não um relatório formal de uma organização.

**Football Analytics: Now and Beyond.** Publicação da **Barça Innovation Hub** (FC Barcelona Marketing
Department), editada por A. Ric e R. Peláez, 2020. Um mergulho no estado da análise avançada de dados
no futebol, estruturado em capítulos temáticos escritos por especialistas diferentes — tracking data em
jogos/treinos, contexto tático, métricas de desempenho. Funciona como coletânea de capítulos técnicos
associada aos summits de analytics do clube, antecessora direta do relatório 2021.

**Football Analytics 2021 — The Role of Context in Transferring Analytics to the Pitch.** Segunda
edição da série da Barça Innovation Hub, com subtítulo focado no papel do **contexto** na tradução de
analytics para decisões em campo. Hospedado no subdomínio oficial `sportstomorrow.fcbarcelona.com`,
reúne contribuições internacionais em capítulos — por exemplo, o Capítulo 4, "How does context affect
player performance in football?", de Lotte Bransen, Pieter Robberechts e colaboradores (os mesmos
pesquisadores por trás do socceraction, evidenciando a ponte entre a pesquisa acadêmica da KU Leuven e
a prática de clube). O tema central é ajustar métricas de desempenho pelo contexto situacional do jogo
(adversário, placar, momento) em vez de tratá-las como números absolutos.

**Data Analytics in Football.** Livro acadêmico de **Daniel Memmert e Dominik Raabe**, Routledge, 2018,
subtítulo *Positional Data Collection, Modelling and Analysis*. Um dos primeiros livros a tratar
sistematicamente a coleta e modelagem de dados posicionais (tracking) no futebol profissional,
referência para estudantes/pesquisadores/profissionais de performance analysis — citado mais de 180
vezes na literatura acadêmica segundo o catálogo da Taylor & Francis. Foco em tracking data, distinto
do foco em event data do socceraction/kloppy.

**Fontes:** https://football-analytics-101.readthedocs.io/en/latest/introduction.html ·
https://sportstomorrow.fcbarcelona.com/wp-content/uploads/2020/11/Barca_Innovation_Hub_FOOTBALL_ANALYTICS_2021.pdf ·
https://efsupit.ro/images/stories/october2023/Art292.pdf (cita "Football Analytics: Now and Beyond") ·
https://www.taylorfrancis.com/books/mono/10.4324/9781351210164/data-analytics-football-daniel-memmert-dominik-raabe ·
https://barcainnovationhub.com/what-do-you-need-to-learn-to-work-in-football-analytics/

---

# Parte B — Mercados de apostas de futebol

## B1. Resultado (1X2 / Moneyline)

**Definição e liquidação.** O mercado 1X2 (moneyline) é o mais tradicional do futebol: o apostador
escolhe vitória da casa ("1"), empate ("X") ou vitória do visitante ("2") ao final dos 90 minutos
regulamentares mais acréscimos. Prorrogação e pênaltis (em mata-matas) normalmente **não** contam para
o mercado de "tempo regulamentar" — a liquidação usa o placar ao fim dos 90 minutos + acréscimos,
independentemente do que acontece depois.

**Variações comuns.** Além do 1X2 de tempo integral: 1X2 do 1º tempo, 1X2 do 2º tempo, e o derivado
"Draw No Bet" (aposta em vitória de um time, com reembolso em caso de empate — matematicamente
equivalente a um Handicap Asiático de linha 0).

**Relação com a modelagem estatística.** O 1X2 é o mercado canônico para ilustrar modelos de gols em
futebol. A abordagem clássica (Maher, 1982) assume que os gols do time da casa e do visitante seguem
distribuições de Poisson independentes, com médias (λ para casa, μ para visitante) determinadas por um
produto de "força de ataque", "força de defesa" e um fator de vantagem de mandante. Multiplicando as
duas PMFs de Poisson obtém-se a matriz conjunta de probabilidades para cada placar exato; somando as
células conforme a relação entre os dois valores (diagonal = empates, abaixo = vitória da casa, acima =
vitória do visitante) chega-se às três probabilidades do 1X2.

O problema da Poisson bivariada independente é que subestima sistematicamente placares baixos e
empatados (0-0, 1-0, 0-1, 1-1), porque no futebol real esses placares têm correlação negativa residual
entre os gols dos dois times que a independência não captura. Dixon e Coles (1997) resolveram isso com
um fator de correção τ(x,y,λ,μ,ρ) aplicado apenas a essas quatro células de placar baixo, com um
parâmetro de correlação ρ estimado dos dados históricos. Isso costuma reduzir levemente a probabilidade
de vitórias por margem mínima e aumentar a de empate 0-0/1-1 em relação ao Poisson simples — em um
exemplo didático citado na literatura, a correção reduziu a probabilidade de vitória do favorito de
0,71846 (Poisson simples) para 0,70951 e elevou o empate de 0,16703 para 0,18608. O parâmetro ρ é
tipicamente pequeno e negativo (entre -0,1 e -0,2), com efeito maior justamente nos placares que mais
interessam ao 1X2. Extensões usam Poisson bivariada verdadeira (com covariância explícita, à la Karlis
& Ntzoufras) ou Binomial Negativa (NB) no lugar da Poisson para capturar overdispersion em ligas
específicas. Em qualquer caso, o fluxo é sempre o mesmo: gerar/aproximar a distribuição conjunta de
placares e agregar as células segundo o sinal de (gols casa − gols visitante), truncando a grade em
algo como 0 a 8-10 gols por time.

---

## B2. Handicap Asiático e Handicap Europeu

**Definição e diferença conceitual.** Ambos ajustam artificialmente o placar final somando/subtraindo
um número de gols de um dos times antes de decidir o resultado — equilibrando times de força desigual
e aproximando as odds de 50/50. A diferença central está em como cada um trata o empate. O **Handicap
Europeu** usa linhas inteiras (-1, -2, +1...) e preserva três resultados (vitória, empate, derrota)
após o ajuste — estruturalmente idêntico a um 1X2 sobre o placar deslocado. O **Handicap Asiático**, de
origem indonésia (popularizado a partir de 1998), usa linhas em incrementos de meio gol (ou quarto de
gol) para **eliminar matematicamente o empate**: como ninguém marca meio gol, uma linha do tipo -0,5 ou
-1,5 sempre produz um vencedor. Linhas de quarto de gol servem para deixar a linha o mais próxima
possível da diferença de força esperada entre os times.

**Variações comuns.** No Handicap Asiático, linhas inteiras (0, -1, -2) ainda podem resultar em *push*
(devolução do valor apostado); por isso operadores preferem linhas de meio gol, que jamais empatam. As
**linhas de quarto de gol** (ex.: -0,25, -0,75) dividem a aposta em duas partes iguais entre as duas
linhas de meio gol adjacentes, permitindo resultados mistos ("meio ganha, meio devolvido"). O Handicap
Europeu, mantendo o empate como resultado válido, é normalmente oferecido só em linhas inteiras (ex.:
Time A -1 vence apenas ganhando por 2+ gols; empata ganhando por exatamente 1; perde caso contrário).

**Relação com a modelagem estatística.** Handicaps derivam diretamente da distribuição da **diferença
de gols**, D = GolsCasa − GolsVisitante. Essa diferença de duas Poissons independentes segue uma
distribuição de Skellam, mas na prática os modeladores calculam a matriz conjunta de placares via
Dixon-Coles (ou Poisson bivariada) e somam as células por diagonais: P(D=k) = soma de P(i,j) para
i-j=k. Para o Handicap Europeu com linha inteira h: P(vitória) = P(D>h), P(empate) = P(D=h), P(derrota)
= P(D<h) — a mesma lógica do 1X2, deslocada. Para o Handicap Asiático de meio gol h+0,5, não há
possibilidade de D=h+0,5 (D é sempre inteiro), então a aposta vira P(D>h+0,5) vs. P(D<h+0,5), sem massa
de empate a redistribuir. Para linhas de quarto de gol, calcula-se a média das probabilidades (e do
retorno esperado) das duas linhas de meio gol adjacentes. A correlação Dixon-Coles nos placares baixos
afeta sobretudo handicaps de linha pequena (0, ±0,5, ±0,25) em jogos equilibrados; handicaps de linhas
grandes (favoritismo claro) dependem quase inteiramente da correta calibração de λ e μ, não da
correlação residual.

---

## B3. BTTS (Ambas Marcam)

**Definição e liquidação.** BTTS ("Ambas Marcam"/"Gols") é uma aposta binária sobre se **os dois
times** marcarão pelo menos um gol cada durante os 90 minutos + acréscimos, independentemente do
resultado final ou placar exato. "BTTS - Sim" vence com 1-1, 2-1, 3-2 etc.; "BTTS - Não" vence em
qualquer placar onde ao menos um time fica a zero (0-0, 2-0, 0-3...). É agnóstico ao vencedor da
partida.

**Variações comuns.** BTTS & Resultado (combina com vencedor da partida), BTTS nos Dois Tempos (exige
que ambos marquem tanto no 1º quanto no 2º tempo — risco bem mais alto), BTTS & Over/Under gols, e
BTTS & Jogador Marcar. Em ligas europeias competitivas, BTTS-Sim se cumpre em torno de 50-60% das
partidas de uma temporada regular — a Premier League 2024-25 teve aproximadamente 59% dos jogos com
ambos os times marcando, segundo dados citados pelo Goal.com.

**Relação com a modelagem estatística.** Sob gols independentes, P(BTTS-Sim) = P(GolsCasa≥1) ×
P(GolsVisitante≥1), onde P(Gols≥1) = 1 − e^(−λ) sob Poisson pura. Na prática, o cálculo correto soma
diretamente da matriz conjunta de placares (Dixon-Coles) todas as células onde ambos os índices são
≥1 — incorporando automaticamente a correção de correlação ρ nos placares baixos, que afeta justamente
0-0 (BTTS-Não), 1-0, 0-1 e 1-1 (única das quatro que conta a favor do BTTS-Sim). Como o fator τ
tipicamente reduz P(1-0)/P(0-1) e aumenta P(0-0)/P(1-1) (ou vice-versa, conforme o sinal de ρ), o
efeito líquido sobre BTTS costuma ser pequeno mas não nulo, e ignorá-lo introduz viés justamente nos
jogos mais equilibrados e de poucos gols esperados.

Há relação intuitiva forte com "goleada vs. jogo fechado": confrontos muito desequilibrados tendem a
ter **menor** P(BTTS-Sim), porque o time mais fraco tem λ baixo e risco real de ficar a zero mesmo em
placar elástico (3-0, 4-1). Confrontos entre times de ataque forte mas defesa vulnerável maximizam
P(BTTS-Sim), pois exigem que **ambos** os λ individuais sejam suficientemente altos, não apenas o λ
total do jogo. Times favoritos com defesa muito sólida (λ do adversário próximo de zero) são o cenário
clássico de BTTS-Não, mesmo em partidas com total de gols esperado moderado ou alto.

---

## B4. Escanteios (total, handicap, over/under)

**Definição e liquidação.** Conta o número total de cobranças de escanteio durante a partida (tempo
regulamentar + acréscimos, sem prorrogação), somando ambos os times. As estruturas mais comuns são
**Total Over/Under** (ex.: mais/menos de 10,5) e **Handicap de Escanteios** (mesma lógica do handicap
de gols).

**Variações comuns.** Escanteios por tempo (1º/2º), por time (linha individual), "qual time terá mais
escanteios" (Handicap 0), e faixas (ex.: 7-9, 10-12). Uma partida média da Premier League tem entre 10
e 11 escanteios; o time favorito venceu a contagem de escanteios em cerca de 63,6% das partidas ao
longo de cinco temporadas — correlação mais forte que a taxa de vitórias no placar (55,6%) no mesmo
período, sugerindo que escanteios refletem domínio territorial de forma mais consistente que o
resultado final.

**Relação com a modelagem estatística.** Escanteios são modelados como variável de contagem análoga a
gols, mas com duas diferenças estruturais: a taxa esperada é maior (~5-6 por time por jogo vs. ~1,3-1,5
gols), o que facilita a estimação; e escanteios exibem **overdispersion** mais pronunciada que gols —
variância excede a média, violando a premissa da Poisson (variância = média). A literatura acadêmica
(Yip et al.; teses como a da Universidade de Lund sobre previsão de odds de escanteios) documenta o
fenômeno e testa alternativas: Binomial Negativa (NB), regressão Geométrica-Poisson e Poisson
compostas, todas acomodando variância superior à média via um parâmetro de dispersão adicional. Maher
(1982) já notava que a Poisson simples é razoável para *gols*, mas trabalhos mais recentes sobre
escanteios (que tendem a "vir em rajadas" — vários seguidos por rebotes e defesas sucessivas) mostram
que ignorar a overdispersion leva a bandas de probabilidade estreitas demais nas linhas de Over/Under,
superestimando a confiança do modelo perto da linha do mercado.

Fluxo prático: (1) estimar λ_casa e λ_visitante via regressão (Poisson, NB ou GP) usando posse de bola,
finalizações, cruzamentos e mando de campo; (2) somar/convolver as duas distribuições para o total; (3)
somar a cauda acima/abaixo da linha para Over/Under, ou a distribuição da diferença para Handicap. O
"estado de jogo" (time perdendo ataca mais, time vencendo se retranca) introduz dependência temporal
intra-jogo que modelos estáticos pré-jogo não capturam, relevante sobretudo para mercados ao vivo.

---

## B5. Cartões (amarelos, vermelhos, total, handicap)

**Definição e liquidação.** Conta advertências mostradas pelo árbitro. Na maioria das casas, cada
**cartão amarelo** vale 1 ponto e um **cartão vermelho** vale 2 pontos. Só entram na contagem cartões
mostrados a jogadores em campo — cartões para reservas/comissão técnica normalmente **não** contam, a
menos que o jogador punido entre em campo depois.

**Variações comuns.** Total de Cartões Over/Under (ex.: mais/menos de 4,5 pontos), Handicap de Cartões
(Europeu com empate possível; Asiático fracionado sem empate), Ambas Equipes Recebem Cartão (análogo
ao BTTS), Cartões por Tempo, e Cartão de Jogador Específico. Cartões vermelhos costumam ter mercado
próprio ("Haverá Cartão Vermelho? Sim/Não"), por ser evento raro (tipicamente bem abaixo de 0,3 por
jogo na maioria das ligas), não se prestando bem a uma linha de Over/Under contínua como a de amarelos.

**Relação com a modelagem estatística.** Cartões amarelos são modelados via Poisson ou Binomial
Negativa, estruturalmente parecidos com gols/escanteios, mas com covariáveis diferentes: o fator
dominante não é a força ofensiva, mas (1) o **perfil do árbitro** — árbitros têm médias de cartões
marcadamente diferentes entre si, tratado por boa parte da literatura como a variável mais preditiva do
mercado; (2) **rivalidade/importância da partida** — clássicos, jogos de título ou de fuga do
rebaixamento tendem a ter faltas/cartões acima da média histórica; e (3) **estilo tático** — retranca ou
pressão alta geram mais faltas táticas. Como o número esperado de cartões (tipicamente 3-6 pontos,
dependendo da liga) e sua variância costumam divergir da relação 1:1 exigida pela Poisson pura — em
parte porque o "efeito árbitro" atua como heterogeneidade latente entre partidas —, a Binomial Negativa
costuma se ajustar melhor, absorvendo essa heterogeneidade via seu parâmetro de dispersão. Trabalhos
acadêmicos ("Modelling Penalty Cards in Football", SIBA-ESE) usam Poisson composta para estudar
fatores que afetam cartões amarelos/vermelhos, tratando os dois tipos com estrutura conjunta (bivariada)
em vez de independente, já que jogos com muitos amarelos tendem a ter mais chance de vermelho (segunda
advertência).

Cartões vermelhos, por serem raros, são tratados de forma diferente: em vez de contagem completa, muitas
implementações modelam a ocorrência como evento binário (Bernoulli) de taxa baixa, ou por regressão
logística, ou por Poisson de taxa (λ) pequena onde P(≥1 vermelho) ≈ 1 − e^(−λ) já é aproximação
aceitável (P(2+ vermelhos no mesmo jogo) é desprezível na maioria dos contextos). Handicap e Over/Under
de cartões seguem a mesma lógica de convolução de gols/escanteios, mas a covariável "árbitro" precisa
ser tratada como efeito por partida (não por time), diferindo estruturalmente de como gols/escanteios
são modelados por força ofensiva/defensiva de cada equipe.

---

## B6. Finalizações (total de chutes, por time)

**Definição e liquidação.** Over/Under sobre o número de tentativas de chute a gol de um time (ou soma
das duas equipes) nos 90 minutos + acréscimos. Conta **todas** as tentativas — chutes no alvo, para
fora e bloqueados por defensor que não seja o "último homem". A liquidação usa o dado estatístico
oficial (tipicamente Opta) reportado ao final: linha 16,5 com 17 finalizações vence o Over.

**Variações comuns.** Total combinado da partida, total por time (Team Total Shots, o mais popular) e
handicap de finalizações. As linhas variam por perfil e mando: times de posse dominante em casa ficam
na faixa de 16,5-18,5, times medianos 11,5-13,5, contra-atacantes 8,5-10,5. O mando de campo acrescenta
de 4 a 6 finalizações por jogo em relação a jogar fora; a Bundesliga tende a ter o maior volume médio
por time entre as cinco grandes ligas europeias, com a Serie A no extremo mais baixo.

**Relação com modelagem estatística.** O total de finalizações é tratado como variável de contagem
anterior na cadeia causal aos gols, ajustado via Poisson (taxa λ por ataque/defesa/mando/ritmo,
análogo ao Dixon-Coles) com Over/Under obtido pela massa acima/abaixo da linha. Na prática, finalizações
exibem **superdispersão** — variância maior que a média —, sintoma de que a Poisson pura subestima a
cauda: o processo não é homogêneo ao longo dos 90 minutos (rajadas após escanteio, período final
perdendo, mudança por cartão vermelho, heterogeneidade de estilo entre confrontos). A alternativa
padrão é a Negative Binomial, com parâmetro de dispersão adicional de forma que Var(Y) = λ + λ²/κ > λ
— mesmo raciocínio usado para escanteios.

O uso mais relevante do total de finalizações para um sistema de previsão é como **preditor auxiliar de
gols** (proxy de xG). Times com posse elevada (>60%) tendem a gerar mais finalizações, mas volume não
implica qualidade — um time pode ter alto volume e baixa conversão (bloqueios baixos, chutes de fora da
área) enquanto outro finaliza pouco e converte com eficiência. Arquiteturas em cascata (como a usada
neste projeto) preferem decompor ainda mais em finalizações no alvo antes de estimar gols.

---

## B7. Chutes no Alvo (Shots on Target)

**Definição exata e liquidação.** Subconjunto das finalizações que, pela convenção usada por Bet365,
Paddy Power e provedores como a Opta, corresponde a qualquer tentativa que entra no gol
independentemente de intenção, ou é chute claro que teria entrado não fosse a defesa do goleiro, ou é
bloqueado por jogador que seria o "último homem" com o goleiro sem chance de evitar o gol. Chutes na
trave/travessão sem gol **não** contam como no alvo; bloqueados por qualquer outro defensor também não
contam.

**Variações comuns.** Os mesmos três formatos das finalizações (total combinado, por time, handicap),
além de mercados de jogador. O SOT é numericamente menor e mais concentrado (tipicamente 5-8 chutes no
alvo por time por jogo, contra 11-19 finalizações totais), com linhas típicas de 3,5 a 7,5 e menor
variância relativa que mercados de artilheiro.

**Relação com modelagem estatística — o encadeamento (cascata) até o gol.** O SOT é o elo intermediário
natural entre "quantas vezes o time atacou" e "quantos gols marcou". A taxa de conversão de
finalizações totais em gols gira entre 13% e 15% nas cinco grandes ligas europeias, enquanto a
conversão de chutes **no alvo** para gols salta para 29%-31% — aproximadamente um gol a cada três
chutes no alvo, contra um a cada sete finalizações totais. Essa diferença de "densidade de sinal" é o
motivo estatístico para preferir uma arquitetura em cascata: o modelo primeiro estima a distribuição de
SOT do time (Poisson ou NB, com parâmetros de ataque/defesa/mando do Dixon-Coles), e usa essa
expectativa como entrada para o estágio seguinte, que modela gols condicionalmente — capturando
"finalização" (conversão) separadamente de "criação de chances" (volume de SOT). Isso reduz a variância
do estimador final ao decompor um processo de dois estágios (gerar oportunidades → converter) em dois
submodelos mais simples e estáveis que ajustar um único modelo de gols contra covariáveis distantes
causalmente.

O SOT também exibe variância acima da média Poisson, mas geralmente menos overdispersion que o total de
finalizações bruto, porque a etapa de "filtragem" (finalização → no alvo) suaviza picos aleatórios de
volume — outro motivo para arquiteturas em cascata preferirem alimentar SOT em vez de finalizações
totais no estágio seguinte de gols. Times de alto volume e baixa precisão mostram divergência clara
entre suas taxas de finalizações totais e SOT, reforçando a necessidade de tratá-las como variáveis
distintas e correlacionadas, não intercambiáveis.

---

## B8. Over/Under (gols) e generalização para outras métricas

**Conceito central.** Over/Under (ou "total"/"goal line") é o mercado mais simples e líquido do
futebol: a casa fixa uma linha L (quase sempre terminando em ",5" para evitar empates técnicos, às
vezes inteira com regra de push) e o apostador escolhe se o total de gols ficará acima (Over) ou abaixo
(Under). A linha mais popular é **2,5 gols**, que divide o histórico de resultados de forma
relativamente equilibrada na maioria das ligas competitivas; linhas de 0,5 a 5,5+ também são comuns,
assim como o "Asian Total" com linhas quebradas (2,25, 2,75) que dividem a aposta proporcionalmente
entre duas linhas inteiras adjacentes.

**Cálculo probabilístico.** O valor justo do mercado vem diretamente da CDF da variável "gols totais".
Se o modelo produz P(X=k) para o total de gols — seja via Poisson simples (soma de duas Poissons
independentes é Poisson com parâmetro λ_casa+λ_visitante), via a matriz de placares Dixon-Coles (com
correção ρ), ou via Negative Binomial —, a probabilidade de Over em L é 1 − CDF(⌊L⌋) = P(X>⌊L⌋), e Under
é o complemento. Para L=2,5: Over 2,5 = P(X≥3) = 1 − [P(0)+P(1)+P(2)].

**A generalização — mesmo framework, distribuição diferente.** O ponto conceitual mais importante é que
esse mecanismo (estimar taxa esperada, escolher distribuição de contagem adequada, integrar a massa
acima/abaixo da linha) se aplica **sem alteração estrutural** a qualquer métrica de contagem do jogo:
escanteios, cartões, finalizações, chutes no alvo, faltas, impedimentos. O que muda é (a) os parâmetros
de taxa λ (re-estimados com covariáveis próprias de cada métrica) e (b) a distribuição-base, porque cada
métrica tem seu próprio padrão de dispersão. Gols em ligas competitivas são bem aproximados por Poisson
(variância ≈ média), mas escanteios e cartões mostram superdispersão mais acentuada — estudos sobre
previsão de escanteios relatam que a Negative Binomial (ou Poisson composta/"clusterizada") se ajusta
melhor, pois corners tendem a vir em sequências (uma cobrança gera outra, pressão ofensiva gera vários
escanteios seguidos), violando a independência de eventos que sustenta a Poisson. O mesmo vale para
cartões, cuja distribuição depende de fatores de "estado do jogo" (jogo decidido, rivalidade, arbitragem)
que também inflam a variância além do permitido pela Poisson.

Em suma: o Over/Under é uma "casca" de liquidação idêntica para qualquer contagem; a engenharia real de
um sistema de previsão está na escolha e calibração da distribuição-base (Poisson vs. Negative Binomial
vs. variantes com inflação de zeros) e das covariáveis do parâmetro de taxa para cada métrica —
exatamente a lógica que já sustenta a arquitetura deste projeto (DC-NB para gols, NB para
escanteios/cartões/finalizações como mercados independentes, todos consumindo o mesmo mecanismo de CDF
para gerar odds).

---

## B9. HT (mercados de primeiro tempo)

**Definição e principais mercados.** Os mercados de Half Time (HT) replicam a estrutura dos mercados de
tempo integral, restringindo a liquidação ao resultado ao final dos 45 minutos regulamentares (mais
acréscimos do 1º tempo). Os três mais líquidos: (1) **1X2 do intervalo** (Halftime Result); (2)
**Over/Under gols no 1º tempo**, com linhas típicas de 0,5 e 1,5 — a linha de 0,5 costuma ter odds
baixas pré-jogo (1,30-1,50), tornando-se mais interessante ao vivo, enquanto a de 1,5 paga mais
(2,50-4,00) por exigir ao menos dois gols em 45 minutos; e (3) **BTTS HT**, naturalmente mais raro que o
de tempo integral.

**Dados reais sobre proporção de gols no 1º tempo.** Um levantamento sobre mais de 100 mil partidas
(Goalstatistics) mostra que aproximadamente **74,8%** das partidas têm ao menos um gol no 1º tempo (cerca
de 25% terminam 0-0 ao intervalo), e que os últimos 15 minutos do 1º tempo produzem cerca de 1,5 vez
mais gols que os primeiros 15. Quanto à fração do total de gols da partida ocorrendo no 1º tempo,
calculadoras que replicam o modelo Poisson para HT/FT costumam adotar uma referência de aproximadamente
**45% dos gols no 1º tempo e 55% no 2º tempo** — consistente com a observação geral de que o 2º tempo
tende a produzir ligeiramente mais gols (cansaço defensivo, substituições ofensivas, urgência de times
atrás no placar).

**Modelagem estatística.** A abordagem padrão é **reescalar o λ do modelo de gols pela fração esperada
de gols em cada metade**: se o Dixon-Coles/Poisson estima λ_casa e λ_visitante para 90 minutos, os
parâmetros de 1º tempo são aproximados por λ_casa×0,45 e λ_visitante×0,45 (ajustados por time/liga
quando há dados suficientes). A partir daí, 1X2 do intervalo, Over/Under HT e BTTS HT são calculados
exatamente como os equivalentes de tempo integral, usando as taxas reduzidas.

A suposição central é a **independência aproximada dos processos de gols entre os dois tempos**,
condicional aos parâmetros do jogo: trata-se cada tempo como processo Poisson separado com taxas
proporcionais ao total, assumindo que gols no 1º tempo não alteram a distribuição esperada do 2º tempo
(dado o mesmo conjunto de forças de ataque/defesa). É uma simplificação — na prática o estado do placar
ao intervalo influencia o ritmo do 2º tempo — mas continua sendo a base padrão de mercado por capturar a
maior parte da variância observada sem exigir modelo de dependência temporal completo, o mesmo tipo de
trade-off que motiva o parâmetro ρ do Dixon-Coles para o desvio de independência em placares baixos.

---

## B10. FT (tempo total) e a relação/correlação HT/FT

**O mercado combinado HT/FT.** O mercado de Half Time/Full Time (HT/FT, ou "resultado duplo") exige
acertar simultaneamente o resultado do intervalo **e** o resultado final. Como cada momento tem três
resultados possíveis, o mercado gera exatamente **9 combinações**: Casa/Casa, Casa/Empate, Casa/Fora,
Empate/Casa, Empate/Empate, Empate/Fora, Fora/Casa, Fora/Empate e Fora/Fora. O apostador precisa acertar
as duas etapas para ganhar — o que faz do HT/FT um dos mercados de maiores odds do futebol,
especialmente nas combinações de "virada" (ex.: Fora/Casa).

**Como o produto de duas Poissons modela o HT/FT.** A forma padrão de precificar as 9 combinações é
tratar o placar do 1º tempo e o do 2º tempo (ou o placar final menos o do 1º) como **duas distribuições
Poisson bivariadas independentes**, cada uma parametrizada pela fração correspondente das taxas de
ataque/defesa do jogo completo (ver B9: ~45%/55%). Calcula-se a matriz de placares do 1º tempo e,
separadamente, a do 2º tempo — a probabilidade de qualquer combinação HT/FT é o produto das
probabilidades marginais das duas etapas, somado sobre todas as combinações de placares parciais que
produzem aquele par de resultados. Um exemplo publicado com λ_casa=0,945 e λ_visitante=0,383 apenas para
o 1º tempo mostra que a combinação mais provável tende a ser Casa/Casa (quando o mandante já é
favorito), seguida de Empate/Casa — times favoritos costumam confirmar a vantagem já mostrada ao
intervalo.

**Independência condicional vs. dependência real.** O modelo "produto de duas Poissons" assume
independência condicional dos gols nas duas metades, dado o conjunto de parâmetros do jogo — assume-se
que, fixadas as forças de ataque/defesa, o resultado do 1º tempo não muda a distribuição esperada do 2º.
Isso simplifica o cálculo (basta multiplicar duas matrizes de Poisson), mas diverge da realidade: o
**estado do placar ao intervalo influencia o comportamento tático do 2º tempo** — times perdendo tendem
a aumentar a pressão ofensiva (mais finalizações, mais gols possíveis, mas mais risco defensivo),
enquanto times na frente tendem a recuar e administrar o resultado, reduzindo a taxa de criação de
chances de ambos os lados. Esse "gerenciamento de jogo" é uma dependência dinâmica intra-partida que o
Dixon-Coles clássico — pensado para o resultado agregado de 90 minutos — não captura; o parâmetro ρ
corrige apenas a correlação entre gols da casa e visitante em placares baixos dentro do mesmo período,
não a dependência entre um período e outro.

Na prática, sistemas de previsão que oferecem HT/FT como mercado — inclusive treinando um modelo de
gols "por tempo" (1º e 2º separadamente, com parâmetros próprios estimados diretamente do histórico de
gols por tempo, em vez de derivados de fração fixa do total) — tendem a capturar parcialmente essa
dependência real de forma indireta, já que os parâmetros de ataque/defesa por tempo absorvem
endogenamente os padrões de "como o time normalmente se comporta batendo/perdendo ao intervalo". Ainda
assim, a correlação exata condicionada ao placar específico do intervalo continua sendo uma
simplificação aceita pela maioria dos modelos de mercado — modelá-la explicitamente (ex.: processo de
Poisson não-homogêneo condicionado ao placar corrente) normalmente custa mais do que ganha em precisão
para fins de precificação, embora seja fronteira ativa de pesquisa em modelagem de futebol ao vivo
(live trading).

---

# Fontes

### Parte A — Bibliotecas e ferramentas

**Scikit-Learn**
- https://scikit-learn.org/stable/modules/calibration.html
- https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html
- https://scikit-learn.org/stable/modules/linear_model.html#generalized-linear-models
- https://scikit-learn.org/stable/modules/generated/sklearn.metrics.log_loss.html
- https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html
- https://scikit-learn.org/stable/modules/model_evaluation.html

**SHAP**
- https://shap.readthedocs.io/en/latest/
- https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html
- https://shap.readthedocs.io/en/latest/api.html
- https://github.com/shap/shap

**XGBoost**
- https://xgboost.readthedocs.io/en/stable/parameter.html
- https://xgboosting.com/configure-xgboost-countpoisson-objective/

**LightGBM**
- https://lightgbm.readthedocs.io/en/latest/Parameters.html
- https://lightgbm.readthedocs.io/en/latest/Features.html
- https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html

**CatBoost**
- https://catboost.ai/docs/en/concepts/algorithm-main-stages_choose-tree-structure
- https://catboost.ai/docs/en/features/categorical-features
- https://catboost.ai/docs/en/concepts/algorithm-main-stages_cat-to-numberic
- https://catboost.ai/docs/en/references/training-parameters/common

**PyMC**
- https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html
- https://www.pymc.io/projects/examples/en/latest/
- https://www.pymc.io/

**API-Football**
- https://www.api-football.com/documentation-v3
- https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide
- https://api-sports.io/documentation/football/v3

**StatsBomb Open Data**
- https://github.com/statsbomb/open-data
- https://github.com/statsbomb/statsbombpy
- https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf

**socceraction**
- https://github.com/ML-KULeuven/socceraction
- https://socceraction.readthedocs.io/en/latest/documentation/valuing_actions/vaep.html

**mplsoccer**
- https://mplsoccer.readthedocs.io/

**Kloppy**
- https://kloppy.pysport.org/
- https://github.com/PySport/kloppy

**Livros e relatórios**
- https://football-analytics-101.readthedocs.io/en/latest/introduction.html
- https://sportstomorrow.fcbarcelona.com/wp-content/uploads/2020/11/Barca_Innovation_Hub_FOOTBALL_ANALYTICS_2021.pdf
- https://efsupit.ro/images/stories/october2023/Art292.pdf
- https://www.taylorfrancis.com/books/mono/10.4324/9781351210164/data-analytics-football-daniel-memmert-dominik-raabe
- https://barcainnovationhub.com/what-do-you-need-to-learn-to-work-in-football-analytics/

### Parte B — Mercados de apostas

- https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/
- https://statsultra.com/dixon-coles-model/
- https://www.ajbuckeconbikesail.net/wkpapers/Airports/MVPoisson/soccer_betting.pdf (Dixon & Coles, 2001)
- https://www.pinnacle.com/betting-resources/en/soccer/poisson-distribution-predicting-the-scores-in-the-world-soccer-cup-2026/md62mlxumkmxz6a8
- https://en.wikipedia.org/wiki/Asian_handicap
- https://thefootytipster.com/the-difference-between-asian-and-european-handicaps/
- https://punter2pro.com/asian-handicap-vs-european-handicap-bets/
- https://www.bettingusa.com/sports/soccer/asian-handicap/
- https://www.betwasp.com/blog/what-is-an-asian-handicap
- https://www.goal.com/en-gb/betting/what-is-both-teams-to-score-betting/blt370fa2ee32c827c1
- https://www.livescore.com/en-gb/betting-sites/strategy/what-does-btts-mean-in-betting/
- https://www.toffeeweb.com/both-teams-to-score/
- https://www.pinnacle.com/betting-resources/en/soccer/corners-betting-in-soccer-value-in-a-lesser-known-market/uty25tp3e3tfmlz5
- https://arxiv.org/pdf/2112.13001 (Yip et al., previsão de escanteios)
- https://lup.lub.lu.se/luur/download?func=downloadFile&recordOId=9127007&fileOId=9127013 (tese Lund University)
- https://stats.stackexchange.com/questions/324337/modeling-the-number-of-corners-in-soccer
- https://www.lance.com.br/sites-de-apostas/apostar-em-cartoes-amarelos.html
- https://www.gazetaesportiva.com/apostas/guias/como-apostar-cartoes
- http://siba-ese.unisalento.it/index.php/ejasa/article/view/15911 (Modelling Penalty Cards in Football)
- https://help.smarkets.com/hc/en-gb/articles/115001457989-How-to-calculate-Poisson-distribution-for-football-betting
- https://statpair.com/blog/team-total-shots-betting-statistical-edge
- https://www.betting.net/atoz/total-shots-on-target/
- https://www.rulesofsport.com/betting/football/how-does-shots-on-target-betting-work/
- https://helpcenter.paddypower.com/app/answers/detail/football-soccer-rules/
- https://help.bet365.com/s/en/sportsrules/soccer/match-statistics
- https://www.statscore.com/news-center/sport/soccer/what-does-the-shot-conversion-rate-for-goals-means-in-soccer/
- https://www.sportmonks.com/glossary/goal-conversion-rate/
- https://docs.pena.lt/y/models/negative_binomial.html
- https://www.betsfortoday.com/guides/poisson-distribution/
- https://goalstatistics.com/article/first-half-goal-stats-and-strategy
- https://gamblingcalc.com/betting/ht-ft-probability-predictor/
- https://www.goal.com/en-us/betting/half-time-full-time-betting/blt95d9173756882c35
- https://footyaccumulators.com/how-to/how-does-half-time-full-time-betting-work?
