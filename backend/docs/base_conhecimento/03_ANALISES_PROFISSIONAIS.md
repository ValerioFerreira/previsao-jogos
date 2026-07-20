# Como analistas profissionais de futebol escrevem análises — guia de referência

> Documento de pesquisa para orientar agentes Claude que geram análises de partidas/times na
> plataforma ApostaInfo. Baseado na leitura direta de artigos reais (não de memória) de 9 sites
> de referência em análise de futebol: StatsBomb/Hudl, Opta Analyst (The Analyst), Between the
> Posts, Total Football Analysis, Spielverlagerung, StatsBomb Open Data (comunidade), American
> Soccer Analysis e Hudl Blog. Síntese e paráfrase apenas — citações diretas são sempre curtas
> (<15 palavras) e atribuídas.

## Sumário

1. [StatsBomb / Hudl Statsbomb](#1-statsbomb--hudl-statsbomb)
2. [Opta Analyst / The Analyst](#2-opta-analyst--the-analyst)
3. [Between the Posts](#3-between-the-posts)
4. [Total Football Analysis](#4-total-football-analysis)
5. [Spielverlagerung](#5-spielverlagerung)
6. [StatsBomb Open Data (comunidade / análises com statsbombpy e StatsBombR)](#6-statsbomb-open-data-comunidade--análises-com-statsbombpy-e-statsbombr)
7. [American Soccer Analysis](#7-american-soccer-analysis)
8. [Hudl Blog (performance analysis)](#8-hudl-blog-performance-analysis)
9. [Padrões comuns entre os analistas profissionais (síntese prática)](#9-padrões-comuns-entre-os-analistas-profissionais-síntese-prática)
10. [Fontes](#10-fontes)

---

## 1. StatsBomb / Hudl Statsbomb

**Nota estrutural importante:** desde a aquisição da StatsBomb pela Hudl, o blog histórico da
StatsBomb (`statsbomb.com/articles/...`) redireciona para `hudl.com/blog/...`. O conteúdo
editorial de dados (metodologia de modelos, releases de métricas, deep dives analíticos)
continua saindo com a marca "Hudl Statsbomb", mas hospedado no domínio da Hudl. Isso é relevante
para quem for citar a fonte: o nome comercial mudou, o tipo de conteúdo não.

**Tipo de análise:** primariamente **metodológica/estatística** — como um modelo funciona, o que
ele mede e por quê — não é cobertura de partida (não existe "análise da rodada" no sentido
jornalístico). Também publica scouting orientado a dados (arquétipos de jogador, "quem se parece
com quem") e conteúdo de recrutamento.

**Métricas/conceitos mais citados:**
- **xG (Expected Goals)** e suas variantes: **post-shot xG**, **Shot Impact Height**, xG com
  posição do goleiro/zagueiros no freeze-frame.
- **OBV (On-Ball Value)** — valor de cada ação (passe, drible, desarme) em termos de probabilidade
  de gol a favor/contra.
- **xPass**, **Pressures**, **Pass Footedness**, **Defensive Responsibility (DefR)**.
- Conceitos de modelagem explícitos: features contínuas vs. discretas, **restrições monotônicas**
  (monotonic constraints) em modelos de gradient boosting, contrafactuais (o que aconteceria se o
  goleiro estivesse em outra posição).

**Estrutura do texto:**
1. Introdução conceitual (por que essa métrica/ideia importa, contexto histórico da métrica).
2. Explicação do "antes" (limitação do modelo/abordagem anterior).
3. Detalhamento técnico da mudança/modelo, com gráficos e animações ilustrando o efeito
   (ex.: GIF mostrando como o xG muda suavemente conforme o goleiro se desloca).
4. Aplicações práticas em dois blocos recorrentes: **análise de adversário** (onde o time é
   perigoso/vulnerável no campo) e **recrutamento** (perfis de risco/retorno de jogadores).
5. Fechamento comercial (call-to-action para contratar o produto) — traço distintivo desse site
   frente aos demais, que são mais editoriais.

**Tom/linguagem:** técnico, primeira pessoa do plural ("we"), assume que o leitor já conhece xG
básico. Muito uso de imagens/GIFs comparando "antes vs. depois" do modelo. Impessoal quanto a
jogos específicos — o foco é sempre no modelo, ilustrado com exemplos de jogos reais.

**Trechos de exemplo (paráfrase/citação curta):**
- Sobre a motivação do upgrade de xG: descreve o objetivo como haver "lot of untapped potential
  left in this simple foundational concept" (Hudl Statsbomb Blog).
- Sobre o OBV: o modelo "assigns a value to each action... in line with... probability of their
  team scoring and conceding" (Hudl Statsbomb Blog).

---

## 2. Opta Analyst / The Analyst

**Tipo de análise:** **pré-jogo com previsão probabilística** — é o site mais próximo, em
propósito, do que a ApostaInfo quer fazer. Cada artigo é um "match preview" ancorado em uma
previsão de simulação (o "Opta supercomputer"), sempre publicado nos dias antes do jogo.

**Métricas/conceitos mais citados:**
- **Probabilidades de simulação** (% vitória casa / empate / vitória visitante, incluindo prórroga
  e pênaltis quando aplicável).
- **xG acumulado do torneio**, **gráficos de "xG race"** (corrida de xG minuto a minuto de jogos
  históricos entre os mesmos times).
- Estatísticas de forma recente (últimos resultados, sequências), recordes individuais/históricos
  (quem já fez quantos gols em Copas, comparação com lendas do passado).
- Escalações prováveis (predicted lineups) como imagem/gráfico.

**Estrutura do texto (muito padronizada, quase um template):**
1. **Título:** `[Time A] vs [Time B] Prediction: [Competição] Match Preview`.
2. **Bloco "Key Insights"** logo no topo — 2-4 bullets em **negrito**, cada um uma estatística de
   impacto (ex.: "England advance in 52.3% of simulations").
3. **Corpo narrativo:** contexto histórico do confronto (rivalidades, jogos memoráveis do
   passado), trajetória de cada time no torneio até ali, destaque para 2-3 jogadores-chave com
   estatísticas específicas (recordes, médias por 90 min).
4. **Seção "Head-to-Head":** retrospecto histórico direto entre os times.
5. **Seção "Prediction":** volta às probabilidades da simulação, agora com mais detalhe
   (frequência em 90 minutos vs. incluindo prorrogação/pênaltis), sempre com gráfico do
   "Opta Supercomputer".
6. **Seção "Squads" / "Predicted Lineups":** elenco convocado e escalação provável em imagem.
7. Fechamento com CTA de newsletter/redes sociais.

**Tom/linguagem:** jornalístico-narrativo, terceira pessoa, storytelling forte (abre com contexto
histórico/dramático antes de qualquer número). Mistura estatística densa com uma narrativa quase
de "prévia esportiva" tradicional — muito mais acessível que StatsBomb, mas sem perder rigor
numérico. Sempre credita "Opta supercomputer" como fonte da previsão, nunca expõe a metodologia
do modelo em si dentro do artigo.

**Trechos de exemplo:**
- "England advance in 52.3% of simulations (including extra-time and penalties)" (The Analyst).
- Uso típico de recorde histórico como gancho: "the first time in World Cup history that two
  players from the same country have hit 6+ goals" (The Analyst).

---

## 3. Between the Posts

**Tipo de análise:** **tática pura, pós-jogo** (match report tático) — provavelmente o site mais
próximo do "estilo Spielverlagerung" em língua inglesa: análise fina de estrutura, rotações e
espaços, não de estatística agregada.

**Métricas/conceitos mais citados:**
- Vocabulário tático "continental": **halfspace** (meio-espaço), **third-man run**, **rest
  defense**, **counterpress**, **overload**, **underlap**, formação nomeada com precisão
  (ex.: "4-4-2 medium block").
- Raramente cita xG ou métricas numéricas isoladas — quando aparece, é qualitativo ("created a
  great deal of chances") mais que number-first.
- Faz referência a **decisões de escalação e substituições do técnico** como parte central da
  análise tática (não é só "o que aconteceu em campo", é "por que o técnico decidiu isso").

**Estrutura do texto:**
1. **Título:** `[Time A] – [Time B]: [Frase de efeito] (placar)`.
2. **Lead em negrito:** 2-3 frases resumindo a "história tática" do jogo (não o placar em si).
3. Crédito do autor ("Tactical analysis and match report by [Nome]").
4. Contexto de forma/narrativa recente dos dois times antes do jogo.
5. **Corpo dividido em subtítulos temáticos** (não cronológicos) — cada subtítulo cobre um padrão
   tático específico que se repetiu no jogo (ex.: "The switch and evasion", "Why Ruiz over
   Pedri?"), com **diagramas táticos (imagens com anotações de movimento)** e a legenda explicando
   o minuto exato e a sequência de passes.
6. Uma seção final **"Takeaways"** — conclusão prospectiva (o que isso significa para o próximo
   jogo do vencedor).

**Tom/linguagem:** altamente técnico-tático, terceira pessoa, frases longas e descritivas do
movimento de bola/jogadores célula a célula. Cada imagem tem legenda funcionando como um
"replay narrado". Site paywall parcial (parte do conteúdo é gratuito, parte por assinatura).

**Trechos de exemplo:**
- Resumo-tese de uma partida: "the story of the game was the effectiveness of the Spanish
  buildup" (Between the Posts).
- Uso de pergunta como subtítulo analítico: "Why Ruiz over Pedri?" (Between the Posts).

---

## 4. Total Football Analysis

**Tipo de análise:** híbrida — **tática de partida** com forte camada de **dados/xG** e, na
versão atual do site, também **odds e previsões de apostas** (o site se reposicionou como
"tactical journalism... with live odds, model-backed predictions and an honest betting layer").

**Métricas/conceitos mais citados:**
- **xG e post-shot xG** por jogo (comparando xG total vs. gols reais como medida de "sorte"/
  eficiência de finalização).
- **PPDA** (passes per defensive action, métrica clássica de intensidade de pressão) e
  "high recoveries".
- **xG por lance de bola parada**.
- Vocabulário tático: **high press man-to-man**, **rest defense**, **transições**, **overloads
  largos e centrais**.

**Estrutura do texto:**
1. Título: `[Time A] Vs [Time B] [placar] – [Competição]: [subtítulo temático] – Tactical
   Analysis`.
2. Lead contextual (o que estava em jogo, forma recente dos dois times, rivalidade se houver).
3. **Seção "Lineups & Formations"** — escalação titular, formação, todas as substituições com
   minuto exato.
4. **Imagem com os XIs** lado a lado.
5. **2-4 seções temáticas com H2** (ex.: "PSG High Press", "PSG's Ruthless Finishing", "Chelsea
   Transitions") — cada uma mistura **prosa tática + screenshot de replay + estatística de
   apoio** (xG do lance, PPDA).
6. **Shot map** como imagem, com xG total por time no rodapé.
7. **Conclusão** com xG final comparado, e uma "ponte" para o próximo jogo do time (contexto de
   calendário, análise prospectiva).

**Tom/linguagem:** primeira pessoa do analista aparece ocasionalmente ("To me, it was more the
mistakes..."), mais opinativo que StatsBomb/Between the Posts, mas ainda ancorado em evidência de
vídeo e dado. Menos denso que Spielverlagerung, mais analítico que Opta Analyst.

**Trechos de exemplo:**
- Contraste dado vs. impressão visual: "PSG created only 0.90 xG but scored five times" (Total
  Football Analysis).
- Opinião do autor como gancho: "you could argue that Chelsea may have been the better side"
  (Total Football Analysis).

---

## 5. Spielverlagerung

**Tipo de análise:** **teoria tática pura** (tactical theory) — o mais acadêmico/conceitual dos
nove sites. Não é cobertura de partida; é um ensaio sobre um conceito tático (ex.: compactação,
diagonalidade), usando múltiplos jogos como evidência ao longo de anos, não um único evento.

**Métricas/conceitos mais citados:**
- Nenhuma métrica numérica de dados públicos (não cita xG, PPDA etc. como número). O vocabulário é
  quase todo **geométrico/espacial**: compactação horizontal/vertical/diagonal, "conexões
  defensivas", "acesso à bola" (defensive access), "controle espacial", "needle players"
  (jogadores de drible que rompem blocos compactos).
- Cita **estudos de terceiros com números** quando reforça o argumento (ex.: taxa de conversão de
  cabeceios vs. chutes normais, citando um estudo de Michael Caley sobre cruzamentos).
- Usa **analogias fora do futebol** (xadrez, uma partida Karpov–Kasparov) para explicar controle
  de espaço central.

**Estrutura do texto:**
1. Título: `Tactical Theory: [Conceito]`.
2. **Citação de abertura** de uma referência tática (ex.: Johan Cruyff) que ancora o tema.
3. Seção de **definição rigorosa do conceito** — discute definições concorrentes antes de adotar
   uma ("qual é o nível ótimo de compactação?").
4. **Múltiplas subseções H3**, cada uma cobrindo uma "vantagem" ou "aplicação" distinta do
   conceito (defensiva, ofensiva, no pressing, na contrapressão), cada uma ilustrada com **1-2
   diagramas esquemáticos desenhados à mão** (não screenshots de replay — são esquemas
   abstratos com setas e zonas coloridas) tirados de jogos reais específicos como exemplo.
5. Seção final frequentemente contrastando estilos nacionais (ex.: futebol inglês vs. europeu
   continental) como estudo de caso.
6. Comentários de leitores extensos e tecnicamente engajados — sinal de audiência de nicho
   (treinadores, analistas amadores).

**Tom/linguagem:** ensaístico, primeira pessoa singular do autor ("I will be looking to explore"),
denso, pressupõe vocabulário tático avançado do leitor. Comentários da própria comunidade
criticam quando o texto fica **prolixo demais** — sinal de que mesmo esse público quer objetividade.

**Trechos de exemplo:**
- Definição do problema central do artigo: "what is the optimal level of compaction?"
  (Spielverlagerung).
- Citação de abertura usada como âncora conceitual: "Defending is a matter of – 'How much space
  should I defend?'" — Johan Cruyff, citado em Spielverlagerung.

---

## 6. StatsBomb Open Data (comunidade / análises com statsbombpy e StatsBombR)

**Nota:** "StatsBomb Open Data" não é um site único, é um **dataset público** (via
`github.com/statsbomb/open-data`, consumido pelos pacotes `statsbombpy` em Python e `StatsBombR`
em R). A "análise profissional" aqui vem de uma comunidade de analistas independentes/aspirantes
que publicam tutoriais e estudos de caso em blogs pessoais (ex.: *The Last Man Analytics*,
*PITCH IQ*) usando esse dataset.

**Tipo de análise:** **tutorial técnico + estudo de caso replicável** — o objetivo declarado é
ensinar a replicar uma visualização/análise específica, usando um jogo real como exemplo (não
uma cobertura editorial do jogo em si).

**Métricas/conceitos mais citados:**
- **xG por chute** (`shot.statsbomb_xg`) como a métrica de entrada mais comum para o primeiro
  tutorial de qualquer analista novo — o **shot map com xG** é quase um "hello world" da análise
  de dados de futebol.
- Localização (x,y) de eventos, "freeze frames" (StatsBomb 360), tipos de evento (passe, drible,
  desarme).
- Conceito de "player receipt locations" (onde um jogador específico recebe a bola) como segundo
  tutorial típico.

**Estrutura do texto:**
1. Motivação pessoal do autor (ex.: "fui a um workshop da StatsBomb e me inspirei a...").
2. Elogio à disponibilidade dos dados gratuitos como reduzindo barreira de entrada à área.
3. **Tutorial passo a passo com código** (blocos de R ou Python), cada passo com uma imagem do
   resultado incremental (pitch em branco → pontos brutos → pontos coloridos por time → destaque
   de gols → tamanho do ponto proporcional ao xG → anotações finais com texto).
4. Comentário interpretativo curto após cada gráfico incremental (ex.: "Oops, looks like all the
   shots happened at the same end").
5. Fechamento convidando o leitor a adaptar o código para outro `match_id`.

**Tom/linguagem:** primeira pessoa, tom de tutorial/professor, deliberadamente didático e
acessível — assume zero conhecimento prévio de R/Python. Foco é ensinar o **processo**, a
"história tática" do jogo específico usado como exemplo é secundária e tratada quase como
efeito colateral do tutorial.

**Trechos de exemplo:**
- Sobre a barreira de entrada na área: "getting data to play around with... is why Statsbomb's
  commitment to offering... free is so amazing" (The Last Man Analytics).
- Comentário de leitura de gráfico incremental: "Oops, looks like all the shots happened at the
  same end, regardless of team" (The Last Man Analytics).

---

## 7. American Soccer Analysis

**Tipo de análise:** **estatística com foco de comunidade/mercado americano** (MLS, USL, NWSL,
seleções dos EUA) — mistura (a) artigos explicativos de metodologia própria de métricas e
(b) reportagem/investigação sobre o *estado da análise de dados dentro do próprio esporte*
(quem faz o quê em cada clube).

**Métricas/conceitos mais citados:**
- **g+ (Goals Added)** — métrica própria da ASA, equivalente conceitual ao OBV da StatsBomb:
  valoriza toda ação em termos de gols, dividindo o valor entre passador e recebedor.
- **xG, xA**, com explicação recorrente de por que a métrica **não recompensa a finalização em
  si** (para não supervalorizar "sorte" de conversão).
- Seis categorias de ação usadas para agregar g+: **Shooting, Receiving, Passing, Dribbling,
  Interrupting, Fouling**.

**Estrutura do texto (dois formatos distintos observados):**

*Formato explicativo de métrica* ("What are Goals Added"):
1. Definição em uma frase, em caixa alta no topo como "manchete" (destaque visual do site).
2. Explicação com **exemplo numérico passo a passo** (ex.: "1.5% chance de gol antes, 6% depois,
   logo o passe vale +0.050 goals added").
3. Explicação da metodologia de machine learning por trás (o que o modelo "aprende" a partir de
   possessões similares).
4. Lista de leituras adicionais linkando a artigos mais profundos da própria série (deep dive
   methodology, roundtable da equipe).

*Formato investigativo* ("The State of MLS Analytics"):
1. Gancho a partir de uma postagem viral do autor nas redes sociais.
2. Definição explícita e cuidadosa do que conta como "analytics" antes de classificar clubes
   (separa analytics de ciência do esporte e de business analytics).
3. **Sistema de "tiers"/camadas** classificando cada clube por nível de investimento em dados,
   com fontes citadas (perfis, entrevistas, podcasts) para cada afirmação.

**Tom/linguagem:** primeira pessoa, informal, bem-humorado ("Soccer nerds with spreadsheets and
ggplot2" é o próprio slogan do site), mas rigoroso nas fontes/atribuições quando o assunto é
investigativo. Menos visual que os sites táticos (poucos diagramas de campo nos artigos
metodológicos, mais texto corrido com exemplos numéricos).

**Trechos de exemplo:**
- Definição-manchete: "measures a player's total on-ball contribution in attack and defense"
  (American Soccer Analysis, sobre g+).
- Autodescrição do site: "Soccer nerds with spreadsheets and ggplot2" (American Soccer Analysis).

---

## 8. Hudl Blog (performance analysis)

**Tipo de análise:** **institucional/educacional sobre o processo de análise**, não análise de
uma partida específica — é conteúdo de produto (Hudl vende as ferramentas) explicando **como**
clubes profissionais fazem análise de desempenho no dia a dia.

**Métricas/conceitos mais citados:**
- As **4 áreas clássicas de performance analysis**: **técnica, tática, física, psicológica**.
- Fluxo de trabalho recorrente: **preparação de jogo (game prep)** → **ajustes em tempo real
  (live coding/replay)** → **análise pós-jogo** → **desenvolvimento de longo prazo do atleta**.
- GPS/wearables para carga física, telestração de vídeo para feedback tático/psicológico.

**Estrutura do texto:**
1. Pergunta retórica no início ("What do we mean when we talk about performance analysis?").
2. Definição do conceito geral, citando explicitamente a origem acadêmica (sports performance
   analysis como campo de estudo).
3. **Bloco de 4 subsções** (uma por área: técnica/tática/física/psicológica), cada uma com
   1 parágrafo de definição + link para uma ferramenta comercial correspondente.
4. **Bloco de aplicações práticas** (preparação, tempo real, pós-jogo, desenvolvimento),
   cada uma citando **um case real de clube** (ex.: Palmeiras fazendo live coding no intervalo,
   CD Leganés integrando wearables da base ao profissional).
5. Fechamento comercial com CTA de contato/demo.

**Tom/linguagem:** corporativo-educacional, terceira pessoa, estruturado como conteúdo de
"thought leadership" de fornecedor de tecnologia — muito mais sobre *processo organizacional* do
que sobre *conteúdo tático de um jogo*. Section headers funcionam quase como um índice de curso.

**Trechos de exemplo:**
- Definição-guarda-chuva do campo: performance analysis "consists of making systematic
  observations to provide... objective information" (Hudl Blog).
- Ênfase no valor prático da velocidade de entrega: análise "distills the complexities of sport
  into quick actionable insights" (Hudl Blog).

---

## 9. Padrões comuns entre os analistas profissionais (síntese prática)

Com base na leitura cruzada dos 9 sites, uma boa análise de partida/time — pré-jogo ou pós-jogo —
tende a conter os seguintes elementos, independentemente do estilo de casa:

### Estrutura recomendada

1. **Um "lead" com tese, não com o placar.** Nenhum site abre com "o jogo terminou X a Y".
   Abrem com a *ideia central* do jogo/preview em 1-3 frases (ex.: "a história do jogo foi a
   efetividade da construção espanhola"; "quase nada separa esses dois times"). A tese vem
   primeiro, os detalhes a sustentam depois.
2. **Números de impacto isolados e destacados no topo**, não enterrados no meio do texto — Opta
   Analyst usa bullets em negrito ("Key Insights"); StatsBomb/Hudl e ASA usam definições/números
   em bloco de destaque. Regra prática: 2-4 estatísticas-âncora logo nos primeiros parágrafos.
3. **Contexto antes do dado.** Forma recente, histórico de confrontos diretos, o que está em
   jogo (classificação, rivalidade, sequência de resultados) sempre aparece antes ou entrelaçado
   com os números — nenhum site profissional despeja estatística sem narrativa.
4. **Segmentação temática do corpo, não cronológica.** Os textos táticos (Between the Posts,
   Total Football Analysis, Spielverlagerung) dividem a análise em 2-5 blocos temáticos com
   subtítulo próprio (um padrão tático, uma decisão de escalação, uma fase do jogo) em vez de
   narrar o jogo minuto a minuto.
5. **Estatística como evidência de um argumento, não como lista.** xG, PPDA, posse, etc.
   aparecem para sustentar uma afirmação específica ("apesar da posse de 58%, não criaram muito"),
   nunca como tabela solta sem interpretação.
6. **Cabeça a cabeça / retrospecto histórico** como seção própria quando relevante (Opta Analyst
   sempre inclui; times/coberturas táticas incluem quando há uma rivalidade real).
7. **Probabilidade explícita quando o objetivo é prever** (Opta Analyst, Total Football
   Analysis): % de vitória/empate/derrota, sempre com a ressalva de contexto (90 minutos vs.
   incluindo prorrogação/pênaltis) e a fonte do modelo citada.
8. **Fechamento prospectivo.** Quase todos terminam olhando para frente — o que este resultado/
   preview significa para o próximo jogo, para a fase seguinte da competição, ou para a
   classificação — não um resumo do que já foi dito.
9. **Visual como parte do argumento, não decoração.** Shot maps, diagramas táticos com setas,
   gráficos de xG race e escalações em imagem aparecem exatamente no ponto do texto em que a
   frase teria dificuldade em transmitir a mesma informação sozinha.
10. **Vocabulário técnico correto, mas nunca opaco.** Mesmo o site mais denso (Spielverlagerung)
    define o conceito-chave antes de usá-lo repetidamente. Termos como xG, PPDA, halfspace,
    overload são usados com naturalidade, mas o texto sempre ancora o termo a um exemplo concreto
    na primeira aparição.

### Tom e registro (por tipo de conteúdo)

| Tipo de conteúdo | Pessoa gramatical | Densidade técnica | Melhor referência |
|---|---|---|---|
| Preview pré-jogo com previsão | 3ª pessoa, narrativo | Média (número + storytelling) | Opta Analyst |
| Análise tática pós-jogo | 3ª pessoa, descritivo-técnico | Alta (jargão tático denso) | Between the Posts, Spielverlagerung |
| Análise de partida com dados | 1ª/3ª mista, mais opinativa | Média-alta (xG, PPDA) | Total Football Analysis |
| Explicação de métrica/modelo | 1ª pessoa do plural, didático | Alta (mas com exemplo numérico) | StatsBomb/Hudl, American Soccer Analysis |
| Tutorial replicável | 1ª pessoa, didático passo a passo | Baixa-média (foco em processo) | Comunidade StatsBomb Open Data |
| Institucional/processo | 3ª pessoa, corporativo | Baixa (conceitual, não numérico) | Hudl Blog |

### Recomendação de aplicação para os agentes da ApostaInfo

Para uma análise de partida gerada pela plataforma (que já tem probabilidades de modelo prontas),
a combinação mais próxima do "estado da arte" observado é: **estrutura do Opta Analyst** (tese +
key insights + contexto/forma + head-to-head + previsão explícita com ressalva de metodologia +
fechamento) **preenchida com o rigor de evidência tática do Total Football Analysis/Between the
Posts** (cada número citado sustenta um argumento específico sobre o jogo, não aparece solto) e
**vocabulário sempre ancorado a um exemplo**, como em Spielverlagerung.

---

## 10. Fontes

Todos os links abaixo foram visitados e lidos (não apenas indexados) para produzir este documento.

**StatsBomb / Hudl Statsbomb**
- https://www.hudl.com/blog/statsbomb-on-ball-value ("On-Ball Value (OBV): Valuing Player Actions in Football")
- https://statsbomb.com/articles/soccer/upgrading-expected-goals/ (redireciona para https://www.hudl.com/blog/upgrading-expected-goals)
- https://statsbomb.com/articles/soccer/ (listagem de artigos, para mapear temas recorrentes)

**Opta Analyst / The Analyst**
- https://theanalyst.com/articles/england-vs-argentina-prediction-world-cup-2026-match-preview
- https://theanalyst.com/articles/spain-vs-belgium-prediction-world-cup-2026-match-preview (consultado via busca/trecho)
- https://theanalyst.com/articles/germany-vs-paraguay-prediction-world-cup-2026-match-preview (consultado via busca/trecho)
- https://theanalyst.com/articles/south-africa-vs-canada-prediction-world-cup-2026-match-preview (consultado via busca/trecho)

**Between the Posts**
- https://betweentheposts.net/spain-belgium-olmo-in-the-middle-final-four-official-2-1/
- https://betweentheposts.net/tag/rudi-garcia/ (listagem de match reports, para mapear título/estrutura recorrente)

**Total Football Analysis**
- https://totalfootballanalysis.com/match-analysis/psg-chelsea-tactics-champions-league-2025-2026-tactical-analysis
- https://totalfootballanalysis.com/tactical-theory (listagem de categoria, para mapear temas recorrentes)

**Spielverlagerung**
- https://spielverlagerung.com/2015/05/08/tactical-theory-compactness/

**StatsBomb Open Data (comunidade)**
- https://thelastmananalytics.home.blog/2019/06/16/15-getting-started-with-free-statsbomb-event-data-xg-shot-map-tutorial/
- https://github.com/statsbomb/statsbombpy (documentação/README do pacote)
- https://github.com/statsbomb/open-data (repositório de dados abertos)

**American Soccer Analysis**
- https://www.americansocceranalysis.com/what-are-goals-added
- https://www.americansocceranalysis.com/home/2020/8/3/the-state-of-mls-analytics

**Hudl Blog**
- https://www.hudl.com/blog/performance-analysis-in-football
