# Base de Conhecimento — Modelos Estatísticos/Matemáticos em Análise de Futebol

> Documento de referência técnica para consulta por agentes que trabalham no projeto ApostaInfo
> (previsão probabilística de partidas — Dixon-Coles + Negative Binomial em cascata, Elo histórico,
> calibração isotônica). Não é um tutorial de implementação; é um mapa denso da teoria, história e
> trade-offs de cada família de modelo, para dar contexto ao "porquê" das escolhas já feitas no
> projeto e ao "o que mais existe" quando se avalia uma hipótese nova.

## Sumário

1. [Dixon-Coles (1997)](#1-dixon-coles-1997)
2. [Modelos de Poisson e Negative Binomial para gols](#2-modelos-de-poisson-e-negative-binomial-para-gols)
3. [Expected Goals (xG)](#3-expected-goals-xg)
4. [Bayesian Ratings para times](#4-bayesian-ratings-para-times)
5. [Elo Ratings aplicado a futebol](#5-elo-ratings-aplicado-a-futebol)
6. [Possession Value / xThreat, Packing, Pitch Control, VAEP](#6-possession-value--xthreat-packing-pitch-control-vaep)
7. [PPDA (Passes Allowed Per Defensive Action)](#7-ppda-passes-allowed-per-defensive-action)
8. [Brier Score e métricas de avaliação de previsões probabilísticas](#8-brier-score-e-métricas-de-avaliação-de-previsões-probabilísticas)
9. [Calibração de modelos probabilísticos](#9-calibração-de-modelos-probabilísticos)
10. [SHAP e Feature Importance](#10-shap-e-feature-importance)
11. [Time Series Forecasting aplicado a forma de times](#11-time-series-forecasting-aplicado-a-forma-de-times)
12. [Ranking Models genéricos: Bradley-Terry, Glicko, TrueSkill](#12-ranking-models-genéricos-bradley-terry-glicko-trueskill)

---

## 1. Dixon-Coles (1997)

### Definição

O modelo Dixon-Coles é uma extensão do modelo de Poisson independente de Maher (1982) para o placar
de partidas de futebol. Mantém gols do mandante e do visitante como variáveis Poisson com médias
determinadas por parâmetros de ataque/defesa de cada time e um efeito de mando de campo, mas corrige
duas limitações do modelo puramente independente: (a) a leve dependência empírica entre placares
baixos (0-0, 1-0, 0-1, 1-1), via um parâmetro de correlação `ρ`; e (b) a natureza dinâmica da força
dos times, via uma pseudo-verossimilhança com decaimento exponencial no tempo (**time-decay**).

### Formulação matemática

Modelo base (Maher, 1982), para um jogo entre o time `i` (mandante) e `j` (visitante):

```
X_ij ~ Poisson(λ = α_i · β_j · γ)      # gols do mandante
Y_ij ~ Poisson(μ = α_j · β_i)          # gols do visitante
```

onde `α_i` é o parâmetro de **ataque** do time `i`, `β_i` o parâmetro de **defesa** (quanto menor,
melhor a defesa) e `γ > 0` é o efeito multiplicativo de jogar em casa (home advantage).

Dixon-Coles perturbam essa distribuição conjunta com uma função `τ_λ,μ(x,y)` que só atua sobre os
placares `x,y ∈ {0,1}`:

```
Pr(X=x, Y=y) = τ_λ,μ(x,y) · Poisson(x;λ) · Poisson(y;μ)

τ_λ,μ(x,y) = 1 − λμρ        se x=0, y=0
           = 1 + λρ         se x=0, y=1
           = 1 + μρ         se x=1, y=0
           = 1 − ρ          se x=1, y=1
           = 1              caso contrário
```

com `ρ` restrito a `max(−1/λ, −1/μ) ≤ ρ ≤ min(1/(λμ), 1)`. `ρ = 0` recupera a independência total; as
distribuições marginais continuam Poisson(λ) e Poisson(μ) independentemente do valor de `ρ` — o
ajuste só redistribui massa de probabilidade *entre* os quatro placares baixos, não altera os totais
esperados de gols de cada time. Um `ρ` negativo (o caso mais comum na literatura) infla 0-0 e 1-1 e
deflaciona 1-0 e 0-1; o próprio Dixon & Coles notaram que essa correlação nasce, em parte, de efeitos
táticos reais (times evitam se expor demais quando o placar está apertado logo cedo).

Para capturar a dinâmica temporal da força dos times, os autores substituem a verossimilhança
estática por uma **pseudo-verossimilhança ponderada por tempo**, calculada em cada instante `t` a
partir apenas dos jogos passados:

```
L_t(α, β, ρ, γ) = Π_{k: t_k<t} { τ_λk,μk(x_k,y_k) · Poisson(x_k;λ_k) · Poisson(y_k;μ_k) }^φ(t−t_k)
```

com peso de decaimento exponencial `φ(t) = exp(−ξt)`. O parâmetro `ξ` (chamado de "half-life"
inversamente) foi otimizado no paper original maximizando um pseudo log-likelihood preditivo apenas
sobre o resultado (vitória/empate/derrota), não sobre o placar exato — e o valor ótimo encontrado
para dados ingleses de 1993-96, com unidade de tempo em meias-semanas, foi `ξ = 0.0065` (robusto a um
range razoável ao redor desse valor).

O paper usa 6.629 partidas das quatro divisões inglesas (1992-95) mais uma temporada de validação
(1995-96) com odds de casas de apostas para testar uma estratégia de aposta simples: apostar quando a
razão `p̂/b > r` para algum limiar `r > 1` (onde `b` é a probabilidade implícita nas odds, reescalada
para somar 1). Com `r ≈ 1.2` o retorno esperado foi positivo mesmo descontando o "take" embutido do
bookmaker (~11% no dataset).

### Histórico/origem

Publicado como Dixon, M. J. & Coles, S. G. (1997), *"Modelling Association Football Scores and
Inefficiencies in the Football Betting Market"*, Journal of the Royal Statistical Society: Series C
(Applied Statistics), 46(2), 265-280. Construído sobre o modelo de Poisson independente de Maher
(1982) e motivado por trabalho anterior sobre ineficiência de mercados de apostas (Pope & Peel, 1989;
Dixon & Pope, 1996). O artigo original já apontava limitações a resolver no futuro: parâmetros
estocasticamente atualizados (o que motivou trabalho posterior de Rue & Salvesen, 2000, e Dixon &
Robinson, 1998, sobre processos de pontos para tempos de gol) e extensão via covariáveis com
estrutura bayesiana — caminho que a literatura seguiu intensamente (ver §4).

Uma extensão importante veio de Karlis & Ntzoufras (2003), *"Analysis of Sports Data by Using
Bivariate Poisson Models"*, que propõe um modelo de Poisson bivariado "diagonal-inflated": em vez de
perturbar só 4 células como Dixon-Coles, infla toda a diagonal (placares empatados) com um parâmetro
extra, argumentando que isso corrige tanto a correlação quanto parte da super/subdispersão
observada. O pacote R `bivpois` implementa essa família (Karlis & Ntzoufras, 2005, Journal of
Statistical Software).

### Prós/contras

**Prós:**
- Simples de estimar (poucos parâmetros por time: ataque, defesa, mais `γ`, `ρ`, `ξ` globais);
  identificável mesmo com dados incompletos entre divisões/competições diferentes.
- O time-decay dá uma forma natural e bem fundamentada de "esquecer" resultados antigos sem precisar
  de uma janela móvel arbitrária.
- Décadas de uso consolidado como baseline em apostas esportivas — é literalmente o modelo mais
  citado da área (850+ citações).

**Contras / limitações conhecidas:**
- O ajuste de `ρ` é estatisticamente frágil: replicações em dados mais recentes (ex. blog
  opisthokonta.net, comparando Premier League e Bundesliga temporada a temporada) mostram que o
  sinal de `ρ` muda de temporada para temporada e frequentemente não é significativamente diferente
  de zero — nem sempre bate a direção prevista no paper de 1997. Há suspeita de overfitting do
  parâmetro `ρ` em amostras pequenas.
- É estruturalmente um modelo de **Poisson independente com uma correção pontual** só nas 4 células
  de placar baixo — não é de fato "bivariado" no sentido de covariância generalizada (crítica
  recorrente na literatura, ver discussão de Karlis/Ntzoufras vs. Dixon-Coles).
- Assume que `α_i, β_i` são "localmente constantes" — não há um modelo estocástico explícito de
  evolução (isso é o que Bayesian dynamic models tentam resolver, §4).
- A escolha de `ξ` (ou de qualquer time-decay) é uma forma de regularização heurística; encontrar o
  valor ótimo exige validação cruzada temporal cuidadosa (ver ARCHITECTURE/DOCUMENTACAO_CENTRAL do
  projeto: o sweep de pesos de gols já testado no projeto encontrou que time-decay clássico não
  ajudava adicionalmente quando combinado com o dataset de treino atual — achado registrado em
  memória do projeto, não repetir).

### Relação com outros tópicos

É a espinha dorsal teórica do stack de produção do projeto (`predictor.py` usa DC-NB em cascata).
Relaciona-se diretamente com:
- **§2** (Poisson/NB): Dixon-Coles é construído sobre Poisson; a extensão para Negative Binomial
  resolve a superdispersão que o Poisson puro não captura quando se agregam várias temporadas/ligas.
- **§4** (Bayesian ratings): a resposta natural à limitação do "θ estático" é tratar ataque/defesa
  como variáveis latentes com prior e atualização sequencial — exatamente o que modelos hierárquicos
  bayesianos (Rue & Salvesen 2000; PyMC/Stan modernos) fazem.
- **§5** (Elo): Elo é um "concorrente" mais simples (rating escalar único vs. ataque+defesa
  separados); muitos sistemas de produção combinam os dois (Elo como feature dentro do DC-NB, que é
  exatamente o que o projeto faz com `home_elo_pre`/`away_elo_pre`).
- **§9** (calibração): mesmo um bom modelo de gols pode gerar probabilidades de mercados derivados
  (over/under, dupla chance) descalibradas — por isso o projeto usa isotonic regression em cima da
  saída do DC-NB.

### Fontes

- Dixon, M. J. & Coles, S. G. (1997). "Modelling Association Football Scores and Inefficiencies in
  the Football Betting Market." *JRSS Series C*, 46(2), 265-280.
  https://www.ajbuckeconbikesail.net/wkpapers/Airports/MVPoisson/soccer_betting.pdf (texto completo)
  e https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9876.00065 (registro editorial, DOI
  10.1111/1467-9876.00065).
- Karlis, D. & Ntzoufras, I. (2003). "Analysis of Sports Data by Using Bivariate Poisson Models."
  http://www2.stat-athens.aueb.gr/~jbn/papers2/08_Karlis_Ntzoufras_2003_RSSD.pdf
- Karlis, D. & Ntzoufras, I. (2005). "Bivariate Poisson and Diagonal Inflated Bivariate Poisson
  Regression Models in R." *Journal of Statistical Software*, 14(10).
  https://www.jstatsoft.org/index.php/jss/article/view/v014i10
- opisthokonta.net — "Underdispersed Poisson alternatives seem to be better at predicting football
  results" (réplica empírica do modelo DC comparando com Poisson/NB/Delaporte/Conway-Maxwell/Double
  Poisson em EPL e Bundesliga 2010-2015). https://opisthokonta.net/?p=1210
- Dynamic Bayesian forecasting (sucessores diretos do problema deixado em aberto por Dixon-Coles):
  https://repository.lboro.ac.uk/ndownloader/files/16978277/1 e
  https://arxiv.org/html/2508.05891v1

---

## 2. Modelos de Poisson e Negative Binomial para gols

### Definição

O modelo de Poisson para gols assume que o número de gols marcados por um time num jogo é uma
variável aleatória de Poisson, cuja característica central é que **média = variância** (equidispersão).
É a base teórica de praticamente todo modelo paramétrico de placar em futebol desde Maher (1982). A
Negative Binomial (NB) generaliza a Poisson permitindo variância maior que a média
(**superdispersão**), tipicamente via uma mistura Poisson-Gamma: se a taxa `λ` de gols de um time não
é fixa mas ela mesma segue uma distribuição Gamma (refletindo heterogeneidade não observada — dias
bons/ruins, adversário específico, arbitragem, clima), a distribuição marginal do número de gols é
Negative Binomial.

### Formulação matemática

Poisson: `P(Y=k) = e^{-λ} λ^k / k!`, com `E[Y] = Var(Y) = λ`.

Modelo log-linear padrão (regressão de Poisson, GLM com link log):

```
Y_im ~ Poisson(μ_im)
log(μ_im) = β0 + home_effect + ataque_i − defesa_oponente + covariáveis
```

Negative Binomial via mistura Poisson-Gamma:

```
λ_i ~ Gamma(θ·μ_i, θ)      # θ = parâmetro de dispersão
Y_i | λ_i ~ Poisson(λ_i)
⇒ Y_i ~ NB(μ_i, θ),  com Var(Y_i) = μ_i + μ_i² / θ
```

Quando `θ → ∞`, a NB converge para a Poisson (dispersão extra desaparece). Valores finitos de `θ`
capturam variância adicional que a Poisson não modela — essencial quando os dados agregam contextos
heterogêneos (múltiplas temporadas, múltiplas ligas, ou quando a "força" de um time no papel oscila
mais do que o modelo estático de ataque/defesa prevê).

### Histórico/origem

Moroney (1956) já notara que a distribuição negative binomial ajusta-se um pouco melhor que Poisson a
contagens de gols agregadas; Reep, Benjamin & Pollard (1971) confirmaram a superdispersão em dados
agregados mas concluíram (de forma influente e um tanto niilista) que "o acaso domina o jogo". Maher
(1982) foi o primeiro a condicionar a média de Poisson na força específica de cada time (em vez de
olhar só a distribuição agregada e não-condicionada), o que muda a interpretação da dispersão: **dados
agregados, não condicionados, tendem a parecer superdispersos simplesmente porque misturam jogos com
médias esperadas (λ) muito diferentes** — isso por si só gera uma distribuição tipo Negative Binomial
mesmo que, condicionalmente a cada confronto específico, o processo seja Poisson puro. Esse é um
ponto sutil e importante: a "superdispersão" que se vê nos números crus muitas vezes desaparece (ou
inverte para subdispersão) quando se condiciona corretamente no confronto observado.

### Prós/contras

**Poisson puro:**
- Prós: parcimonioso, fácil de estimar via GLM padrão (`statsmodels`/`scikit-learn` não têm Poisson
  GLM nativo tão direto quanto R, mas é trivial via `PoissonRegressor` ou GLM customizado); base
  matemática limpa para derivar todo o resto (over/under, BTTS, handicaps são todos calculáveis
  fechando a PMF de Poisson/Skellam).
  Assunção de independência entre gols do mandante e visitante é surpreendentemente boa em dados
  agregados (Dixon & Coles mostraram empiricamente que o desvio de independência só aparece em
  placares baixos específicos).
- Contras: não acomoda superdispersão em datasets heterogêneos (múltiplas ligas/temporadas
  misturadas sem condicionamento fino); a assunção de independência gol-mandante/gol-visitante,
  embora boa em média, quebra sistematicamente perto de 0-0/1-1 (motivo de existir o `ρ` de
  Dixon-Coles).

**Negative Binomial:**
- Prós: acomoda a variância extra sem precisar inflar artificialmente parâmetros de ataque/defesa;
  natural quando o dataset de treino mistura contextos com heterogeneidade latente não capturada
  pelas features (exatamente o cenário de datasets multi-liga/multi-temporada como o do projeto).
  Cascata Poisson→NB é uma forma comum de primeiro modelar a média esperada com um regressor
  determinístico e depois deixar a componente de variância residual ser tratada por um segundo
  estágio (o padrão "em cascata" do projeto: DC estima λ/μ, e a distribuição de contagem final usada
  para as probabilidades de mercado é NB, não Poisson puro).
- Contras: mais um parâmetro para estimar (`θ`) por mercado/target, o que exige mais dados para não
  overfittar; réplicas empíricas (blog opisthokonta.net) mostraram que a NB **nunca** venceu a Poisson
  pura por AIC em comparações condicionadas em dados de Premier League/Bundesliga 2010-2015 — quem
  venceu foram justamente modelos de **subdispersão** (Conway-Maxwell-Poisson, Double Poisson), um
  achado contra-intuitivo que reforça o ponto de Maher: condicionar bem no confronto específico tende
  a *reduzir* a dispersão residual abaixo até da equidispersão de Poisson, não elevá-la — a decisão de
  usar NB deve ser guiada por gate de validação empírico no próprio dataset, não por intuição a priori.

### Relação com outros tópicos

Base matemática do Dixon-Coles (§1); a cascata Poisson-NB do projeto ApostaInfo é uma escolha de
engenharia que reconhece que a variância residual dos gols, no dataset agregado de treino do projeto
(múltiplas competições/temporadas), não é bem descrita só pela média condicional — daí NB. Relaciona-se
com calibração (§9): mesmo escolhendo a família de distribuição certa, a "probabilidade de over 2.5"
final derivada da PMF deve ainda ser calibrada isotonicamente contra a frequência observada, porque
erros de especificação de modelo (mesmo pequenos) tendem a se acumular nas caudas.

### Fontes

- Dixon & Coles (1997), já citado — Tabela 1 do paper mostra o ajuste quase perfeito de Poisson aos
  dados agregados de gol da liga inglesa.
- opisthokonta.net, "Underdispersed Poisson alternatives seem to be better at predicting football
  results" — comparação empírica AIC entre Poisson, NB, Delaporte, Conway-Maxwell-Poisson, Double
  Poisson e Dixon-Coles em 5 temporadas de EPL e Bundesliga. https://opisthokonta.net/?p=1210
- Karlis & Ntzoufras (2003), já citado — motivação para diagonal-inflation como correção alternativa
  a super/subdispersão + correlação simultaneamente.
- "Modeling Goal Scoring in Football: A Comparative Study of Inference and Prediction" (dissertação,
  DiVA portal) — revisão comparativa de Poisson GLM, hierárquico bayesiano e mistura Poisson-Gamma
  aplicados a futebol moderno. https://www.diva-portal.org/smash/get/diva2:1980101/FULLTEXT01.pdf
- "Predicting Football Match Results Using a Poisson Regression Model" (MDPI, Applied Sciences,
  2024) — revisão de Maher (1982) e Karlis & Ntzoufras com formulação do GLM log-linear moderno.
  https://www.mdpi.com/2076-3417/14/16/7230

---

## 3. Expected Goals (xG)

### Definição

Expected Goals (xG) é uma métrica que atribui, a cada finalização, uma probabilidade estimada de
resultar em gol, com base em características observáveis do chute (distância e ângulo até o gol,
parte do corpo, tipo de assistência/fase de jogo, pressão defensiva, etc.). A soma dos xG de todas as
finalizações de um time/jogador num período estima quantos gols "deveriam" ter sido marcados dado o
volume e a qualidade das chances criadas — independente de terem sido convertidas ou não.

### Metodologia

Tipicamente um modelo de classificação binária (goal/no-goal) treinado sobre milhares de finalizações
históricas, com features como:
- Distância e ângulo geométrico até o gol (ângulo de visão do gol, que é a métrica mais preditiva
  isoladamente).
- Parte do corpo usada (pé forte, pé fraco, cabeça).
- Tipo de jogada precedente (contra-ataque, escanteio, cruzamento, jogada ensaiada, rebote).
- Presença/proximidade de defensores e do goleiro (quando há dado posicional — "goalkeeper positioning"
  e "defensive pressure" nos modelos mais sofisticados, como o xGOT — expected goals on target — da
  Opta/StatsPerform).
- Provedores mais avançados (StatsBomb, Opta/StatsPerform) incorporam dados de rastreamento (tracking)
  ou "freeze frames" (posição de todos os jogadores no momento do chute), enquanto modelos mais simples
  (Understat, versões públicas) usam apenas dados de eventos.

Como resultado, **modelos de xG de provedores diferentes não são diretamente comparáveis** — cada um
usa definições de evento e conjuntos de features distintos, então o mesmo chute pode receber valores
de xG diferentes segundo StatsBomb, Opta ou Understat.

### Histórico/origem

A origem do termo é debatida. Referências pré-modernas:
- Barnett & Hilditch (1993) usaram "expected goals" ao estudar o efeito de gramados artificiais no
  desempenho em casa na Inglaterra.
- Ensum, Pollard & Taylor (2004) rodaram regressão logística sobre 930 chutes da Copa de 2002,
  identificando distância, ângulo, proximidade do defensor mais próximo, presença de cruzamento
  antecedendo o chute e número de jogadores entre o chutador e o gol como fatores significativos —
  essencialmente o esqueleto de qualquer xG moderno.
- Sander Ijtsma (2011, respectedgeek.com) e Sarah Rudd (2011, usando cadeias de Markov) formalizaram
  a ideia de "valor de chance" de forma mais próxima ao conceito atual.
- Sam Green (Opta, abril de 2012) popularizou o termo "xG" no contexto de análise de artilheiros da
  Premier League — geralmente citado como o marco de popularização pública do termo no jornalismo
  esportivo em língua inglesa.
- A métrica análoga em hóquei no gelo existe desde Alan Ryder (2004) e Brian Macdonald (MIT Sloan
  Sports Analytics Conference, 2012) — a ideia de "nem todo chute é igual" é anterior e paralela nas
  duas modalidades.
- Provedores que hoje dominam o mercado: **Opta/StatsPerform** (xG e, mais recentemente, xGOT —
  incorporando a trajetória/qualidade do chute no alvo), **StatsBomb** (xG com dados de eventos +
  freeze frames de 360°), **Understat** (modelo público, popular entre analistas independentes por
  disponibilizar dados gratuitos).

### Críticas e limitações

- **Não-padronização entre provedores**: como cada xG usa definição de evento e feature set próprios,
  comparações "xG StatsBomb 1.8" vs "xG Opta 1.5" para o mesmo jogo não são diretamente compatíveis.
- **xG não captura tudo**: gols de desvio, gols contra e situações fora do conjunto tradicional de
  eventos rotulados fogem do modelo; a natureza de baixa pontuação do futebol significa que mesmo um
  bom modelo de xG explica só uma fração da variância de resultado (times "azarados"/"sortudos" numa
  janela curta é esperado estatisticamente, não necessariamente sinal real).
- **Variância em amostra pequena**: comparações de "gols menos xG" (over/underperformance) por
  jogador/time em janelas curtas (poucos jogos) são ruidosas e sensíveis à escolha de modelo — não
  devem ser lidas como julgamento definitivo de "sorte" vs "habilidade" sem considerar o tamanho de
  amostra.
- **Interpretação probabilística correta**: um xG de 0.3 não afirma nada sobre o chute individual —
  significa que chutes com características semelhantes viram gol ~30% das vezes na base histórica.
  Confundir isso com "esse chute específico tinha 30% de chance" é um erro comum de comunicação (mas
  tecnicamente aceitável sob a interpretação frequentista de probabilidade condicional).
- Avaliação correta de um modelo de xG exige tanto discriminação (separar gol de não-gol, ex. AUC)
  quanto calibração (a frequência observada bate com a probabilidade prevista) — ver §8/§9.

### Relação com outros tópicos

xG é o análogo "por chute" do que Dixon-Coles/Poisson-NB fazem "por partida" — ambos reduzem um evento
esportivo ruidoso a uma expectativa probabilística. **xThreat (§6)** generaliza a ideia de xG para
"antes do chute": em vez de só valorizar a finalização, valoriza toda ação que aumenta a probabilidade
de finalização futura. **VAEP (§6)** generaliza ainda mais, valorizando qualquer ação (defensiva ou
ofensiva) pelo impacto na probabilidade de marcar/sofrer gol nos próximos N eventos — literalmente
usando P(gol) como a Pscore em vez de xG isolado. No contexto do projeto ApostaInfo, xG por chute não
é usado diretamente (o stack modela gols agregados via DC-NB, não eventos individuais), mas os
princípios de "probabilidade condicional bem calibrada" e "cuidado com amostra pequena" se aplicam
igualmente às métricas derivadas do projeto (ex. GAP ratings de chutes/escanteios, promovidos ao
DC-NB de clube — ver DOCUMENTACAO_CENTRAL.md §17).

### Fontes

- Wikipedia, "Expected goals" (revisão abrangente de história, metodologia e críticas, com citações
  primárias a Anzer 2021, Mead 2023, Robberechts & Davis 2020).
  https://en.wikipedia.org/wiki/Expected_goals
- "A probabilistic and dynamic reformulation of expected goals (xG): Methodological advances and
  modelling perspectives" (mini-review, ScienceDirect, 2026).
  https://www.sciencedirect.com/science/article/pii/S3050544526000241

---

## 4. Bayesian Ratings para times

### Definição

Modelos bayesianos hierárquicos tratam a força de ataque e defesa de cada time não como um número
fixo estimado por máxima verossimilhança, mas como uma variável aleatória latente com uma
distribuição de probabilidade (prior → posterior). A estrutura hierárquica típica assume que os
parâmetros de ataque/defesa de todos os times de uma liga vêm de uma distribuição comum (ex. Normal
com média e variância a estimar), o que produz **encolhimento (shrinkage)** de times com poucos dados
em direção à média da liga — uma forma automática de regularização que o MLE puro não tem.

### Formulação matemática

Estrutura padrão (equivalente hierárquico do Poisson de Maher/Dixon-Coles), como implementado em
PyMC/Stan:

```
home ~ Flat()                                  # efeito de mando de campo

τ_att ~ Gamma(0.1, 0.1)
atts_star_i ~ Normal(0, τ_att)  para cada time i
τ_def ~ Gamma(0.1, 0.1)
defs_star_i ~ Normal(0, τ_def)  para cada time i

atts_i = atts_star_i − mean(atts_star)         # restrição soma-zero p/ identificabilidade
defs_i = defs_star_i − mean(defs_star)

θ_home = exp(home + atts[time_mandante] + defs[time_visitante])
θ_away = exp(atts[time_visitante] + defs[time_mandante])

gols_mandante ~ Poisson(θ_home)
gols_visitante ~ Poisson(θ_away)
```

A diferença crucial frente ao MLE de Dixon-Coles: `atts_i` e `defs_i` não são estimados
independentemente time a time, mas "emprestam força" (**partial pooling**) da distribuição comum
`Normal(0, τ_att)`/`Normal(0, τ_def)` — times com poucos jogos disputados (early season, promovidos)
têm sua estimativa puxada em direção à média da liga, proporcionalmente à incerteza. A inferência é
feita via MCMC (NUTS/Hamiltonian Monte Carlo em Stan/PyMC) em vez de otimização pontual de
verossimilhança, produzindo uma distribuição posterior completa (não só um ponto estimado) para cada
parâmetro — o que permite quantificar incerteza (HDI/intervalos de credibilidade) em cada rating.

Extensões hierárquicas dinâmicas (Rue & Salvesen, 2000; trabalhos mais recentes como "Dynamic
Bayesian forecasting models of football match outcomes", Owen 2011, e "Bayesian weighted
discrete-time dynamic models", 2025) tratam `atts_i(t)` e `defs_i(t)` como um processo estocástico
(ex. random walk) que evolui jogo a jogo, generalizando formalmente o "time-decay" heurístico de
Dixon-Coles (§1) para uma verossimilhança de espaço de estados propriamente especificada, com o
parâmetro de "variância de evolução" estimado dos dados em vez de fixado a priori.

### Histórico/origem

A ideia de tratar força de time como efeito aleatório hierárquico vem da literatura geral de modelos
lineares generalizados mistos/bayesianos hierárquicos (Gelman & Hill, etc.), aplicada especificamente
a futebol por diversos autores ao longo dos anos 2000-2010. Rue & Salvesen (2000) propuseram um
enfoque bayesiano dinâmico explicitamente como resposta à limitação estática do Dixon-Coles original.
A popularização prática entre analistas independentes veio com o crescimento de PyMC/Stan como
ferramentas acessíveis — o exemplo mais citado no meio de blogs de análise esportiva é a "Rugby
analytics" case-study da documentação oficial do PyMC (adaptado de futebol), e o post de pena.lt
("Predicting Football Results Using Bayesian Modelling with Python and PyMC3", 2021), que mostra
exatamente o código acima e o compara com Dixon-Coles usando Ranked Probability Score (RPS) como
métrica de avaliação.

### Prós/contras

**Prós:**
- Encolhimento (shrinkage) natural resolve o problema de "poucos jogos disputados" (times promovidos,
  início de temporada, ligas com poucos dados históricos) sem heurística ad hoc.
- Quantificação de incerteza nativa (intervalo de credibilidade por time), útil para decisões que
  precisam saber "quão confiante" o modelo está, não só o ponto estimado.
- Fácil de estender: covariáveis adicionais, estrutura de correlação entre parâmetros, efeitos
  aleatórios por competição/temporada — tudo se encaixa no mesmo framework hierárquico sem redesenhar
  o modelo do zero.
- Versões dinâmicas resolvem formalmente o problema que o time-decay do Dixon-Coles resolve de forma
  heurística.

**Contras:**
- Custo computacional real: MCMC é ordens de magnitude mais lento que otimização de máxima
  verossimilhança, o que importa quando o pipeline de retreino precisa rodar em produção
  frequentemente (o predictor de produção do projeto retreina via MLE/GBM em cascata, não MCMC).
  Aproximações variacionais (ADVI) mitigam mas não eliminam o custo.
  - Modelos hierárquicos bayesianos genéricos, quando comparados empiricamente contra o Dixon-Coles
  bem ajustado em produção, historicamente **não** garantem ganho de log-loss/ECE — o benefício
  teórico do shrinkage só se traduz em ganho prático quando o dataset tem times com poucos jogos ou
  forte desbalanceamento (ligas pequenas, promovidos); em datasets grandes e maduros a diferença
  tende a ser marginal frente ao custo de implementação/manutenção.
- Identificabilidade exige a restrição soma-zero (ou equivalente) explicitamente no código — um erro
  comum de implementação é esquecer essa restrição e obter parâmetros não-identificados.

### Relação com outros tópicos

É a generalização teórica "correta" do Dixon-Coles (§1): resolve tanto o "time-decay heurístico" (via
dinâmica de estado explícita) quanto a falta de encolhimento para times com poucos dados. Compartilha
a mesma estrutura de likelihood Poisson de §2. Relaciona-se com Bradley-Terry/Glicko/TrueSkill (§12) —
todos são, no fundo, formas de estimar "força latente" de um agente competitivo a partir de resultados
de confrontos, diferindo em (a) qual distribuição de observação assumem (Poisson de gols vs.
Bernoulli/logística de vitória-derrota) e (b) se a inferência é pontual/incremental (Elo, Glicko,
TrueSkill) ou totalmente bayesiana em batch/sequencial (hierárquico bayesiano, TrueSkill via factor
graphs).

### Fontes

- pena.lt/y — "Predicting Football Results Using Bayesian Modelling with Python and PyMC3" (código
  completo do modelo hierárquico acima, comparação com Dixon-Coles via RPS).
  https://pena.lt/y/2021/08/25/predicting-football-results-using-bayesian-statistics-with-python-and-pymc3/
- PyMC official docs — "A Hierarchical model for Rugby prediction" (estrutura idêntica aplicada a
  outro esporte, usada como referência-padrão da comunidade PyMC).
  https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html
- "A Bayesian approach to predict performance in football: a case study" (PMC/NCBI, formulação formal
  do modelo hierárquico vs. não-hierárquico, dados do Brasileirão).
  https://pmc.ncbi.nlm.nih.gov/articles/PMC11949986/
- "Dynamic Bayesian forecasting models of football match outcomes with estimation of the evolution
  variance parameter" (extensão dinâmica de Rue & Salvesen).
  https://repository.lboro.ac.uk/ndownloader/files/16978277/1
- "Bayesian weighted discrete-time dynamic models for association football" (arXiv, 2025 —
  generalização mais recente do framework dinâmico).
  https://arxiv.org/html/2508.05891v1

---

## 5. Elo Ratings aplicado a futebol

### Definição

O sistema Elo, desenvolvido por Arpad Elo para xadrez (adotado pela FIDE), atribui a cada competidor
um rating escalar único que se atualiza após cada confronto com base na diferença entre o resultado
observado e o resultado esperado (dado pela diferença de ratings). Aplicado a futebol — mais
notavelmente pelo site **World Football Elo Ratings** (eloratings.net) — o sistema básico é adaptado
com três elementos que o xadrez não precisa: peso por importância do torneio, ajuste para mando de
campo, e ajuste pela margem de vitória (goal difference).

### Formulação matemática (World Football Elo Ratings)

```
R_novo = R_antigo + K × (W − W_e)
```

- `W` é o resultado observado: `1` vitória, `0.5` empate, `0` derrota.
- `W_e` é o resultado esperado (probabilidade de vitória), dado por:
  ```
  W_e = 1 / (10^(−dr/400) + 1)
  ```
  onde `dr` é a diferença de rating **mais 100 pontos de bônus para o time mandante**.
- `K` é o peso do tipo de torneio:
  - `60` — finais de Copa do Mundo
  - `50` — finais de campeonatos continentais e torneios intercontinentais principais
  - `40` — eliminatórias de Copa do Mundo, eliminatórias continentais e torneios principais
  - `30` — demais torneios
  - `20` — amistosos
- `K` é então **ajustado pela diferença de gols** no jogo: aumenta em `metade` se a vitória for por 2
  gols, em `3/4` se for por 3 gols, e em `3/4 + (N−3)/8` se for por 4 gols ou mais (`N` = diferença de
  gols). Esse ajuste multiplicativo em `K` é o mecanismo central que diferencia o Elo de futebol do
  Elo de xadrez: um resultado "mais dominante" produz uma atualização de rating maior, mesmo mantendo
  o resultado binário (W/D/L) igual.

Ratings tendem a convergir para a força real de um time relativa a seus competidores após cerca de 30
partidas; ratings de seleções com menos de 30 jogos disputados são considerados provisórios.

### Histórico/origem

Adaptado do sistema de xadrez de Arpad Elo (formalizado nos anos 1960 para a USCF, depois adotado
pela FIDE em 1970). A aplicação a futebol internacional por eloratings.net agrega dados de todas as
partidas "A" internacionais documentadas (fontes primárias: rsssf.com e outras bases históricas),
mantendo ratings retroativos desde o século XIX. É amplamente citado como referência de força relativa
de seleções nacionais (inclusive por acadêmicos e pela FIFA em análises comparativas ao seu próprio
ranking oficial, que usa uma metodologia derivada mas distinta desde 2018).

### Prós/contras

**Prós:**
- Extremamente simples de calcular e atualizar incrementalmente (`O(1)` por partida, sem precisar
  reotimizar toda a base histórica) — ideal como feature de "força pré-jogo" alimentando um modelo
  mais rico (exatamente o uso do projeto: `home_elo_pre`/`away_elo_pre` como covariáveis do DC-NB).
- Interpretável: a diferença de rating mapeia diretamente para uma probabilidade de vitória via a
  fórmula logística, o que facilita comunicação e sanity-checks.
- O ajuste por margem de vitória é uma melhoria real sobre o Elo puro de xadrez — recompensa
  desempenho dominante além do resultado binário, sem precisar de um modelo de gols completo.

**Contras:**
- Rating escalar único não separa força ofensiva de força defensiva — dois times com o mesmo Elo
  podem ter perfis completamente diferentes (ataque forte/defesa fraca vs. o oposto), o que Dixon-Coles
  (com `α`/`β` separados) captura e Elo não.
- Não modela covariância entre confrontos além do resultado agregado — não produz diretamente uma
  distribuição de placar (só uma probabilidade de W/D/L via calibração externa da diferença de
  rating), então normalmente precisa ser combinado com outro modelo para gerar mercados de gols.
- É reativo, não preditivo de tendência: reage ao resultado já ocorrido; não incorpora informação de
  forma contextual (lesões, escalação) a menos que seja usado como uma feature de um modelo maior.
- Assunções de misspecificação do modelo subjacente (Bradley-Terry/logística) foram formalmente
  estudadas (ver §12) e podem produzir vieses sistemáticos quando o padrão de confrontos não é
  bem descrito pela suposição de "vantagem transitiva" simples.

### Relação com outros tópicos

Elo é o membro mais simples e mais conhecido da família de "rating systems" que inclui Bradley-Terry
(o modelo probabilístico subjacente à fórmula logística do Elo), Glicko (que adiciona incerteza
explícita ao rating) e TrueSkill (que generaliza para times/multiplayer com incerteza bayesiana
completa) — ver §12 para a comparação formal. No projeto ApostaInfo, Elo histórico real (derivado do
próprio dataset de treino via `home_elo_pre`/`away_elo_pre`, calculado por
`scripts/build_elo_history.py`) é usado como **feature de entrada** do DC-NB, não como modelo de
previsão isolado — uma combinação comum na prática: usar Elo como sinal de força pré-jogo compacto,
deixando o modelo de gols (Dixon-Coles/Poisson-NB) fazer o trabalho de gerar a distribuição de placar
completa.

### Fontes

- eloratings.net — "About Elo Ratings" (página oficial com a fórmula completa, tabela de expectativas
  de vitória por diferença de rating, e valores de `K` por tipo de torneio).
  https://www.eloratings.net/about

---

## 6. Possession Value / xThreat, Packing, Pitch Control, VAEP

### Definição

Esta família de métricas move o foco de "resultado final" (gol, xG) para o **valor de cada ação
individual** durante a posse de bola, usando dados de eventos e/ou rastreamento (tracking) para
atribuir crédito de forma granular a passes, dribles e ações defensivas.

- **Expected Threat (xT)** — Karun Singh (2018): modela o valor de cada zona do campo como a
  probabilidade de gol nas próximas N ações, permitindo valorizar passes que não geram xG imediato mas
  colocam a bola em posição de "ameaça" futura.
- **VAEP (Valuing Actions by Estimating Probabilities)** — Decroos et al. (KU Leuven, 2019):
  generaliza a ideia para *qualquer* ação (não só passe/drible), valorizando pela mudança conjunta na
  probabilidade de marcar e de sofrer gol nas próximas ações.
- **Packing** — Stefan Reinartz/Impect: conta quantos jogadores adversários (ou especificamente
  defensores) são "ultrapassados" (bypassados) por um passe ou drible.
- **Pitch Control** — William Spearman (ex-Liverpool FC/Hudl): modelo espacial probabilístico, a
  partir de dados de rastreamento, de qual jogador controlaria a bola primeiro se ela fosse lançada
  para cada ponto do campo, gerando um "mapa de controle" contínuo do gramado.

### Formulação matemática

**xT (Karun Singh):** para cada zona `(x,y)` do campo (grade de 16×12), define-se:
```
xT(x,y) = s(x,y)·g(x,y) + m(x,y)·Σ_{z,w} T_{(x,y)→(z,w)} · xT(z,w)
```
onde `s(x,y)` é a probabilidade de chutar estando em `(x,y)`, `g(x,y)` a probabilidade de gol dado que
chutou (essencialmente um xG simplificado por zona), `m(x,y) = 1 − s(x,y)` a probabilidade de mover a
bola, e `T_{(x,y)→(z,w)}` a matriz de transição empírica (probabilidade de, ao mover, a bola ir
parar em `(z,w)`). Como o lado direito depende do próprio `xT` (dependência cíclica), resolve-se por
**iteração de ponto fixo**: inicializa `xT=0` em toda zona e itera a equação até convergência (na
prática, 4-5 iterações bastam). Na iteração 1, o resultado é essencialmente um xG por zona; cada
iteração subsequente "olha um passe adiante", incorporando a possibilidade de mais uma ação antes do
chute. O valor de uma ação específica que move a bola de `(x,y)` para `(z,w)` é simplesmente
`xT(z,w) − xT(x,y)`.

**VAEP:** para uma ação `a_i` no estado de jogo `S_i` (contexto: últimas 3 ações), define-se o valor:
```
V(a_i, x) = ΔP_scores(a_i, x) + (−ΔP_concedes(a_i, x))
```
onde `P_scores(S_i, x)` e `P_concedes(S_i, x)` são estimadas por **dois classificadores probabilísticos
treinados via aprendizado supervisionado** (tipicamente gradient boosting) sobre o rótulo "houve gol
marcado/sofrido nas próximas k ações (k=10)?" dado o estado `S_i`. O valor de uma ação é a mudança
nessas duas probabilidades entre o estado pré-ação e pós-ação — um framework mais geral que xT porque
não se restringe a passe/drible baseado em posição, e não impõe estrutura Markoviana explícita (o
contexto de 3 ações passadas entra como feature). O rating agregado de um jogador soma `V(a_i)` de
todas as suas ações, normalizado por 90 minutos: `rating(p) = (90/m)·Σ V(a_i)`.

**Packing:** métrica de contagem simples — cada passe ou drible recebe pontos iguais ao número de
jogadores adversários posicionados entre a origem e o destino da ação que foram "ultrapassados"
(deixados fora de posição de disputa imediata). Variações distinguem por linha (defensor vale mais
pontos que meio-campista, que vale mais que atacante) ou focam especificamente em defensores da última
linha (a métrica "Impect" original de Reinartz conta apenas isso, por estar mais diretamente ligada à
criação de chance de gol).

**Pitch Control (Spearman):** modelo probabilístico espacial — para cada ponto `(x,y)` do campo e cada
jogador, calcula-se a probabilidade de que *esse jogador específico* controlaria a bola primeiro se ela
fosse lançada instantaneamente para `(x,y)`, com base em posição, velocidade e tempo de reação de todos
os jogadores em campo (requer dados de rastreamento posicional, não apenas eventos). Somando sobre os
jogadores de um time, obtém-se a fração do campo "controlada" por aquele time em cada instante — uma
superfície contínua e dinâmica, ao contrário de posse de bola tradicional (medida só em % de tempo).

### Histórico/origem

- **xT**: Karun Singh publicou o método em blog pessoal (karun.in, 2018), com forte inspiração
  declarada em Cervone et al. (2014, análise de basquete via processos de decisão de Markov) — a
  ideia de "olhar além do xeque-mate" (valorizar não só o chute, mas o caminho até ele) é explicitamente
  emprestada dessa linha de pesquisa em basquete.
- **VAEP**: Decroos, Bransen, Van Haaren & Davis, "Actions Speak Louder than Goals: Valuing Player
  Actions in Soccer" (KDD 2019, arXiv:1802.07127), do grupo DTAI da KU Leuven, mesma equipe por trás do
  pacote open-source `socceraction`. Um IJCAI 2020 companion paper detalha a comparação com abordagens
  anteriores (xG chain/xG buildup, que dividem o xG do chute final igualmente entre todos os
  participantes da jogada — uma forma bem mais grosseira de atribuição de crédito que tanto xT quanto
  VAEP tentam superar).
- **Packing**: criado por Stefan Reinartz (ex-jogador do Bayer Leverkusen) e Jörg Seidel, comercializado
  pela empresa **Impect**; ganhou notoriedade pública em análises de mídia esportiva (ex. cobertura da
  campanha do Leicester City campeão 2015-16).
- **Pitch Control**: William Spearman formalizou o modelo enquanto trabalhava para clubes/empresas de
  tracking data (Hudl, depois Liverpool FC), apresentado em conferências como o Sloan Sports Analytics
  Conference; há trabalho acadêmico subsequente propondo variações do modelo de movimento subjacente
  (ex. Wu et al., "A New Metric for Pitch Control based on an Intuitive Motion Model").

### Prós/contras

**Prós (da família como um todo):**
- Resolvem o problema de "crédito binário" do futebol tradicional (assistência = tudo, passe anterior
  = nada): permitem valorizar contribuições graduais em toda a construção de jogada, não só o toque
  final.
- xT/VAEP produzem métricas com interpretação probabilística clara (xT: "probabilidade de gol nos
  próximos N eventos"; VAEP: "mudança de probabilidade de marcar/sofrer").
- Pitch Control e Packing capturam dimensões *espaciais e táticas* que métricas baseadas só em eventos
  (xG, xT event-based) não veem — ex. um passe que não avança xT mas imobiliza 4 defensores fora de
  posição.

**Contras:**
- xT clássico (Karun Singh) é uma simplificação de campo-em-zonas (16×12) que perde granularidade
  espacial fina; existe trade-off documentado entre resolução da grade e precisão/estabilidade do
  modelo (mais zonas = mais parâmetros a estimar = mais variância com dados finitos).
- VAEP e xT dependem fortemente da qualidade e granularidade dos dados de eventos disponíveis — sem
  dados de rastreamento, não capturam contexto posicional de jogadores fora da bola (compensado
  parcialmente por features de contexto como "últimas 3 ações").
- Pitch Control exige dados de rastreamento (tracking, 25 fps), que são caros e restritos a clubes/
  ligas com contrato com provedores como Second Spectrum, Tracab, StatsPerform — inacessível à maioria
  dos analistas independentes e não disponível para praticamente nenhuma competição no dataset do
  projeto ApostaInfo (que é baseado em eventos via API-Football, não tracking).
- Packing, sendo uma contagem simples, não diferencia *qualidade* do passe (um passe arriscado que
  "packa" 3 defensores mas tem alta chance de interceptação recebe o mesmo crédito que um seguro).

### Relação com outros tópicos

xT e VAEP são extensões diretas e explícitas de **xG (§3)**: iteração 1 do xT *é* um xG por zona; VAEP
usa a mesma ideia de "probabilidade de gol" como alvo, mas generaliza tanto a ação valorizada (qualquer
ação, não só chute) quanto o horizonte (próximas k ações, não só o próximo chute). Pitch Control é a
contraparte espacial-contínua do que **PPDA (§7)** tenta capturar de forma agregada e simplificada
(intensidade de pressão) — PPDA é uma proxy pobre mas barata (só precisa de dados de evento) para algo
que Pitch Control mede diretamente e com muito mais fidelidade (mas exige tracking data). Nenhuma
dessas métricas está em uso direto no projeto ApostaInfo hoje (que modela resultado agregado da
partida, não ações individuais) — mas fazem parte do "estado da arte" contextual: são o caminho que a
indústria de analytics tomou para ir além de "gols esperados" rumo a "todo o processo que gera gols",
e informam por que futuras features de "qualidade de posse"/"progressão" seriam, em princípio, um
território de pesquisa coerente com a trajetória do campo (ainda que o projeto até 2026-07-19 não
tenha dados de tracking para viabilizar pitch control, e as tentativas de sinal de "momentum de
equipe" já testadas — ver memória `bateria-momentum-jogador.md` — tenham sido reprovadas no nível de
equipe, embora tenham passado no nível de jogador).

### Fontes

- Karun Singh, "Introducing Expected Threat (xT)" (post original, com a derivação completa da equação
  de ponto fixo e visualizações). https://karun.in/blog/expected-threat.html
- Decroos, T. et al. (2019). "Actions Speak Louder than Goals: Valuing Player Actions in Soccer."
  arXiv:1802.07127. https://arxiv.org/pdf/1802.07127
- KU Leuven DTAI — "Exploring VAEP" (explicação interativa oficial do grupo de pesquisa).
  https://dtai.cs.kuleuven.be/sports/vaep/
- Decroos, T. et al. (2020). "VAEP: An Objective Approach to Valuing On-the-Ball Actions in Soccer."
  IJCAI 2020. https://www.ijcai.org/proceedings/2020/0648.pdf
- Medium (Dominic Wells), "Packing in football: Leicester City" (explicação da métrica de Reinartz/
  Impect com pontuação por linha defensiva). https://medium.com/@dominic.wells24/packing-in-football-leicester-city-18465932d5b4
- getgoalsideanalytics.com, "A history of 'pitch control'" (contexto histórico do trabalho de William
  Spearman). https://www.getgoalsideanalytics.com/everything-you-need-to-know-about-pitch-control/
- Wu, L. et al., "A New Metric for Pitch Control based on an Intuitive Motion Model" (SFU).
  https://www.sfu.ca/~tswartz/papers/pitch_control.pdf

---

## 7. PPDA (Passes Allowed Per Defensive Action)

### Definição

PPDA quantifica a intensidade de pressão (pressing) de um time: é o número de passes que o time
adversário consegue completar, na área de pressão relevante do campo, **por cada ação defensiva**
(desarme, interceptação, disputa/carrinho falhado, falta) que o time em questão realiza nessa mesma
área. Valores **baixos** de PPDA indicam pressão mais intensa (o time interrompe o adversário com
poucos passes de intervalo); valores **altos** indicam um time que "recua" e não pressiona muito.

### Formulação matemática

```
PPDA = (passes completados pelo adversário na zona de pressão) / (ações defensivas do time na mesma zona)
```

A "zona de pressão" convencionalmente considerada é os **3/5 finais do campo** em direção ao gol
adversário — ou seja, todo o campo de ataque do time que pressiona mais 1/5 do próprio campo defensivo
(a convenção de "40% do campo a partir do gol próprio, para frente", conforme definição da StatsBomb/
Opta). Ações defensivas contabilizadas: desarmes (tackles), interceptações, disputas/desarmes falhados
(challenges) e faltas cometidas.

### Histórico/origem

Métrica introduzida por **Colin Trainor**, analista independente, popularizada como proxy simples e
acessível (calculável só com dados de evento, sem tracking) de intensidade de pressing na era pós-
Klopp/Gegenpressing, quando a análise tática de imprensa passou a buscar uma forma quantitativa de
comparar estilos de jogo entre equipes.

### Prós/contras

**Prós:**
- Barata de calcular (só exige dados de eventos padrão: passes, desarmes, interceptações, faltas —
  disponível em praticamente qualquer provedor, incluindo API-Football usado pelo projeto).
- Dá, com um único número, uma leitura rápida do estilo defensivo/fora de posse de um time — útil
  para features de "estilo de jogo" em modelos de match-up (dois times de pressing alto tendem a gerar
  jogos mais abertos/caóticos, por exemplo).

**Contras:**
- **Confunde território com intensidade de pressão**: um time que domina posse/território terá PPDA
  baixo quase por construção (o adversário simplesmente tem a bola perto do próprio gol, círculo mais
  apertado), mesmo sem pressing agressivo de fato (o exemplo clássico citado é o PSG na Ligue 1 —
  dominância territorial, não necessariamente pressing extremo).
- Só conta ações *com bola* dos jogadores que efetivamente desarmam/interceptam — ignora todo o
  trabalho coletivo de "sombra"/cobertura de espaço que sustenta um pressing eficaz sem gerar disparo
  de ação defensiva registrada (a forma do bloco, distâncias entre linhas).
- Não mede *sucesso* do pressing: um time pode ter PPDA baixo cometendo muitas faltas/disputas
  falhadas na área de pressão, sendo repetidamente superado (played through) sem nunca recuperar a
  bola de fato — PPDA baixo não implica recuperação de bola eficaz.

### Relação com outros tópicos

É a versão "pobre porém acessível" do que **Pitch Control (§6)** mede de forma direta e espacialmente
rica (mas exige tracking data caro). PPDA é um bom exemplo do trade-off central da analítica esportiva
moderna: métricas baseadas em eventos são baratas e escaláveis mas estruturalmente limitadas; métricas
baseadas em tracking são ricas mas caras e restritas. Não está em uso no projeto ApostaInfo hoje (o
dataset do projeto, via API-Football, tem eventos mas o pipeline de produção não constrói PPDA como
feature) — mas é candidato natural de feature de "estilo tático" se dados de eventos detalhados por
zona do campo estiverem disponíveis no futuro.

### Fontes

- Coaches' Voice Academy, "PPDA: explained" (explicação completa com definição de zona, exemplos reais
  de temporadas 2021-22 das top-5 ligas europeias, limitações).
  https://learning.coachesvoice.com/cv/ppda-explained-passes-per-defensive-action/
- Hudl/StatsBomb Data Glossary, "Passes Per Defensive Action (PPDA)".
  https://support.hudl.com/s/article/passes-defensive-action?topic=Statsbomb_Global_Football_Data_Glossary
- Wyscout Data Glossary, "PPDA" (atribuição da métrica a Colin Trainor).
  https://dataglossary.wyscout.com/ppda/

---

## 8. Brier Score e métricas de avaliação de previsões probabilísticas

### Definição

Métricas de avaliação para modelos que produzem **probabilidades** (não só uma classificação
binária) precisam medir mais do que acurácia — precisam medir se a probabilidade em si é informativa
e honesta. As duas métricas centrais são **proper scoring rules** (regras de pontuação próprias): o
**Brier Score** e o **Log Loss** (entropia cruzada). Uma regra de pontuação é "própria" (proper) se é
minimizada, em expectativa, exatamente quando o modelo reporta a probabilidade verdadeira — ou seja, o
modelo não pode "trapacear" distorcendo a probabilidade reportada para melhorar artificialmente o
score.

### Formulação matemática

```
Brier Score = (1/n) Σ (p_i − y_i)²
Log Loss    = −(1/n) Σ [ y_i·log(p_i) + (1−y_i)·log(1−p_i) ]
```

onde `p_i` é a probabilidade prevista e `y_i ∈ {0,1}` o rótulo observado. Ambas são estritamente
próprias. Diferenças de comportamento:
- **Brier** é um erro quadrático médio sobre probabilidades — limitado em `[0,1]`, simétrico,
  relativamente insensível a excesso de confiança extremo (um erro de 0.99→0 custa só ~0.98 de
  penalidade quadrática).
- **Log Loss** cresce sem limite quando uma previsão confiante está errada (`log(0) → −∞`) — pune
  overconfidence de forma muito mais severa, o que a torna sensível a caudas mas também mais informativa
  para expor um modelo mal calibrado nas extremidades.

A **decomposição de Murphy (1973)** divide o Brier Score em três componentes aditivos:
```
Brier = Reliability − Resolution + Uncertainty
```
- **Reliability** (confiabilidade/calibração): o quanto a probabilidade prevista, em média por bin,
  diverge da frequência observada — quanto menor, melhor (é exatamente o que a calibração corrige,
  §9).
- **Resolution**: o quanto as frequências condicionais por bin se afastam da taxa-base geral — quanto
  maior, melhor (mede poder discriminativo real do modelo; só um modelo melhor, não recalibração,
  aumenta isso).
- **Uncertainty**: a variância intrínseca da taxa-base `p(1−p)` — propriedade dos dados, não do
  modelo.

Diagnóstico visual complementar: o **reliability diagram** (diagrama de confiabilidade) agrupa
previsões em bins de confiança e plota a frequência empírica observada (eixo Y) contra a probabilidade
média prevista no bin (eixo X) — um modelo perfeitamente calibrado forma a diagonal de 45°. O resumo
escalar mais usado desse diagrama é o **Expected Calibration Error (ECE)**:
```
ECE = Σ_b (|S_b|/n) · |acc(S_b) − conf(S_b)|
```
soma ponderada, por bin `b`, da diferença absoluta entre a taxa de acerto empírica `acc(S_b)` e a
confiança média prevista `conf(S_b)` no bin. ECE **não é** uma proper scoring rule (só mede
calibração/reliability isoladamente) — deve sempre ser reportado junto de Brier/log-loss, nunca
sozinho, porque um modelo pode ter ECE baixo com pouquíssimo poder discriminativo (ex. sempre prever a
taxa-base).

### Histórico/origem

Brier Score: Glenn W. Brier (1950), "Verification of forecasts expressed in terms of probability",
Monthly Weather Review — originado em meteorologia (previsão de chuva), depois adotado amplamente em
qualquer domínio de previsão probabilística, incluindo esportes. A decomposição em reliability/
resolution/uncertainty é de Allan Murphy (1973). Refinamentos mais recentes de estabilidade estatística
dos diagramas de confiabilidade (o método **CORP** — isotonic-regression-based, para evitar
instabilidade de binning arbitrário) são propostos em trabalho de 2021-22 na PNAS.

Um caso especial de proper scoring rule para resultados de mais de duas categorias (o caso de futebol:
vitória/empate/derrota) é o **Ranked Probability Score (RPS)**, que — diferente do Brier multiclasse
"ingênuo" — respeita a natureza *ordenada* das categorias (por exemplo, para um resultado de vitória
do mandante, uma previsão que erra para "empate" deveria ser penalizada menos que uma que erra para
"vitória do visitante"). RPS é a métrica padrão de avaliação usada na literatura acadêmica específica
de previsão de resultados de futebol (aparece, por exemplo, na comparação Dixon-Coles vs. Bayesian
hierárquico do pena.lt citado em §4).

### Prós/contras

- **Brier**: fácil de interpretar como "erro quadrático de probabilidade", decomposição de Murphy é
  clássica e bem entendida; porém insensível a erros extremos de confiança.
- **Log Loss**: é a função objetivo nativa de regressão logística/muitos classificadores — penaliza
  duramente overconfidence, o que a torna sensível para detectar modelos "confiantes demais" (comum em
  redes neurais modernas treinadas com cross-entropy, que tendem a empurrar probabilidades para 0/1
  além do ponto de acurácia probabilística ótima — fenômeno bem documentado na literatura de
  calibração de deep learning).
- **ECE**: resumo escalar prático, mas sensível à escolha de binning (largura igual vs. contagem
  igual por bin pode produzir valores bem diferentes) — sempre reportar junto com o diagrama visual,
  nunca como número isolado.
- Recomendação de boas práticas (consolidada na literatura): reportar Brier, log-loss, ECE, o
  diagrama de confiabilidade e uma métrica de ranqueamento (AUC ou RPS) em conjunto — nenhuma métrica
  isolada captura todas as dimensões de qualidade de uma previsão probabilística.

### Relação com outros tópicos

É o critério de avaliação objetivo por trás do "gate de validação" que qualquer modelo (Dixon-Coles,
Bayesian, xG) precisa passar antes de ir para produção — inclusive o §6 do doc-mestre do projeto
ApostaInfo (`DOCUMENTACAO_CENTRAL.md`), que exige "reduzir log-loss sem piorar ECE" como critério de
promoção. Motiva diretamente a necessidade de **calibração (§9)**: um modelo pode ter boa resolução
(discriminação) mas reliability ruim — a calibração corrige especificamente o termo de reliability sem
mexer no termo de resolution.

### Fontes

- MetricGate, "Brier Score vs Log Loss vs Calibration" (definições formais, decomposição de Murphy,
  citação de Dawid 1982). https://metricgate.com/blogs/brier-score-vs-log-loss-vs-calibration/
- impliedscore.com, "Football Probability Calibration: Brier Score & Log Loss" (aplicação específica a
  probabilidades de futebol, reliability diagrams, resolution, validação out-of-sample).
  https://impliedscore.com/football-probability-calibration/
- "Stable reliability diagrams for probabilistic classifiers" (PNAS/PMC — método CORP, generalização
  moderna da decomposição de Murphy com garantias de estabilidade estatística).
  https://pmc.ncbi.nlm.nih.gov/articles/PMC7923594/

---

## 9. Calibração de modelos probabilísticos

### Definição

Um classificador probabilístico é **calibrado** (ou confiável/reliable) quando, entre todas as
instâncias às quais ele atribui probabilidade `p`, aproximadamente uma fração `p` de fato pertence à
classe positiva. Muitos modelos de machine learning (SVMs, árvores boosted, redes neurais) produzem
scores que discriminam bem entre classes (boa resolução/AUC) mas cuja escala numérica não corresponde
a probabilidades verdadeiras — a calibração é o passo de pós-processamento que corrige essa escala sem
alterar a ordenação/ranking do modelo (idealmente).

### Formulação matemática — os dois métodos clássicos

**Platt Scaling** (sigmoid scaling): ajusta uma regressão logística de um parâmetro sobre o score bruto
do classificador `f(x)`:
```
P(y=1|x) = 1 / (1 + exp(A·f(x) + B))
```
com `A, B` estimados por máxima verossimilhança num conjunto de calibração separado (held-out, nunca
o conjunto de treino do modelo base). Funciona melhor quando a distorção da probabilidade é
aproximadamente sigmoidal — o caso clássico de SVMs, mas também eficaz em boosted trees e mesmo Naive
Bayes.

**Isotonic Regression**: ajusta uma função **não-paramétrica, monótona não-decrescente** (step
function) que minimiza o erro quadrático sujeito à restrição de monotonicidade:
```
minimizar Σ (y_i − f̂_i)²   sujeito a   f̂_i ≥ f̂_j sempre que f_i ≥ f_j
```
É estritamente mais geral que Platt scaling (não assume forma sigmoidal, só monotonicidade) — pode
corrigir qualquer distorção monótona do modelo base, à custa de ser mais propensa a overfitting em
datasets pequenos (mais parâmetros efetivos que o Platt de 2 parâmetros).

**Temperature Scaling**: uma variante de Platt de parâmetro único aplicada aos *logits* (antes da
softmax) em vez da probabilidade final — popular especificamente para calibrar redes neurais profundas
modernas, que tendem a ser sistematicamente overconfident quando treinadas com cross-entropy além do
ponto de acurácia ótima.

### Regra prática de escolha

A literatura (e a documentação oficial do scikit-learn) converge num critério simples: **isotonic
regression tende a igualar ou superar Platt scaling quando há dados de calibração suficientes**
(porque sua flexibilidade extra só ajuda, não atrapalha, com amostra grande); com poucos dados de
calibração, Platt scaling tende a generalizar melhor por ter muito menos parâmetros a estimar. Um
detalhe técnico frequentemente esquecido: isotonic regression introduz **empates** na probabilidade
calibrada final (função em degraus), o que pode alterar levemente métricas de ranking (AUC) que dependem
de desempates — normalmente um efeito pequeno, mas vale checar.

### Histórico/origem

Platt Scaling: John Platt (1999), desenvolvido originalmente para calibrar as saídas de SVMs (que não
produzem probabilidades nativamente, só uma distância à margem). Isotonic Regression como técnica de
calibração de classificadores: popularizada por trabalhos de Zadrozny & Elkan (2001-2002). Ambas hoje
são implementações de primeira classe em `sklearn.calibration` (`CalibratedClassifierCV`), com a opção
`method="sigmoid"` (Platt) ou `method="isotonic"`.

### Prós/contras

**Platt Scaling:**
- Prós: poucos parâmetros (2), funciona bem com poucos dados de calibração, suave (sem degraus,
  preserva melhor granularidade de ranking).
- Contras: assume forma sigmoidal da distorção — se a miscalibração real do modelo não for sigmoidal,
  a correção fica sistematicamente errada em algum trecho da curva.

**Isotonic Regression:**
- Prós: não assume forma paramétrica nenhuma além de monotonicidade — corrige qualquer distorção
  monótona; evidência empírica recorrente mostra melhoria de ECE maior que Platt em datasets grandes
  (uma comparação citada mostra ~22% de melhoria média de ECE sobre Platt em 18 de 20 combinações
  classificador/feature testadas).
- Contras: mais propensa a overfitting com poucos dados de calibração; produz função em degraus (perde
  granularidade contínua); precisa de um conjunto de calibração maior para não introduzir ruído.

### Relação com outros tópicos

É a ferramenta que resolve exatamente o termo de **reliability** da decomposição de Murphy do Brier
Score (§8) — calibração não melhora resolution (poder discriminativo), só reliability. É diretamente
relevante ao projeto: `DOCUMENTACAO_CENTRAL.md` documenta a promoção de calibração isotônica para
mercados de over/under (escanteios, a-gol, cartões) como a "1ª melhora aprovada" registrada no histórico
do projeto (ver memória `calibracao-ou-promovida.md`) — um caso concreto onde o modelo de contagem
(Poisson/NB) tinha boa discriminação mas miscalibração residual nas caudas, corrigida por isotonic
regression pós-hoc sem precisar reestimar o modelo de contagem em si. Relaciona-se também com xG (§3):
avaliar um modelo de xG corretamente exige checar tanto discriminação (separar gol de não-gol) quanto
calibração (a probabilidade bate com a frequência real).

### Fontes

- scikit-learn, "1.16. Probability calibration" (documentação oficial, formulação de isotonic
  regression, discussão de quando isotonic supera sigmoid).
  https://scikit-learn.org/stable/modules/calibration.html
- Wikipedia, "Platt scaling" (formalização do problema, análise de quando funciona bem).
  https://en.wikipedia.org/wiki/Platt_scaling
- MetricGate/kingsubham27 (Medium), comparações práticas Platt vs. isotonic com curvas de calibração
  e Brier Score antes/depois.
  https://kingsubham27.medium.com/calibration-techniques-and-its-importance-in-machine-learning-71bec997b661

---

## 10. SHAP e Feature Importance

### Definição

SHAP (**SHapley Additive exPlanations**) é um framework unificado para explicar previsões individuais
de qualquer modelo de machine learning, atribuindo a cada feature um "valor de importância" para uma
previsão específica, baseado nos **valores de Shapley** da teoria dos jogos cooperativos (Lloyd
Shapley, 1953) — a única solução que satisfaz simultaneamente as propriedades de Eficiência, Simetria,
Dummy (feature irrelevante recebe valor zero) e Aditividade.

### Formulação matemática

A previsão do modelo `f(x)` para uma instância `x` é decomposta como soma de um valor-base (a previsão
média sobre todo o dataset) mais a contribuição de cada feature:
```
f(x) = φ_0 + Σ_j φ_j
```
onde `φ_0` é o valor esperado do modelo (baseline) e `φ_j` é o valor de Shapley da feature `j` — a
contribuição marginal média dessa feature, calculada sobre **todas as ordens possíveis de inclusão**
das features (todas as "coalizões"):
```
φ_j = Σ_{S ⊆ F\{j}} [|S|!(|F|−|S|−1)! / |F|!] · [f(S∪{j}) − f(S)]
```
Isso é computacionalmente caro (exponencial no número de features) para calcular exatamente; SHAP
propõe métodos de aproximação eficientes — **KernelSHAP** (agnóstico ao modelo, usa amostragem
ponderada de coalizões) e variantes específicas de modelo muito mais rápidas como **TreeSHAP**
(exploração exata da estrutura de árvores em modelos como XGBoost/LightGBM/GBM sklearn, com custo
polinomial em vez de exponencial) — o que tornou o cálculo prático em escala e foi, segundo a
literatura, o principal motivo da adoção massiva de SHAP na indústria.

### Histórico/origem

Lundberg & Lee (2017), "A Unified Approach to Interpreting Model Predictions" (NeurIPS 2017,
arXiv:1705.07874) — unifica formalmente várias técnicas de interpretabilidade preexistentes (incluindo
LIME) sob a lente teórica dos valores de Shapley, e propõe as aproximações eficientes que tornaram o
método praticável. O paper acumulou dezenas de milhares de citações, tornando-se um dos artigos de
machine learning mais citados da década.

### Prós/contras

**Prós:**
- Fundamentação teórica sólida em teoria dos jogos — é a *única* atribuição que satisfaz as quatro
  propriedades de justiça mencionadas, o que dá credibilidade acima de heurísticas ad hoc de feature
  importance.
- Explicações **locais** (por previsão individual) e **globais** (agregando SHAP values sobre todo o
  dataset) são consistentes entre si — a importância global é literalmente a agregação das explicações
  locais, ao contrário de métodos que calculam importância global e local por caminhos matematicamente
  desconectados.
- TreeSHAP torna o cálculo viável em produção para os próprios modelos de árvore/gradient boosting que
  o projeto usa (scikit-learn GBM).

**Contras:**
- Ainda caro para modelos não-baseados-em-árvore de alta dimensionalidade (KernelSHAP escala mal); em
  modelos com muitas features correlacionadas, a interpretação de "contribuição individual" pode ser
  enganosa (duas features altamente correlacionadas dividem crédito de forma que pode confundir,
  mesmo satisfazendo as propriedades formais).
- Quando se usa amostragem condicional (em vez de marginal) para lidar com features ausentes, uma
  feature que o modelo nem sequer usa pode, ainda assim, receber valor de Shapley não-nulo — um
  detalhe técnico sutil que exige cuidado na interpretação.
- SHAP explica *o que o modelo aprendeu*, não *causalidade real* — uma feature com SHAP alto é
  importante para a previsão do modelo, não necessariamente uma causa real do fenômeno (confusão comum
  fora do círculo técnico).

### Relação com outros tópicos

Não é um modelo preditivo em si (diferente de todos os outros tópicos deste documento) — é uma
ferramenta de **diagnóstico e comunicação** aplicável a qualquer modelo do projeto (o GBM em cascata do
DC-NB, os classificadores de mercados por-tempo/marcador-primeiro/GAP ratings, etc.). É especialmente
relevante quando se testa uma hipótese de feature nova (o processo de pesquisa do projeto, documentado
em `DOCUMENTACAO_CENTRAL.md` §8/§9/§13 e `backend/docs/PESQUISA_CLUBES.md`): SHAP ajuda a entender *por
que* uma feature nova passou (ou não) no gate de validação, indo além do log-loss agregado para revelar
se o ganho vem de casos específicos (uma competição, uma faixa de Elo) ou é distribuído de forma
consistente — informação que orienta decisões como a promoção de GAP ratings ao DC-NB de clube (§17 do
doc-mestre).

### Fontes

- Lundberg, S. & Lee, S.-I. (2017). "A Unified Approach to Interpreting Model Predictions."
  arXiv:1705.07874. https://arxiv.org/abs/1705.07874
- Christoph Molnar, "Interpretable Machine Learning" — capítulo 18, SHAP (explicação didática detalhada
  da teoria, KernelSHAP, TreeSHAP, pontos fortes/fracos).
  https://christophm.github.io/interpretable-ml-book/shap.html

---

## 11. Time Series Forecasting aplicado a forma de times

### Definição

Aplicação de métodos clássicos de séries temporais (ARIMA, suavização exponencial, modelos de espaço
de estados, e mais recentemente redes recorrentes como LSTM/GRU) para modelar a sequência de resultados
ou métricas de desempenho de um time ao longo do tempo, tratando "forma" (form) como um processo
estocástico com possível autocorrelação, tendência ou sazonalidade, em vez de um número estático.

### Abordagens na literatura

- **ARIMA/modelos autorregressivos clássicos**: aplicados a sequências de resultados ou métricas
  agregadas (gols marcados/sofridos, pontos) de um time — a literatura de esportes em geral (incluindo
  futebol) usa ARIMA principalmente para prever métricas de *contexto* (ex. frequência de público,
  audiência) mais do que resultado direto de partida, porque a natureza discreta e fortemente
  contextual (adversário específico, mando de campo) do resultado de uma partida não se encaixa bem na
  suposição de um processo autorregressivo estacionário simples.
- **Modelos de espaço de estados (state-space) e dinâmica bayesiana**: essa é, na prática, a forma
  dominante e mais bem-sucedida de "time series" aplicada a força de time em futebol — é exatamente a
  extensão dinâmica do Dixon-Coles mencionada em §1/§4 (Rue & Salvesen 2000 em diante), que trata
  `α_i(t)`/`β_i(t)` como um passeio aleatório (random walk) ou processo autorregressivo latente, com
  inferência via filtro de Kalman ou MCMC sequencial — muito mais robusto teoricamente que ARIMA
  aplicado ingenuamente à sequência de resultados brutos, porque respeita a estrutura condicional
  time-vs-time do problema.
- **Deep learning sequencial (LSTM/GRU)**: aplicado com sucesso documentado a séries temporais
  contextuais em esporte (ex. previsão de público em estádios da NFL, comparando LSTM/GRU com métodos
  clássicos), mas a aplicação direta a "forma de time → resultado de próxima partida" enfrenta o mesmo
  obstáculo estrutural do ARIMA: dados esparsos por time (poucas dezenas de jogos por temporada) tornam
  modelos sequenciais profundos propensos a overfitting sem transferência de informação entre times
  (pooling), motivo pelo qual a literatura de ponta prefere as abordagens hierárquicas bayesianas (§4)
  ou o time-decay do Dixon-Coles (§1) a redes recorrentes puras por time.

### Prós/contras

**Prós:**
- Formaliza matematicamente a intuição de "forma recente pesa mais" além do time-decay heurístico —
  um filtro de Kalman, por exemplo, estima explicitamente a variância de processo (quanto a força real
  do time varia jogo a jogo) em vez de fixá-la a priori como faz o `ξ` do Dixon-Coles.
- Métodos de espaço de estados produzem naturalmente intervalos de incerteza que crescem com o tempo
  desde a última observação — útil para lidar com pausas de temporada, lesões prolongadas, etc.

**Contras:**
- Séries de resultados de futebol são curtas (uma temporada tem ~38 jogos para um time em uma liga),
  ruidosas, e fortemente dependentes do adversário específico de cada rodada — isso quebra a suposição
  central de estacionariedade/autocorrelação simples que sustenta ARIMA clássico aplicado ingenuamente
  à sequência "pontos por jogo" ou "resultado".
- No próprio projeto ApostaInfo, a pesquisa registrada em memória (`bateria-momentum-jogador.md`) já
  testou hipóteses de "momentum" de **equipe** no resultado (uma forma de sinal de série temporal de
  curto prazo) e elas foram reprovadas repetidamente sob o gate de validação — o sinal de momentum que
  *passou* foi o de **jogador** (ex. AUC de goleador melhorou de 0.68 para 0.71), não o de equipe. Isso
  é consistente com a literatura: forma recente agregada por equipe tende a ser dominada por ruído
  quando comparada a um bom rating de força já condicionado no adversário (Elo, Dixon-Coles); sinal de
  série temporal de jogador individual (finalizações recentes, por exemplo) carrega mais informação
  incremental genuína.
- Uma tentativa relacionada e já registrada no projeto (`relatorio4-proximos-passos.md`) — "forma-blend"
  — ficou em estado "âmbar" (precisa validar contra o Dixon-Coles real antes de qualquer promoção), o
  que reforça que qualquer novo sinal de série temporal de forma agregada precisa necessariamente
  passar pelo gate §6 antes de ser considerado, e que a literatura acadêmica generalista sobre "forecasting
  de forma" tende a superestimar o valor incremental desse sinal quando comparado contra um bom rating
  de força condicionado (Dixon-Coles/Elo já capturam boa parte do que "forma" tentaria capturar
  adicionalmente).

### Relação com outros tópicos

É, na prática, o mesmo problema que o **time-decay do Dixon-Coles (§1)** e a **extensão dinâmica
bayesiana (§4)** já resolvem de forma mais adequada ao domínio (condicionando no adversário, não
tratando resultado bruto como série univariada). Relaciona-se com **Elo (§5)**, que já é, na sua
essência, um filtro sequencial simples (atualização incremental após cada jogo) — uma forma
rudimentar mas eficaz de "forecasting" de força latente sem exigir maquinário de séries temporais
completo. O achado mais importante para o contexto do projeto é metodológico, não sobre uma técnica
específica: qualquer hipótese de "forma"/"momentum" precisa ser testada contra o benchmark real
(Dixon-Coles de produção) sob o gate §6, porque a literatura mostra repetidamente que esse tipo de
sinal, embora teoricamente atraente, frequentemente não entrega ganho incremental quando o modelo base
já é bom.

### Fontes

- "Forecasting in Sport: The Power of Social Context — A Time Series Analysis with English Premier
  League Soccer" (ResearchGate).
  https://www.researchgate.net/publication/258142677_Forecasting_in_Sport_The_Power_of_Social_Context_-_A_Time_Series_Analysis_with_English_Premier_League_Soccer
- "Time-Series Forecasting in Sports: Using LSTM and GRU for Stadium Attendance" (Sciendo/PCSSR) —
  exemplo de aplicação de deep learning sequencial a métrica de contexto esportivo (não resultado
  direto de partida). https://sciendo.com/2/v2/download/article/10.2478/pcssr-2025-0027.pdf
- Rue & Salvesen e sucessores (já citados em §4) como a linha de pesquisa que resolve "forma dinâmica"
  de forma estruturalmente mais adequada ao futebol do que ARIMA genérico.

---

## 12. Ranking Models genéricos: Bradley-Terry, Glicko, TrueSkill

### Definição

Esta é a família geral de modelos estatísticos para estimar a "força" latente de competidores a partir
de resultados de confrontos pareados (ou multiway). Elo (§5) é o membro mais simples e mais conhecido;
Bradley-Terry é o modelo probabilístico formal subjacente à fórmula logística do Elo; Glicko adiciona
incerteza explícita ao rating; TrueSkill generaliza tudo para times/multiplayer com inferência bayesiana
completa via grafos de fatores.

### Formulação matemática

**Bradley-Terry** (1952): modelo probabilístico de comparação pareada — a probabilidade do competidor
`i` vencer o competidor `j` é
```
P(i vence j) = π_i / (π_i + π_j)
```
onde `π_i > 0` é a "força" do competidor `i` (equivalentemente, com `π_i = exp(s_i)`, isso vira a forma
logística padrão `P = 1/(1+exp(-(s_i-s_j)))` — exatamente a fórmula de expectativa de vitória do Elo,
§5). A variante gaussiana do mesmo problema de comparação pareada é o **modelo de Thurstone (Case V)**
— TrueSkill usa essa formulação (CDF Gaussiana) em vez da logística de Bradley-Terry.

**Glicko** (Glickman, 1995): estende Elo/Bradley-Terry introduzindo uma segunda variável por
competidor — o **rating deviation (RD)**, que representa a incerteza/confiança na estimativa do
rating (análogo a um desvio-padrão). Um jogador com poucos jogos recentes tem RD alto (rating
"provisório", análogo à convenção de 30 jogos do World Football Elo); o algoritmo de atualização usa
uma função `g(RD)` que reduz o impacto de resultados contra oponentes com RD alto (resultado incerto
contra oponente de força mal-conhecida ensina menos). Glicko-2 (Glickman, 2012) adiciona ainda um
terceiro parâmetro, **volatilidade**, capturando o quão consistente/errático tem sido o desempenho do
competidor.

**TrueSkill** (Herbrich, Minka & Graepel, Microsoft Research, 2006): generaliza Glicko para (a) mais de
dois competidores/times por partida e (b) resultados que são permutações/rankings, não só
vitória-empate-derrota binária. Representa a força de cada jogador como uma distribuição Gaussiana
`N(μ, σ²)` e usa **passagem de mensagens aproximada em um grafo de fatores** (approximate message
passing / expectation propagation) para inferir a distribuição posterior de força de cada jogador após
cada partida — uma forma de inferência bayesiana online muito mais rica que a atualização pontual do
Elo. Comparado empiricamente pelos próprios autores contra Elo (com performance gaussiana) em dados
reais do Xbox Live (Halo 2), TrueSkill convergiu mais rápido para a força real de jogadores novos e
produziu partidas mais equilibradas (medido pela taxa de empates em jogos que os respectivos sistemas
classificaram como "disputados").

### Histórico/origem

- **Bradley-Terry**: Ralph Bradley & Milton Terry (1952), formalizando um modelo já esboçado por Zermelo
  (1929) — é o modelo estatístico padrão de comparação pareada em toda a literatura de ranking desde
  então (chess, esportes, votação, testes de preferência de produto).
- **Glicko**: Mark Glickman (1995, *Amer. Chess Journal*; formalização estatística em 1999, *Applied
  Statistics*) — desenvolvido explicitamente para corrigir a falta de tratamento de incerteza do Elo
  clássico usado pela USCF.
- **TrueSkill**: Herbrich, Minka & Graepel (Microsoft Research, NeurIPS 2006) — desenvolvido para
  matchmaking no Xbox Live, hoje usado (com variações) em múltiplos sistemas de matchmaking de jogos
  online.

### Prós/contras

**Bradley-Terry:**
- Prós: fundação teórica limpa, base de quase todo sistema de rating pareado subsequente.
- Contras: assume **transitividade** estrita (se A tende a vencer B e B tende a vencer C, o modelo força
  A a ter maior probabilidade de vencer C) — trabalho recente (Oliveira et al., 2018, citado em estudos
  de misspecificação) mostra que essa suposição falha visivelmente em domínios com muitos competidores
  de força comparável (ex. ~200 programas de xadrez computacional testados), e o mesmo tipo de
  não-transitividade (pedra-papel-tesoura tático entre estilos de jogo) é uma preocupação legítima, ainda
  que difícil de quantificar, em futebol.

**Glicko:**
- Prós: resolve o problema mais prático do Elo puro (tratar igualmente um rating "recém-calculado com
  poucos jogos" e um rating "maduro com centenas de jogos") sem precisar de heurística ad hoc como o
  "primeiros 30 jogos são provisórios" do World Football Elo.
- Contras: ainda assume ordenação total/transitividade como Bradley-Terry; mais complexo de
  implementar e comunicar que Elo puro.

**TrueSkill:**
- Prós: generaliza para times e multiplayer de forma nativa (relevante em esportes coletivos, embora
  o caso de futebol de 11 jogadores por time normalmente seja tratado no nível de "time" agregado, não
  jogador a jogador); inferência bayesiana completa via grafo de fatores é teoricamente mais rica que
  atualização pontual.
- Contras: computacionalmente mais caro (passagem de mensagens iterativa) que Elo/Glicko; a
  literatura recente de "misspecificação de modelo" (arXiv 2502.10985, 2025) agrupa Elo, Glicko e
  TrueSkill como "qualitativamente similares" em resultados empíricos apesar da complexidade adicional
  — ou seja, o ganho prático de TrueSkill sobre Glicko/Elo não é automaticamente grande o suficiente
  para justificar a complexidade extra em todo domínio; depende do caso de uso (multiplayer/multi-time
  genuíno favorece TrueSkill mais claramente que confrontos estritamente pareados como a maioria dos
  jogos de futebol).

### Relação com outros tópicos

Essa família inteira é uma abordagem **diferente e mais simples** do mesmo problema que Dixon-Coles/
Bayesian hierárquico (§1/§4) resolvem de forma mais rica para futebol: em vez de modelar a distribuição
completa de gols (permitindo derivar qualquer mercado — over/under, handicap, BTTS), Bradley-Terry/
Glicko/TrueSkill modelam diretamente `P(vitória)` (ou uma permutação de resultados), sem produzir uma
distribuição de placar. Isso os torna **mais simples e mais baratos** de manter, mas **estruturalmente
insuficientes** para o caso de uso central do projeto ApostaInfo, que precisa de mercados de gols
granulares (Poisson/NB), não só W/D/L. O Elo usado no projeto (§5, via `home_elo_pre`/`away_elo_pre`) é,
portanto, deliberadamente "só" o membro mais simples desta família, usado como **feature de entrada**
resumindo força relativa — não como o modelo de previsão final, papel que cabe ao Dixon-Coles-NB. Vale
notar que nenhuma variante Glicko/TrueSkill está em uso ou em teste registrado no projeto atualmente;
seriam candidatos razoáveis se o projeto algum dia precisasse de uma feature de "incerteza de rating"
mais rica que o Elo pontual atual — mas qualquer teste desse tipo teria que provar ganho incremental
sob o gate §6 antes de substituir ou complementar o Elo existente.

### Fontes

- Herbrich, R., Minka, T. & Graepel, T. (2006). "TrueSkill™: A Bayesian Skill Rating System." NeurIPS
  2006. https://papers.neurips.cc/paper/3079-trueskilltm-a-bayesian-skill-rating-system.pdf
- Coulom, R. (2008). "A Bayesian Rating System for Players of Time-Varying Strength" (usa e discute
  Bradley-Terry como base). https://inria.hal.science/inria-00323349/document
- "Is Elo Rating Reliable? A Study Under Model Misspecification" (arXiv, 2025) — comparação crítica
  entre Elo, Glicko, TrueSkill e discussão de transitividade/misspecificação do Bradley-Terry.
  https://arxiv.org/html/2502.10985v1
- MetricGate, "TrueSkill Team Rating" (resumo comparativo Elo/Glicko/Bradley-Terry/Thurstone/TrueSkill).
  https://metricgate.com/docs/trueskill-team-rating/

---

## Notas finais de uso

- Este documento é uma **fotografia da literatura e do estado da arte externo** — não descreve o que
  já foi testado e aprovado/reprovado especificamente no projeto ApostaInfo (isso vive em
  `DOCUMENTACAO_CENTRAL.md` §8/§9/§13/§16/§17 e nos arquivos de memória do agente). Antes de propor uma
  hipótese nova baseada em algo lido aqui, sempre cruzar com essas fontes internas — várias ideias
  "óbvias" da literatura genérica (momentum de equipe, hierárquico bayesiano completo, time-decay
  clássico) já foram tentadas e reprovadas no dataset e no gate específicos deste projeto.
- Quando algum tópico aqui parecer promissor para uma feature/mercado novo, o caminho correto continua
  sendo o gate de validação (§6 do doc-mestre): CV temporal, comparação de log-loss/ECE contra a
  produção real, consistência por competição — nunca promoção só por plausibilidade teórica.
