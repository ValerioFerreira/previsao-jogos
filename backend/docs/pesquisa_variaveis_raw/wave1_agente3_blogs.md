# Onda 1 — Agente 3: Blogs técnicos e artigos especializados em football analytics

Data da pesquisa: 2026-07-24

Domínio: conteúdo editorial/explicativo de analistas independentes e blogueiros de football
analytics (não papers acadêmicos formais — isso é Agente 1; não material de vendor — isso é
Agente 2). Fontes cobertas: `pena.lt/y` (penaltyblog, Martin Eastwood), Marc Lamberts (Medium),
`opisthokonta.net`, Jan Van Haaren (curadoria anual "Soccer Analytics Review 2025" — usada como
índice para achar o restante), Analytics FC, StatsBomb/Hudl blog archive, American Soccer
Analysis, Soccerment, David Sumpter (soccermatics), FiveThirtyEight/SPI, McKay Johns (Substack),
thexgfootballclub (Substack), fóruns (r/SoccerBetting, r/algobetting — r/soccernerd não retornou
threads específicas), blogs/portais em português (Futebol de Dados, Trocando Passes — sem posts
técnicos específicos indexados no momento da busca; retornaram só conteúdo institucional
genérico) e espanhol (busca ampla, sem blog técnico individual de peso equivalente a
pena.lt/y ou Analytics FC encontrado — mercado de língua espanhola em football analytics é bem
mais fraco que o inglês).

## Tabela de candidatos

| nome | descrição | fórmula/como é calculada | mercados impactados | ganho esperado | complexidade | fonte de dado (API-Football já traz? senão qual) | disponibilidade | evidência (link + por que confiar) |
|---|---|---|---|---|---|---|---|---|
| **FSAA — Finishing Skill Above Average (shrinkage bayesiano)** | Habilidade de finalização de um jogador estimada por regressão logística hierárquica multinível (efeitos aleatórios cruzados jogador×competição) sobre xG por chute, com "shrinkage" para a média da liga proporcional ao tamanho da amostra e intervalo de credibilidade (HDI) em vez de um número único. Resolve o problema do `Goals − xG` simples, que confunde sorte de amostra pequena com habilidade real (ex.: 1 gol em chance de 0,1 xG parece "elite" com G-xG ingênuo, mas o modelo bayesiano puxa isso de volta pra média até acumular evidência). | `logit(P(gol\|chute)) = xG_logit + efeito_competição + efeito_jogador`, `efeito_jogador ~ Normal(0, σ_liga)` (hierárquico, shrinkage automático); saída = `FSAA` (média posterior) + `HDI 3%/97%` + `P(acima da média)`. Amostra: 500k+ chutes, 5 ligas, 2014/15–2025/26. | Marcador (first_scorer_clf), props de jogador (scorer_model — goleador/finalizações) | Médio-alto *se* adaptável ao nosso dado (ver ressalva) — o ganho não é em log-loss agregado de resultado, é em **qualidade de ranking de jogador** (o momentum de jogador do projeto já passou o gate com AUC 0,68→0,71; isto ataca o mesmo alvo por outro ângulo: habilidade estável vs. forma recente) | Alta — exige xG por chute em nível de evento e um modelo hierárquico bayesiano (MCMC/NUTS), não é um GBM tabular simples. **Ressalva crítica**: nosso dataset não tem xG de seleção (~0% cobertura) e xG de clube só ~10-15% ("muro de dados", já documentado); FSAA como descrito é inviável para nós sem primeiro resolver a cobertura de xG. Um substituto plausível seria aplicar o mesmo *shrinkage bayesiano* sobre `gols − esperado_por_finalizações` (nosso proxy via `shots_prop_model`) em vez de xG por chute — ideia adaptável, não o método literal | API-Football não traz xG por chute (só box-score agregado); precisaria de xG evento-a-evento (Opta/StatsBomb) que não temos, ou adaptar para o proxy de finalizações que já coletamos | Ambos em tese (jogador de seleção e de clube), mas na prática só viável hoje pro proxy de finalizações de clube (maior amostra) | [Shrinkage, Uncertainty, and Son Heung-min](https://pena.lt/y/2025/10/01/a-better-way-to-measure-finishing-skill/) — Martin Eastwood/penaltyblog, autor de referência no espaço (mantém a lib `penaltyblog`, citado recorrentemente na curadoria anual de Jan Van Haaren); metodologia declarada (multilevel Bayesian logistic regression, NUTS, r_hat<1.01) e resultados batem com senso comum de scout (Messi/Son no topo, Calvert-Lewin/Navas no fundo) |
| **Expected Shot Danger (xSD) — modelo de 2 estágios com chutes bloqueados** | Alternativa ao xG que incorpora conceitos de hóquei (Fenwick/Corsi) para não descartar chutes bloqueados. Decompõe em 2 estágios: `P(chute vai a gol)` (pré-shot danger — inclui bloqueados) × `P(gol \| chute no alvo)` (pós-shot danger — qualidade de finalização isolada). Argumento: xG tradicional zera chutes bloqueados mesmo quando saem de posição perigosa, perdendo sinal de pressão ofensiva/qualidade de criação. | `xSD = P(on_target) × P(gol\|on_target)`, cada estágio um classificador (testaram logístico 2-stage vs LightGBM/XGBoost — o logístico simples bateu os GBM em AUC, 0,79-0,80 vs 0,70-0,73, quando treinado em múltiplas ligas). Features: distância/ângulo ao gol, parte do corpo, tipo de jogada, técnica, tipo de assistência, se foi desviado. | Gols (DC-NB), chutes→escanteios (cascata), possivelmente cartões (via chutes bloqueados como proxy de intensidade defensiva) | Baixo-médio — decompor "chegar ao alvo" vs "finalizar" é conceitualmente parecido com o que o projeto já faz na cascata chutes→escanteios→cartões (NB/GP em cascata); o ganho seria separar melhor "criar perigo" de "finalizar bem", mas exige dado de evento (posição XY do chute) que não temos | Alta — precisa de coordenadas XY do chute e classificação de chutes bloqueados por evento; API-Football só dá contagem agregada (`shots.blocked`, `shots.on`, `shots.total` por jogo), sem localização | API-Football traz `shots.blocked` como contagem por time/jogo (não por evento) — dá pra usar como feature agregada (ex.: razão bloqueados/total como proxy de "chutes de dentro da área que foram cortados"), mas não dá pra replicar o modelo de 2 estágios sem dado de evento | Clube prioritariamente (é onde há mais chutes bloqueados registrados na API); seleção teria amostra pequena | [Expected Shot Danger: building an alternative to xG](https://marclamberts.medium.com/expected-shot-danger-building-an-alternative-to-xg-3d1282564feb) — Marc Lamberts, dez/2025, consultor de recrutamento+análise de dados em futebol, autor prolífico e citado na curadoria de Jan Van Haaren; post é transparente sobre limitações (dado só de evento, sem pressão de defensor/goleiro) e mostra AUC caindo quando generaliza pra múltiplas ligas — honestidade metodológica que dá confiança |
| **Comparação empírica de métodos de de-vig (multiplicative vs Shin vs power vs logarithmic vs odds-ratio vs additive vs differential margin weighting)** | Teste em escala (380 jogos, Premier League 2024/25, odds de fechamento Bet365) comparando 7 métodos de remoção de overround via RPS. Achado: **multiplicative** (o mais simples, `p_i = (1/odds_i) / Σ(1/odds_j)`) teve o menor RPS (0,19724), com Shin/logarithmic/odds-ratio essencialmente empatados (diferença de 4ª casa decimal) — ou seja, em mercado líquido (EPL), o método de de-vig quase não importa. | 7 fórmulas documentadas no post (multiplicative, additive, power, Shin, odds-ratio, differential margin weighting, logarithmic) — todas implementadas na lib `penaltyblog`. | Verificador de Bets / "Oportunidades Encontradas" (cálculo de probabilidade justa a partir de odds de casa para achar EV positivo) | **Este NÃO é candidato novo — é validação cruzada direta do que já foi testado no projeto** (§20 doc-mestre: bug real corrigido em `devig_methods.py::shin_devig`, que nunca tinha sido testado de verdade e caía em power). O achado do blog (multiplicative ≈ Shin ≈ logarithmic em mercado líquido) é consistente com a conclusão do projeto de que não há edge robusto de valor (§19/§20) — reforça que a escolha do método de de-vig não é onde está o problema, é a eficiência do mercado em si | Baixa (já implementado) | API-Football já traz odds via `GET /odds` / tabelas `{,club_}odds_bookmaker_latest` (ver §22 doc-mestre) | Ambos | [From Biased Odds to Fair Probabilities](https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/) e [How Accurate Are Soccer Odds?](https://pena.lt/y/2025/07/16/how-accurate-are-soccer-odds/) — mesmo autor, mesma lib usada no primeiro trabalho de devig do projeto; segundo post usa 250M linhas de odds reais e conclui que bookmakers grandes (Pinnacle, bet365) estão bem calibrados (curva de calibração colada na diagonal) e que overround não prediz RPS — achado direto e independente que corrobora a conclusão "SEM edge robusto" do §20 do projeto |
| **Overround por liga/temporada como sinal de incerteza/eficiência de mercado** | Overround médio (margem do bookmaker) varia sistematicamente por competição (4,1%-5,1% em ligas top-5; 6-7,6% em ligas secundárias/menores) e cresceu ao longo de 5 temporadas em quase todas as competições. RPS (acurácia) segue padrão parecido mas mais fraco — ligas obscuras (Seicheles, Mongólia) têm overround alto mas RPS nem sempre pior, sugerindo que overround alto é precificação de incerteza, não sinal de mercado "batível". | Overround = `Σ(1/odds_i) − 1`; RPS = escala de erro proprio para outcomes ordenados (H/D/A). Tabelas completas por liga/temporada/bookmaker no post. | Indiretamente: qualquer mercado onde o modelo é comparado/blendado com odds de mercado (Verificador de Bets, calibração de mercados de apostas) | Uso possível como **feature de confiança/peso**: overround da liga como proxy de quão "líquido"/coberto é aquele campeonato pode servir pra ponderar o quanto confiar em odds de casas menores nas ligas onde a coleta de clube ainda é mais rala (83 competições, cobertura desigual) | Baixa — é um cálculo direto sobre odds já coletadas, sem modelo novo | API-Football já traz odds por casa (mesma tabela do item acima) | Ambos, mas mais relevante pra clube (maior variação de liga/qualidade de mercado) | Mesmo post acima ([How Accurate Are Soccer Odds?](https://pena.lt/y/2025/07/16/how-accurate-are-soccer-odds/)) — dataset de 250M linhas/1,25M partidas é a maior amostra empírica encontrada nesta busca sobre o assunto, dá confiança estatística ao padrão descrito |
| **Vantagem de mandante variável no tempo/por nível competitivo (não é constante)** | Múltiplas fontes (WEF/The Conversation sobre estádios vazios na pandemia, blog Engora, artigo acadêmico "Time-Varying Home Field Advantage") convergem no achado de que a vantagem de mandante (a) caiu ~50% em jogos sem torcida, (b) vem numa tendência de queda estrutural desde a 2ª Guerra Mundial (não é um evento único da pandemia), e (c) varia por divisão/nível competitivo dentro da mesma liga (maior em divisões de elite que em divisões inferiores). | Não há fórmula única — é um conjunto de achados empíricos que sugerem que o parâmetro de vantagem de mandante no DC-NB (hoje provavelmente um efeito fixo ou por-competição estático) poderia ser modelado como **decaindo/variando com uma tendência temporal** em vez de constante por período de treino. | Resultado 1X2, handicap asiático, dupla chance — qualquer mercado que dependa do parâmetro de home advantage do DC-NB | Incerto — o projeto já tem `home_elo_pre`/`away_elo_pre` e K por competição; se o home advantage já é recalibrado a cada retreino (retreinos frequentes: 2026-07-18, 2026-07-22), o efeito de "tendência estrutural lenta" pode já estar implicitamente capturado. Only vale a pena testar se o retreino for espaçado o suficiente pra a tendência se mover entre janelas | Média — precisaria de um termo de tendência temporal explícito (ex.: home_adv como função linear/spline do tempo, não escalar único) no lugar do fixo/por-competição atual | Já temos `days_rest`/calendário e `home_elo_pre`; a informação-base (data do jogo, presença de público, se é jogo neutro) já está disponível na API-Football | Ambos | [As football returns in empty stadiums, four graphs show how home advantage disappears](https://theconversation.com/as-football-returns-in-empty-stadiums-four-graphs-show-how-home-advantage-disappears-138685) (The Conversation, dados agregados por pesquisadores acadêmicos, republicado várias vezes — achado replicado independentemente por vários veículos); [Vanishing home field advantage in English football](https://blog.engora.com/2025/07/vanishing-home-field-advantage-in.html) (Engora Data Blog, mais recente, foco isolado na tendência de longo prazo) |
| **xThreat (xT) / On-Ball Value (OBV) — modelos de valorização de posse baseados em Markov/zona** | Framework clássico (Karun Singh 2018, origem StatsBomb OBV) que atribui valor a cada zona do campo via cadeia de Markov e credita jogadores por mover a bola pra zonas de maior probabilidade de gol (passes/carries). OBV é a versão comercial mais recente (Hudl/StatsBomb) que decompõe em componente ofensivo/defensivo. | xT: value surface por zona resolvida via cadeia de Markov absorvente (probabilidade de finalizar bem-sucedida a partir de cada zona); OBV: `Δ P(gol_a_favor) − Δ P(gol_contra)` antes/depois de cada evento, com modelo próprio de "próxima possessão". | Nenhum mercado do projeto hoje — é métrica de valorização de jogador/ação, não de previsão de resultado agregado | **Não recomendado para este projeto** — é o candidato mais claramente incompatível com nossa fonte de dado | Alta | **API-Football não traz.** Exige dado de evento com coordenadas XY de cada ação (passe, drible, carry) — isto é dado de "event data" tipo Opta/StatsBomb/Wyscout, uma categoria de dado inteiramente diferente do box-score agregado que a API-Football fornece. Confirma o "muro de dados" já documentado no projeto para xG — o mesmo muro bloqueia xT/OBV, e de forma ainda mais severa (xG precisa só da localização do chute; xT/OBV precisam da localização de *toda* ação) | Nenhuma, dado o gap de dado | [Introducing Expected Threat (xT)](https://karun.in/blog/expected-threat.html) — post original de Karun Singh, referência canônica citada por praticamente toda a literatura subsequente; [On-Ball Value (OBV) Model Explained](https://www.hudl.com/blog/statsbomb-on-ball-value) — Hudl/StatsBomb, descrição oficial do sucessor comercial |

## Cruzamento com reprovados

- **De-vig / método de remoção de overround** (linha 3 da tabela): **overlap direto** com trabalho
  já feito no projeto. O `DOCUMENTACAO_CENTRAL.md` §20 registra que o bug real em
  `devig_methods.py::shin_devig` foi corrigido durante a bateria W1-W4 (nunca tinha sido testado
  de verdade, caía em `power`). O achado do blog de Martin Eastwood — que `multiplicative` bate
  ou empata com métodos mais sofisticados (Shin, logarithmic, odds-ratio) em mercado líquido — não
  é uma proposta nova, é uma **segunda fonte independente confirmando** que a escolha do método de
  de-vig não é o gargalo. Não reproponho testar de-vig de novo; cito aqui só como evidência
  corroborante do encerramento do tema em §20.
- **Calibração de mercado / ausência de edge de valor** (linhas 3 e 4): o achado de Eastwood
  (bookmakers grandes bem calibrados, overround não prediz RPS, ligas obscuras "caras mas não
  batíveis") é consistente com a conclusão do §19/§20 do projeto (H3: SEM edge robusto em nenhum
  mercado/liga, confirmado com ~60x a amostra da bateria W1-W4). Não é um candidato de feature —
  é confirmação externa de um resultado negativo já fechado no projeto.
- **Momentum de jogador / habilidade de finalização** (linha 1, FSAA): o projeto já testou e
  **aprovou** momentum de jogador (`bateria-momentum-jogador.md`: AUC goleador 0,68→0,71). FSAA
  ataca o mesmo alvo (props de jogador) por um ângulo diferente e complementar — não é forma
  recente, é habilidade estável estimada com shrinkage bayesiano contra amostra pequena. Não é
  redundante com o que já passou, mas também não é imediatamente aplicável porque depende de xG
  por chute em nível de evento, que é exatamente o dado que falta ("muro de dados" — xG reprovado
  3x como feature de match-level, cobertura de clube ~10-15%, seleção ~0%). Um teste real exigiria
  primeiro decidir se vale adaptar a metodologia para o proxy de finalizações (`shots_prop_model`)
  em vez do xG por chute literal do post.
- **PPDA / pressão tática**: o projeto já tem `style_ppda` como proxy tático ortogonalizado contra
  `elo_diff` (ver CLAUDE.md, features de estilo). Os posts sobre PPDA encontrados nesta busca são
  puramente explicativos (o que é, como se calcula) e não trazem refinamento metodológico novo
  além do que provavelmente já foi considerado ao construir a feature — não abri linha na tabela
  por não ter achado ângulo incremental.
- **xThreat / OBV** (linha 6): não colide com nenhuma hipótese testada e reprovada — é a primeira
  vez que aparece no radar do projeto nesta pesquisa — mas colide com uma **limitação estrutural
  já documentada** (dependência de API-Football, sem tracking real, "muro de dados" de xG). Incluí
  na tabela justamente para deixar registrado *por que* não vale a pena perseguir, evitando que um
  agente futuro reabra a ideia sem saber do gap de dado.
- **Vantagem de mandante variável no tempo** (linha 5): não colide com nada testado — o projeto
  testou calendário/viagem/altitude (mistos/nulos, ver CLAUDE.md) mas não especificamente uma
  *tendência temporal* no parâmetro de home advantage do DC-NB em si. Ângulo genuinamente novo,
  mas com ressalva de que pode já estar implicitamente absorvido pelos retreinos frequentes.

## Fontes consultadas

**Meta-fonte principal (usada como índice para o resto):**
- [Jan Van Haaren — Soccer Analytics 2025 Review](https://janvanhaaren.be/posts/soccer-analytics-review-2025/) — curadoria anual (desde 2020) de tudo que se publicou em football analytics no ano: 82 papers, 51 posts de blog, 32 matérias de imprensa, 10 podcasts, 10 webinars, 11 eventos, 10 repositórios de código. Usada para identificar os autores/blogs de maior peso relativo (Martin Eastwood/penaltyblog, Marc Lamberts, Analytics FC, American Soccer Analysis, David Sumpter, StatsBomb/Hudl) sem depender só de busca por palavra-chave.

**Posts lidos na íntegra (scrape completo):**
- [Shrinkage, Uncertainty, and Son Heung-min: Using Bayesian Methods to Identify Finishing Ability](https://pena.lt/y/2025/10/01/a-better-way-to-measure-finishing-skill/) — Martin Eastwood, penaltyblog, 1 out 2025
- [From Biased Odds to Fair Probabilities: Removing the Bookmaker's Overround](https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/) — Martin Eastwood, penaltyblog, 14 set 2025
- [How Accurate Are Soccer Odds? A Data Dive into 250 Million Betting Lines](https://pena.lt/y/2025/07/16/how-accurate-are-soccer-odds/) — Martin Eastwood, penaltyblog, 16 jul 2025
- [Expected Shot Danger: building an alternative to xG](https://marclamberts.medium.com/expected-shot-danger-building-an-alternative-to-xg-3d1282564feb) — Marc Lamberts, dez 2025

**Buscas realizadas (WebSearch, ~17 queries em PT/EN/ES):**
xThreat/expected threat explicado; métricas caseiras xG em português (Futebol de Dados); David
Sumpter/soccermatics; FiveThirtyEight SPI methodology; Ben Torvaney/xG dispersão; closing line
value/eficiência de mercado; Dixon-Coles explicado (blog); PPDA/pressão; corner kicks
negative binomial (blog+paper); post-shot xG/PSxG/goleiro; Trocando Passes (sem achados
específicos); r/soccernerd value betting; opisthokonta.net/Elo; StatsBomb OBV; home advantage
declínio/estádios vazios; McKay Johns Substack xG; Soccerment blog xG/shot quality; devig
Shin/power/logarithmic comparação; análise fútbol datos español; Analytics FC blog; expected
points (xP) explicado; vantagem de mandante declínio PT; apuestas fútbol calibración ES; cartões
amarelos/árbitro viés PT.

**Outras fontes relevantes identificadas mas não aprofundadas (por escopo/tempo ou por já
estarem cobertas por outro agente):**
- `opisthokonta.net` (Elo ratings, K-factor, home advantage) — muito conteúdo, mas pi-ratings/Elo
  já é território extensamente testado no projeto (produção já usa Elo com K por competição).
- Analytics FC blog (`analyticsfc.co.uk`) — "Are Some Players Consistently Good Finishers?" (fev
  2025) parece cobrir terreno adjacente ao FSAA; não lido na íntegra por redundância.
- American Soccer Analysis (`americansocceranalysis.com`) — métrica "Goals Added" (g+) e
  subcategorias — modelo de valorização de ação tipo VAEP/OBV, mesma limitação de dado de evento.
- `dtai.cs.kuleuven.be/sports/blog` (Jesse Davis/Pieter Robberechts/Jan Van Haaren) — "Expected
  Goals and the Monte Carlo Trap" e "How Do We Know a Metric Is Good? A Case Study on VAEP" — mais
  sobre metodologia de validação de métrica do que sobre uma métrica candidata específica;
  relevante para quem for revisar o próprio gate §6, mas fora do escopo de "candidato de
  variável" desta tabela.
- Blogs em português (Trocando Passes, Futebol de Dados Br) e espanhóis não retornaram posts
  técnicos individuais com validação própria comparável ao nível de pena.lt/y ou Analytics FC —
  o conteúdo em PT/ES encontrado nas buscas foi majoritariamente institucional/genérico (o que é
  xG, o que é PPDA) sem metodologia própria testada, portanto não qualificou como candidato
  substantivo para a tabela.
