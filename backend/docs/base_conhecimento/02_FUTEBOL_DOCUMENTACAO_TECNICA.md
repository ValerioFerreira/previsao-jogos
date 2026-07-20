# Documentação Técnica e Literatura Acadêmica de Análise de Futebol

> Documento de referência para agentes de IA que trabalham no projeto ApostaInfo (previsão
> probabilística de partidas — Dixon-Coles/Poisson bivariado, contagens NB/GP em cascata,
> Elo, mercados de gols/escanteios/cartões/BTTS/handicap, coleta via API-Football). Não é
> enciclopédia definitiva: é um mapa de fontes primárias (documentação oficial, dados abertos,
> literatura acadêmica e blogs técnicos) para consulta rápida antes de propor uma nova feature,
> hipótese de modelo ou fonte de dado.
>
> Compilado em 2026-07-20 via pesquisa com Firecrawl (busca + scraping de páginas reais).
> Resumos escritos com palavras próprias; citações diretas limitadas a trechos curtos (<15
> palavras) com atribuição, nunca reprodução de parágrafos inteiros. Nenhum conteúdo pirata
> de livros foi acessado — apenas sumários públicos, resenhas e entrevistas.

## Sumário

1. [API-Football / API-Sports](#1-api-football--api-sports)
2. [StatsBomb Open Data](#2-statsbomb-open-data)
3. [Understat](#3-understat)
4. [FBref (Sports Reference)](#4-fbref-sports-reference)
5. [Opta](#5-opta)
6. [Wyscout](#6-wyscout)
7. [Livros de referência em Football Analytics](#7-livros-de-referência-em-football-analytics)
8. [Papers e teses acadêmicas sobre football analytics](#8-papers-e-teses-acadêmicas-sobre-football-analytics)
9. [Blogs técnicos de referência](#9-blogs-técnicos-de-referência)
10. [Fontes consolidadas](#10-fontes-consolidadas)

---

## 1. API-Football / API-Sports

**API-Football** (também vendido sob a marca guarda-chuva **API-Sports**, mesma empresa/mesmo backend) é a fonte que o projeto já consome via `backend/app/services/fixture_fetch.py`. É uma API REST somente-leitura (GET), com URL base `https://v3.football.api-sports.io/` e autenticação por header único `x-apisports-key` — sem OAuth. Cobre mais de 1.200 ligas/copas no mundo todo, incluindo os torneios de clube usados na coleta deste projeto (60+ competições, ver `DOCUMENTACAO_CENTRAL.md` §17.6).

**Estrutura de resposta.** Toda chamada devolve o mesmo envelope: `get` (endpoint chamado), `parameters` (filtros ecoados), `errors` (array, vazio em sucesso), `results` (contagem da página atual), `paging` (`current`/`total`) e `response` (payload). É comum um `200` vir com `response` vazio (parâmetro inválido, dado ainda não disponível, ou simplesmente sem jogo).

**Endpoints principais** (organizados por função):
- **Referência/bootstrap** — `/timezone` (425 fusos), `/countries`, `/leagues` (catálogo completo com o objeto **`coverage`** por temporada: flags booleanas para events, lineups, fixture statistics, player statistics, standings, players, top scorers/assists/cards, injuries, predictions e odds — deve ser checado antes de chamar o endpoint correspondente, pois uma flag `false` garante resposta vazia), `/leagues/seasons`, `/teams`, `/teams/statistics` (com parâmetro `date` para snapshot histórico), `/venues`.
- **Fixtures** (o "coração" da API — todo o resto pende do `fixture.id`): `/fixtures` (filtros por `live`, `date`, `team`+`next`/`last`, `league`+`season`, `from`/`to`, `ids` em lote até 20), `/fixtures/rounds`, `/fixtures/headtohead` (H2H por par de `team` ids), `/fixtures/statistics` (chutes, posse, escanteios, faltas, cartões, passes — **campos `null` são comuns em ligas menores**, nem toda estatística é coletada para toda competição), `/fixtures/events` (timeline de gols/cartões/substituições, com `time.extra` para acréscimos), `/fixtures/lineups` (formação + titulares/banco, **disponível tipicamente 20–40 min antes do jogo**, podendo variar por competição), `/fixtures/players` (rating 0–10 e estatísticas individuais por partida).
- **Standings**, **players** (`/players`, `/players/topscorers|topassists|topyellowcards|topredcards`, `/players/squads`), **coachs**, **transfers**, **trophies**, **injuries** (atualização a cada ~4h, também condicionada à flag `coverage.injuries`) e **sidelined** (histórico de lesões/suspensões).
- **Predictions e odds:** `/predictions` é o **modelo estatístico próprio da API** (não é odds de casa de aposta) — devolve `winner`, `win_or_draw`, `under_over`, `percent` (probabilidades 1X2) e comparação de força de ataque/defesa + Poisson, atualizado a cada hora. `/odds` traz odds pré-jogo de bookmakers reais, paginado em **10 por página**, mas **retém só os últimos 7 dias** (não é possível recuperar odds retroativamente — precisa capturar no momento). `/odds/live` cobre odds ao vivo (sem histórico algum, dado descartado 5–20 min após o apito final); atenção: os IDs de tipo de aposta (`bet`) de `/odds/bets` (pré-jogo) e `/odds/live/bets` (ao vivo) **são sistemas de numeração completamente distintos** e não intercambiáveis.

**Planos e cota.** Free: 100 requisições/dia, todos os endpoints liberados (diferença entre planos é volume/profundidade histórica, não funcionalidade). Pro US$19/mês → 7.500/dia; Ultra US$29/mês → 75.000/dia (o plano que este projeto usa, conforme `ARCHITECTURE.md`/`CLAUDE.md`); Mega US$39/mês → 150.000/dia; planos custom até 1,5M/dia. Além da cota diária, há um **rate limit por minuto** simultâneo, reportado nos headers de cada resposta (`x-ratelimit-requests-remaining` para a cota diária, `X-Ratelimit-Remaining` para o limite por minuto); estourar o limite por minuto de forma repetida pode levar a bloqueio pelo firewall sem aviso prévio. Logos/escudos/bandeiras **não contam na cota**, mas têm rate limit próprio no CDN de mídia.

**Particularidades relevantes para este projeto:** paginação silenciosa é a armadilha mais comum (`/players` pagina a 20/página, `/odds` a 10/página — sempre checar `paging.total`); dados ao vivo atualizam a cada 15s (fixtures/eventos/odds live), estatísticas e player stats a cada 1 min, standings a cada hora; times têm ID persistente entre competições/temporadas (bom para chave estável); e, como o próprio material da API resume, o ID da partida é o pivô de tudo — "the fixture ID is your master key" (api-football.com, guia de introdução).

**Fontes consultadas:**
- https://www.api-football.com/documentation-v3
- https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide
- https://www.api-football.com/news/post/how-ratelimit-works
- https://www.api-football.com/pricing
- https://api-sports.io/sports/football

---

## 2. StatsBomb Open Data

**StatsBomb** (hoje parte do grupo **Hudl**) é uma empresa de dados/analytics de futebol conhecida por seu modelo de **event data** granular (inclui métricas proprietárias como xG, pressões, OBV — On-Ball Value). O repositório **`statsbomb/open-data`** no GitHub (atualmente hospedado sob a organização `hudl/open-data`, ~3,5 mil estrelas) disponibiliza gratuitamente, para pesquisa e uso não comercial, um subconjunto de competições em formato JSON, sob os termos descritos no `LICENSE.pdf` do próprio repositório — o README resume o objetivo como fornecer dados "freely available for public use for research projects" (statsbomb/open-data, GitHub).

**Estrutura de dados.** O repositório segue uma cadeia hierárquica simples de arquivos:
```
data/competitions.json                          → lista de pares competição–temporada (fonte de IDs)
data/matches/{competition_id}/{season_id}.json   → partidas de cada temporada
data/events/{match_id}.json                      → log de eventos (cronológico) de cada partida
data/lineups/{match_id}.json                     → escalações/formação de cada partida
data/three-sixty/{match_id}.json                 → dados StatsBomb 360 (só para partidas selecionadas)
```
Cada evento em `events/{match_id}.json` traz um `type` (nome do evento — passe, chute, duelo, recuperação de bola, carry, own goal etc.), localização em coordenadas de campo, time/jogador envolvidos, e atributos específicos do tipo de evento (por isso a estrutura é heterogênea entre tipos — um evento de chute tem campos como `shot.statsbomb_xg`, `shot.outcome`, `shot.freeze_frame`, enquanto um passe tem `pass.length`, `pass.angle`, `pass.outcome` etc.). O **StatsBomb Open Data Specification** (PDF versionado, atualmente v1.1, publicado no diretório `doc/` do repositório) é o glossário oficial que documenta cada tipo de evento e seus subcampos.

**Cobertura gratuita (competições confirmadas no `competitions.json` atual):** Copas do Mundo masculina (edições de 1958 a 2022, cobertura desigual por ano) e feminina (2019, 2023); Eurocopa masculina (2020, 2024) e feminina (2022, 2025); Copa América 2024; Champions League masculina (múltiplas temporadas, de 1970/71 até 2018/19, incluindo temporadas históricas dos anos 1970); Europa League (1988/89); Premier League (apenas 2003/04 e 2015/16 — cobertura limitada, não uma série histórica completa); La Liga (cobertura extensa, 2004/05 a 2020/21, tradicionalmente ligada à era Messi no Barcelona); Serie A (1986/87 e 2015/16); Bundesliga (2015/16 e 2023/24); Ligue 1 (2015/16, 2021/22, 2022/23); Liga F e FA Women's Super League e Frauen Bundesliga e Serie A Women (2023/24); NWSL (2018, 2023); MLS (2023); Liga Profesional Argentina (1981, 1997/98); Indian Super League (2021/22); Copa del Rey (temporadas antigas dos anos 1970/80); African Cup of Nations 2023; FIFA U20 World Cup (1979). A lista muda com o tempo (o próprio repositório recebe novas cargas periodicamente), então não deve ser tratada como fixa — o caminho recomendado é sempre reconsultar `competitions.json` na hora de planejar uma coleta.

**StatsBomb 360.** É uma camada adicional de contexto espacial anexada a eventos selecionados (majoritariamente chutes, em partidas/competições específicas — no `competitions.json` isso aparece como o campo `match_available_360` preenchido apenas para certas temporadas, ex.: Copa do Mundo 2022, Euro 2020/2024, Women's Euro 2022/2025, Copa do Mundo Feminina 2023, Ligue 1 2021/22–2022/23, La Liga 2020/21, MLS 2023, ACON 2023). Cada frame de 360 registra a posição de jogadores (e do goleiro) dentro da **área visível** da câmera de transmissão no instante do evento — não é tracking óptico completo do campo, mas uma amostra de "quem estava visível ao redor da jogada", útil para métricas de definição de espaço, pressão e finalização sem goleiro à frente ("clear shots").

**Fontes consultadas:**
- https://github.com/statsbomb/open-data
- https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json
- https://github.com/statsbomb/open-data/blob/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf
- https://github.com/statsbomb/statsbombpy
- https://blogarchive.statsbomb.com/news/statsbomb-360-freeze-frame-viewer-a-new-release-in-statsbomb-iq/

---

## 3. Understat

**Understat** (understat.com) é um site gratuito e independente (não afiliado a nenhuma casa de dados oficial como Opta/Stats Perform) dedicado a estatísticas de **xG (expected goals)** para as principais ligas europeias. Cobre historicamente as "top 5" ligas — Premier League, La Liga, Bundesliga, Serie A e Ligue 1 — tendo incluído também o Campeonato Russo (RFPL) em períodos anteriores; a lista de ligas disponíveis no site já variou ao longo do tempo.

O site oferece xG e xGA (xG contra) por partida, por temporada, por time e por jogador, além de métricas derivadas como NPxG (xG sem pênaltis), xA (expected assists) e xPTS (pontos esperados a partir do saldo de xG). Os dados podem ser exportados em CSV/JSON/XLSX diretamente pela interface.

Sobre a metodologia, o próprio Understat é sucinto: eles descrevem ter treinado "neural network prediction algorithms" com uma base de mais de 100 mil chutes, usando mais de 10 parâmetros por chute, para estimar a probabilidade de gol de cada finalização. Não há artigo técnico publicado, paper revisado por pares, nem detalhamento da arquitetura da rede, das features exatas ou da fonte primária dos eventos (posição do chute, tipo de jogada, pressão defensiva etc.) — é um modelo proprietário e "caixa-preta" do ponto de vista externo, cuja proveniência dos dados brutos (coordenadas de chute) não é licenciada publicamente como a da Opta.

Estudos comparativos independentes (ex.: análise publicada no ResearchGate comparando erros L1/L2 de Opta x Understat nas 5 grandes ligas, e comparações informais como as do blog Transfer Science) mostram que o xG do Understat tende a rodar sistematicamente **mais alto na média** que o da Opta/StatsBomb e apresenta padrões de viés diferentes (superestima times fracos, tem mais variância nos extremos), embora a divergência entre os provedores seja moderada (correlação ~0,92–0,93 entre eles no nível de partida). Ou seja: é um provedor útil e amplamente citado na comunidade de analytics, mas com transparência metodológica bem inferior à de provedores licenciados como Opta/StatsBomb — o que é relevante para qualquer sistema (como o deste projeto, que usa Dixon-Coles/NB próprios) que use Understat apenas como referência cruzada, não como fonte de treino direta.

**Fontes consultadas:**
- https://understat.com/
- https://fbref.com/en/expected-goals-model-explained/ (para contraste de definição de xG)
- https://www.researchgate.net/publication/387250442_Comparative_Analysis_of_Expected_Goals_Models_Evaluating_Predictive_Accuracy_and_Feature_Importance_in_European_Soccer
- https://www.transferscience.com/p/which-xg-data-should-you-trust
- https://beatthebookie.blog/2024/01/06/comparing-the-predictive-power-of-different-xg-data-providers/

---

## 4. FBref (Sports Reference)

FBref.com é operado pela **Sports Reference LLC**, a mesma empresa por trás de Baseball-Reference e Basketball-Reference. Lançou em junho de 2018 cobrindo 6 países (Inglaterra, França, Espanha, Itália, Alemanha, EUA) e hoje cobre mais de 45 países e 140+ competições, incluindo futebol feminino (Copa do Mundo Feminina completa e ligas domésticas de 9 países).

**Estrutura histórica das tabelas avançadas** (por competição/temporada/time/jogador): Standard Stats (gols, assistências, cartões, minutos), Goalkeeping, Advanced Goalkeeping (PSxG, PSxG/SoT, PSxG+/-, % de lançamento, % de defesas de cruzamento, ações fora da área — #OPA), Shooting (finalizações, xG, npxG, gols menos xG), Passing e Pass Types, Goal and Shot Creation (SCA/GCA — ações que geram finalização/gol), Defensive Actions (desarmes, interceptações, bloqueios, cortes), Possession (toques, conduções, conduções/passes progressivos, dribles) e Miscellaneous Stats.

**Glossário das métricas-chave:**
- **xG**: probabilidade de gol de um chute dado local, ângulo, parte do corpo, tipo de jogada precedente etc. — segundo a própria FBref, cada chute é comparado a milhares de chutes com características similares.
- **npxG**: xG excluindo pênaltis (cada pênalti vale ~0,75–0,80 xG fixo, então distorce comparações se não isolado).
- **xAG**: probabilidade de que um passe se torne assistência (xG do chute gerado por aquele passe).
- **PSxG (post-shot xG)**: xG recalculado após o chute, considerando a colocação real da bola (não apenas as condições pré-chute) — usado para medir desempenho de goleiro via PSxG+/- (gols evitados além do esperado).
- **Progressive carries/passes**: conduções ou passes que avançam a bola substancialmente em direção ao gol adversário, segundo limiares de distância definidos pela metodologia da Opta/StatsBomb.

**Ponto crítico e atual (relevante para julho de 2026):** essas estatísticas avançadas eram historicamente licenciadas de terceiros — inicialmente da StatsBomb, e nos últimos anos da **Opta (Stats Perform)**. Em janeiro de 2026, a Opta **encerrou unilateralmente o contrato de dados** com a Sports Reference, exigindo a remoção imediata de todos os dados avançados do site. O próprio blog da Sports Reference confirmou o fato publicamente, e cobertura do setor (The Athletic/NYT, The IX, Awful Announcing) descreveu o episódio como um "divórcio de dados" que abalou a comunidade de analytics de futebol, com impacto particularmente grave para dados avançados do futebol feminino. Isso foi **confirmado nesta pesquisa** por scrape direto: a tabela de "Advanced Goalkeeping" da Premier League 2025-26 no FBref hoje mostra os cabeçalhos de colunas (PSxG, PSxG/SoT, PSxG+/-, Cmp, Att etc.) mas com **todas as células vazias** — ou seja, a estrutura das tabelas permanece, mas os dados licenciados da Opta não estão mais sendo preenchidos. Estatísticas básicas não-licenciadas (gols, assistências, minutos, cartões — "Standard Stats") continuam disponíveis normalmente.

**Fontes consultadas:**
- https://fbref.com/en/expected-goals-model-explained/
- https://fbref.com/en/about/
- https://fbref.com/en/comps/9/keepersadv/Premier-League-Stats (evidência direta das colunas vazias)
- https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/
- https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/
- https://awfulannouncing.com/soccer/sports-reference-pulls-advanced-data-agreement-violation-dispute.html
- https://www.nytimes.com/athletic/7002196/2026/01/28/fbref-opta-football-data-soccer-analytics/

---

## 5. Opta

**Opta**, fundada em 1996 e hoje parte da **Stats Perform**, é uma das maiores provedoras primárias de dados esportivos do mundo — não um agregador, mas uma coletora primária: segundo a própria empresa, os dados são coletados em tempo real por analistas especializados e enriquecidos com visão computacional e IA, cobrindo mais de 3.900 competições e 20+ esportes, com mais de 7,2 petabytes de dados proprietários acumulados. A Opta atua como **fonte primária de eventos** para diversos produtos de terceiros — por exemplo, forneceu (até o rompimento de contrato em janeiro de 2026, ver seção 4) os dados avançados exibidos pelo FBref — e é parceira estatística oficial de ligas como a Premier League (via acordo divulgado em 2020 com a Football DataCo).

O braço editorial público da empresa é o **Opta Analyst** (theanalyst.com), onde publicam artigos abertos sobre metodologia e conteúdo de dados:

- **Opta Power Rankings**: sistema de rating hierárquico baseado em Elo que atribui uma pontuação de 0 a 100 a mais de 10.000 times masculinos e 2.000 femininos, cobrindo 183 países e 562+ ligas domésticas, atualizado diariamente. A metodologia publicamente documentada usa Elo tradicional (pontos trocados conforme resultado e expectativa prévia) organizado em uma **hierarquia de 4 níveis** (time → liga → país → continente), de forma que uma partida entre times de ligas/países diferentes atualiza também os Elos agregados de liga/país/continente envolvidos — o mecanismo que permite comparar times que nunca se enfrentaram. O Elo final é transformado para a escala 0–100 via uma "transformação de potência" (power transformation) e min-max scaling.
- **Supercomputador Opta / previsões**: usa uma combinação de odds de mercado de apostas e o próprio Opta Power Rankings para estimar probabilidades de resultado (vitória/empate/derrota) partida a partida e simular a tabela de classificação inteira, gerando probabilidades de título/rebaixamento por posição final.
- **Opta xG** e outras métricas "possession-adjusted" (ajustadas por posse de bola) também são mencionadas na literatura do setor como parte do pacote de métricas proprietárias da Opta, embora a metodologia detalhada de cálculo do xG da Opta (pesos exatos do modelo, dataset de treino) não seja publicada abertamente — de forma similar ao Understat, mas com a diferença de que a Opta licencia oficialmente seus dados posicionais brutos (coordenadas de chute) para parceiros, o que dá mais credibilidade de proveniência aos números derivados (é o que a comunidade de analytics chama de xG "de verdade", baseado em dados posicionais, em contraste com modelos que só usam estatísticas agregadas pós-jogo).

**Fontes consultadas:**
- https://theanalyst.com/articles/who-are-the-best-football-team-in-the-world-opta-power-rankings
- https://theanalyst.com/articles/power-rankings-your-club-ranked
- https://theanalyst.com/articles/opta-football-predictions
- https://www.statsperform.com/products/opta-data/
- https://www.businesswire.com/news/home/20200623005577/en/Stats-Perform-Named-Exclusive-Official-Premier-League-Statistics-Partner
- https://beatthebookie.blog/2024/01/06/comparing-the-predictive-power-of-different-xg-data-providers/

---

## 6. Wyscout

Wyscout (hoje "Hudl Wyscout", após a aquisição pela Hudl) é uma das maiores bases de vídeo e dados de futebol do mundo, com cobertura declarada de mais de 1.000 competições. Diferente de Opta ou StatsBomb — cuja proposta central é o dado de evento estruturado para análise estatística/modelagem —, o Wyscout nasceu e se posiciona primeiro como ferramenta de **scouting e vídeo**: a plataforma une filmagem completa de partidas, clipes recortados por ação e dados de desempenho de jogador num único fluxo de trabalho, permitindo que um analista sinalize um alvo de contratação e avalie-o em vídeo antes de mandar um olheiro presencial ao campo (Scouting Area, base pesquisável que combina relatórios subjetivos de olheiros, clipes de vídeo e dados de carreira/desempenho).

**Metodologia de coleta.** Segundo entrevista publicada no blog da Hudl com o diretor de direitos da empresa, cada partida é analisada por profissionais de tagging (analistas de dados treinados na modalidade), gerando em média **2.500 pontos de dados por jogo** (passes, finalizações e eventos mais granulares); ao menos 25% das partidas passam por revisão completa de qualidade. Todo o conteúdo é adquirido via acordos de direitos com ligas, clubes e federações (Football DataCo, Lega Serie A, LaLiga, ligas suíças, escandinavas, etc.) sob a categoria de "direitos de scouting" — uso B2B, com atraso em relação ao vivo, estritamente para fins profissionais (recrutamento, análise de desempenho, coaching, tutoriais), nunca para transmissão ao vivo. Vídeo é entregue em no mínimo 1080p.

**Tipos de dados oferecidos.** Três frentes centrais: (1) **eventos taggeados** (passes, duelos, finalizações, disciplina) com metadado posicional básico; (2) **vídeo** de partida completa e biblioteca de clipes recortados por tipo de ação, ponto forte histórico do produto frente aos concorrentes orientados a dados puros; (3) **dados físicos/tracking**, oferecidos via parceria (o "Physical Data Pack", usando tracking derivado de transmissão de TV/broadcast tracking) — não é tracking óptico próprio como o de empresas especializadas (ex: SkillCorner, Second Spectrum), mas um complemento contratado. A empresa também investe em automação (ex: pesquisa apresentada no OptaPro Forum sobre representações self-supervised de dados de tracking para acelerar buscas de vídeo — "situation search", auto-tagging, "fingerprints" de time), sinalizando uma aproximação gradual a workflows mais quantitativos.

**Posicionamento frente a Opta/StatsBomb.** Fontes do setor (guias de ferramentas para analistas, comparativos de bases de dados) descrevem uma divisão de papéis relativamente estável: Wyscout é citado como "padrão da indústria" para vídeo + scouting, quase universal nos departamentos de recrutamento de clubes; StatsBomb (hoje Hudl StatsBomb) é apontado como a referência em profundidade de evento e métricas avançadas (xG, on-ball value, StatsBomb 360 com dados posicionais por evento, pressões); Opta (Stats Perform) é descrito como o provedor mais estabelecido historicamente, com a maior cobertura de ligas e o dado que alimenta emissoras de TV e boa parte das estatísticas que aparecem na mídia. Na prática, muitos clubes profissionais licenciam mais de um provedor simultaneamente (Wyscout para vídeo/scouting, StatsBomb ou Opta para modelagem estatística), em vez de tratar as três como substitutas diretas.

**Uso em scouting profissional vs. modelos de previsão/apostas.** O caso de uso predominante do Wyscout permanece o scouting tradicional (olheiro/analista avaliando jogadores e adversários via vídeo) — é essa a proposta de valor mencionada em praticamente todo material institucional da Hudl. Ainda assim, há evidência de uso do dado do Wyscout em algoritmos preditivos (o próprio blog da Hudl cita clientes que "usam dados do Wyscout em seus algoritmos preditivos para medir a força de cada time"), e produtos de terceiros voltados a apostadores/analistas quantitativos citam o Wyscout como referência de preço e cobertura ao se posicionarem como alternativa mais barata voltada a "value betting". Comparado a StatsBomb (que disponibiliza uma biblioteca de dados aberta amplamente usada por pesquisadores e ao público de analytics) e ao ecossistema Opta (que alimenta diretamente muitos modelos públicos de xG/rating), o Wyscout tem pegada mais discreta em pesquisa acadêmica/pública de modelagem — reforçando que seu diferencial de mercado é vídeo + fluxo de scouting, não a abertura de dados para ciência de dados externa.

**Fontes consultadas:**
- https://www.hudl.com/blog/wyscout-video-data-sourcing-standard
- https://www.hudl.com/products/wyscout
- https://www.hudl.com/products/wyscout/scouting-area
- https://www.hudl.com/blog/kv-mechelen-wyscout-scouting
- https://www.hudl.com/blog/how-to-be-ahead-of-your-competition-with-data
- https://www.socceredu.com/en-US/blog/soccer-databases
- https://www.liamhenshaw.com/writing/the-tools-every-football-analyst-should-know
- https://www.scout52.com/what-software-do-football-scouts-use
- https://scoutingstats.ai/premium

---

## 7. Livros de referência em Football Analytics

### 7.1 Soccermatics: Mathematical Adventures in the Beautiful Game
- **Autor(es):** David Sumpter (professor de matemática aplicada, Uppsala University)
- **Editora:** Bloomsbury Sigma (edição Pro atual: 2ª ed., 2017; edição original 2016)
- **Ano:** 2016 (1ª ed.), 2017 (Pro-Edition)
- **Tese central:** futebol é um dos esportes mais "matemáticos" que existem — padrões de posicionamento, tomada de decisão coletiva e resultados de partida podem ser modelados com as mesmas ferramentas usadas em biologia (comportamento coletivo de formigas/cardumes), física estatística e teoria dos jogos.
- **Tópicos cobertos:** geometria de passe e formação (previsão de resultados, dinâmica de enxame aplicada ao meio-campo, redes de passe, distribuições estatísticas de gols); tática e gestão (teoria dos jogos aplicada a pênaltis e escalações, mapas táticos, redes neurais aplicadas a scouting); comportamento de torcida e apostas (psicologia de multidão, mercados de apostas).
- **Relevância para o projeto:** referência de divulgação mais citada que trata explicitamente de distribuição de gols como processo estatístico — ponte acessível entre o público leigo e os fundamentos de Poisson/Dixon-Coles já usados no projeto, além de discutir mercados de apostas de forma crítica (relevante para o módulo de odds/EV do backend).

### 7.2 Data Analytics in Football: Positional Data Collection, Modelling and Analysis
- **Autor(es):** Daniel Memmert e Dominik Raabe (German Sport University Cologne)
- **Editora:** Routledge (Taylor & Francis)
- **Ano:** 2018 (1ª ed.; há 2ª ed. 2024)
- **Tese central:** dados posicionais (tracking data) — e não apenas eventos — são a verdadeira "revolução" pendente na análise de futebol; defende a passagem da análise de jogo tradicional para KPIs derivados de posição/movimento coletivo, testados sobre dados reais da Bundesliga e da Champions League.
- **Tópicos cobertos:** histórico da análise posicional, tecnologias de captura (câmeras óticas, GPS), KPIs baseados em posição, vantagem de mando de campo, influência do técnico, padrões de clássicos, estudo de caso do FC Barcelona e previsão de convocados para a Copa de 2018.
- **Relevância para o projeto:** livro acadêmico mais próximo do escopo atual do projeto (contagens de eventos → KPIs → modelos preditivos), ainda que use dados de tracking que o projeto não possui; o capítulo sobre "mito da vantagem de mando" dialoga diretamente com features de mando/Elo já usadas no `Predictor`.

### 7.3 Sports Analytics and Data Science: Winning the Game with Methods and Models
- **Autor(es):** Thomas W. Miller (diretor do programa de Predictive Analytics da Northwestern University)
- **Editora:** Pearson / FT Press
- **Ano:** 2015
- **Tese central:** análise esportiva profissional combina três frentes — economia/negócio do esporte, tecnologia da informação e modelagem estatística/machine learning — ensinadas via vinhetas realistas com código completo em R e Python.
- **Tópicos cobertos:** avaliação de jogadores e times, ranqueamento, previsão de placares e decisões em dia de jogo, precificação/branding, geração de receita, simulações "e se". Não é específico de futebol (cobre beisebol, basquete, futebol americano), mas usa modelos de contagem/regressão aplicáveis a esportes de placar baixo.
- **Relevância para o projeto:** manual de boas práticas de pipeline de dados esportivos (problema → dados → modelo → interpretação → decisão); útil sobretudo para a camada de comunicação de incerteza/decisão (ex. Bet Builder).

### 7.4 Football Analytics: Now and Beyond — A Deep Dive Into the Current State of Advanced Data Analytics
- **Autor(es):** coletânea de especialistas publicada pelo Barça Innovation Hub (FC Barcelona), incluindo capítulos de Daniel Link e Steffen Lang (TU Munich), entre outros.
- **Editora:** Barça Innovation Hub (FC Barcelona)
- **Ano:** 2019
- **Tese central:** reúne, em coletânea, o estado da arte da análise avançada de dados no futebol profissional na virada da década de 2020 — da coleta de dados posicionais a aplicações táticas e de negócio dentro de um clube-referência.
- **Tópicos cobertos:** entre os capítulos identificados, "How to Find Elementary Football Structures in Positional Data" (Link & Lang) descreve métodos para identificar posses de bola e padrões táticos elementares a partir de dados de tracking (conceito de "episódio" de posse ≥3s).
- **Relevância para o projeto:** relatório técnico de nicho, usado majoritariamente como referência bibliográfica em papers acadêmicos; relevante pelo capítulo de estruturação de dados posicionais, ilustrando o "próximo nível" de granularidade que o projeto não coleta hoje.

### 7.5 The Expected Goals Philosophy: A Game-Changing Way of Analysing Football
- **Autor(es):** James Tippett
- **Editora:** autopublicado (independente)
- **Ano:** 2019
- **Tese central:** o Expected Goals (xG) — probabilidade de gol de cada finalização a partir de posição, tipo de assistência e parte do corpo — é a ferramenta que melhor separa habilidade de sorte no futebol, decisiva para clubes de orçamento menor (caso do Brentford FC) encontrarem jogadores subvalorizados.
- **Tópicos cobertos:** origem da análise estatística no futebol com Charles Reep (anos 1950); surgimento do xG via empresas como a Opta; "placar esperado" (xG scoreline); aplicação do xG em recrutamento e no mercado de apostas, com o caso Brentford FC/Matthew Benham como estudo central.
- **Relevância para o projeto:** referência de divulgação mais direta sobre o próprio conceito de "gol esperado" — central para qualquer sistema de gols via Dixon-Coles/Poisson-NB — e reforça a lógica de comparar xG contra odds de mercado para achar valor esperado positivo.

### 7.6 How to Win the Premier League: The Inside Story of Football's Data Revolution
- **Autor(es):** Ian Graham (Diretor de Pesquisa do Liverpool FC entre 2012 e 2023; hoje à frente da consultoria Ludonautics)
- **Editora:** Penguin (Cornerstone/Century)
- **Ano:** 2024
- **Tese central:** relato em primeira pessoa de como um departamento de pesquisa orientado a dados influenciou decisões concretas de um grande clube — da contratação de Jürgen Klopp à assinatura de Mohamed Salah — mostrando que vantagem competitiva sustentável vem de decisões estatísticas bem executadas.
- **Tópicos cobertos:** construção do primeiro departamento de analytics interno da Premier League; modelos estatísticos para prever partidas e performance de jogadores; reavaliação da vantagem de mando de campo durante a pandemia; recrutamento orientado por modelo (Salah como caso emblemático).
- **Relevância para o projeto:** relato mais próximo, em espírito, do problema do projeto — construir e operacionalizar modelos preditivos de futebol dentro de restrições reais — vindo de quem fez esse trabalho em escala profissional; eleito "Livro do Ano 2024" por FT, Sunday Times e Telegraph (mais narrativo que técnico).

### 7.7 The Numbers Game: Why Everything You Know About Football Is Wrong
- **Autor(es):** Chris Anderson (ex-jogador profissional, cientista político) e David Sally (economista comportamental)
- **Editora:** Viking/Penguin
- **Ano:** 2013
- **Tese central:** boa parte do "senso comum" sobre futebol — vulnerabilidade pós-gol, efeito de escanteios, relação finalizações-vitória — não se sustenta diante dos dados; o resultado de uma única partida tem componente de sorte maior do que se costuma admitir.
- **Tópicos cobertos:** história da análise estatística no futebol desde Charles Reep; desmistificação de crenças de comentarista; papel da distribuição de Poisson na modelagem de gols; peso relativo de jogadores "fracos" vs. "fortes" no resultado agregado da temporada; ceticismo de dirigentes/técnicos quanto a dados.
- **Relevância para o projeto:** cita explicitamente a distribuição de Poisson como base para modelar a probabilidade de gol por minuto — o mesmo fundamento estatístico do Dixon-Coles do projeto — e serve como inventário de "mitos populares" testáveis contra os próprios dados do projeto.

### 7.8 Soccernomics
- **Autor(es):** Simon Kuper (jornalista) e Stefan Szymanski (economista esportivo, University of Michigan)
- **Editora:** Nation Books
- **Ano:** 2009 (edições revisadas posteriores)
- **Tese central:** aplica ferramentas de economia e estatística para explicar padrões estruturais do futebol mundial — por que certos países/times têm sucesso sistemático e como o mercado de transferências frequentemente avalia mal os jogadores.
- **Tópicos cobertos:** ineficiências do mercado de transferências, fatores estruturais de sucesso de seleções nacionais, psicologia de pênaltis, mitos sobre técnicos, economia de clubes e torcida.
- **Relevância para o projeto:** mais macroeconômico/estrutural do que estatístico-preditivo — não trata de Poisson/Dixon-Coles diretamente — mas é citado como pioneiro do "Moneyball do futebol" e discute ineficiências de mercado aplicáveis ao raciocínio de valor esperado em odds.

### 7.9 Inverting the Pyramid: A History of Football Tactics (menção breve)
- **Autor(es):** Jonathan Wilson
- **Editora:** Orion Books / Bold Type Books
- **Ano:** 2008 (edições revisadas posteriores)
- **Tese central:** narra a evolução histórica das formações e filosofias táticas do futebol, sem uso de dados ou estatística — livro de história/tática, não de analytics.
- **Tópicos cobertos:** evolução de sistemas táticos por país/época, biografias de técnicos influentes, mudança de mentalidade tática ao longo do século XX.
- **Relevância para o projeto:** indireta — não traz metodologia estatística aplicável ao Dixon-Coles/Poisson/Elo do projeto, mas complementa qualitativamente ("o porquê tático") o "o quê estatístico" dos demais livros; incluído apenas por completude.

**Fontes consultadas:**
- https://www.bloomsbury.com/us/soccermatics-9781472924148/
- https://www.taylorfrancis.com/books/mono/10.4324/9781351210164/data-analytics-football-daniel-memmert-dominik-raabe
- https://www.oreilly.com/library/view/sports-analytics-and/9780133887402/
- https://www.amazon.com/Sports-Analytics-Data-Science-Winning/dp/0133886433
- https://www.researchgate.net/publication/337339250_How_to_Find_Elementary_Football_Structures_in_Positional_Data
- https://www.scribd.com/document/831818697/Football-Analytics-Now-and-Beyond
- https://www.shortform.com/summary/the-expected-goals-philosophy-summary-james-tippett
- https://www.penguin.co.uk/books/462193/how-to-win-the-premier-league-by-graham-ian/9781804950302
- https://www.goodreads.com/book/show/218356861-how-to-win-the-premier-league
- https://www.theguardian.com/books/2013/may/24/numbers-game-everything-football-wrong
- https://www.amazon.com/Soccernomics-Australia-Turkey-Iraq-Are-Destined/dp/1568584253
- https://www.amazon.com/Inverting-Pyramid-History-Football-Tactics/dp/1399610090
- https://www.boldtypebooks.com/titles/jonathan-wilson/inverting-the-pyramid/9781645030522/

---

## 8. Papers e teses acadêmicas sobre football analytics

1. **Modelling Association Football Scores and Inefficiencies in the Football Betting Market**
   - Autores: Mark J. Dixon, Stuart G. Coles
   - Ano: 1997
   - Venue/Instituição: Journal of the Royal Statistical Society: Series C (Applied Statistics), vol. 46, nº 2, pp. 265–280
   - Link: https://doi.org/10.1111/1467-9876.00065 (PDF espelhado em https://www.ajbuckeconbikesail.net/wkpapers/Airports/MVPoisson/soccer_betting.pdf)
   - Resumo: O paper fundador do modelo usado em produção neste projeto. Parte de dois Poisson independentes (ataque/defesa por time, força de mando) e corrige a correlação artificial em placares baixos (0-0, 1-0, 0-1, 1-1) com o parâmetro "rho" (Dixon-Coles adjustment) e um fator de decaimento temporal que dá menos peso a jogos antigos. Mostra que o modelo, combinado com uma estratégia de valor, gerava lucro contra as odds das casas de 1995-96 — a motivação original do "gate de eficiência de mercado" que o projeto ainda usa como referência conceitual.

2. **Analysis of Sports Data Using Bivariate Poisson Models**
   - Autores: Dimitris Karlis, Ioannis Ntzoufras
   - Ano: 2003
   - Venue/Instituição: Journal of the Royal Statistical Society: Series D (The Statistician), vol. 52, nº 3, pp. 381–393
   - Link: https://www.researchgate.net/publication/227719079
   - Resumo: Propõe o Poisson bivariado "de verdade" (com termo de covariância explícito entre gols de mandante/visitante), em vez do ajuste local de Dixon-Coles nos placares baixos, comparando-o empiricamente em ligas europeias. Referência clássica para avaliar se vale a pena trocar o "double Poisson + correção local" por um bivariado formal.

3. **Prediction and Retrospective Analysis of Soccer Matches in a League**
   - Autores: Håvard Rue, Øyvind Salvesen
   - Ano: 2000
   - Venue/Instituição: The Statistician (JRSS Series D), vol. 49, nº 3, pp. 399–418
   - Link: https://www.jstor.org/stable/2681065
   - Resumo: Estende a lógica de Dixon-Coles para um modelo Bayesiano dinâmico, em que as forças de ataque/defesa evoluem no tempo via passeio aleatório em vez de decaimento fixo por jogo. Referência canônica para qualquer experimento futuro de "ratings que variam suavemente no tempo" como alternativa ao Elo ou ao time-decay atual do pipeline.

4. **A Bivariate Weibull Count Model for Forecasting Association Football Scores**
   - Autores: Georgi Boshnakov, Tarak Kharrat, Ian G. McHale
   - Ano: 2017
   - Venue/Instituição: International Journal of Forecasting, vol. 33, nº 2, pp. 458–466
   - Link: https://doi.org/10.1016/j.ijforecast.2016.11.006
   - Resumo: Substitui a Poisson de Dixon-Coles por uma família de contagem derivada de tempos de sobrevivência Weibull, alegando capturar melhor a dependência entre os gols dos dois times sem o ajuste ad-hoc de placares baixos. Citado com frequência como benchmark competitivo ao Dixon-Coles clássico.

5. **On the Dependence in Football Match Outcomes: Traditional Model Assumptions and an Alternative Proposal**
   - Autores: Leonardo Egidi, Francesco Pauli, Nicola Torelli
   - Ano: 2021 (v2 2022)
   - Venue/Instituição: arXiv (stat.ME)
   - Link: https://arxiv.org/abs/2103.07272
   - Resumo: Questiona as premissas de dependência embutidas no Dixon-Coles original e em extensões bivariadas, argumentando que boa parte não tem justificativa sólida nos dados reais, e propõe uma modificação alternativa mantendo a simplicidade do modelo. Útil como checklist crítico antes de mexer na estrutura de dependência do DC-NB de produção.

6. **Extending the Dixon and Coles Model: An Application to Women's Football Data**
   - Autores: Rouven Michels, Marius Ötting, Dimitris Karlis
   - Ano: 2023
   - Venue/Instituição: arXiv (stat.AP)
   - Link: https://arxiv.org/abs/2307.02139
   - Resumo: Mostra que o ajuste de Dixon-Coles nos placares 0-0/1-0/0-1/1-1 é um caso particular da família Sarmanov, generalizando o método para outras distribuições discretas e aplicando a dados de futebol feminino. Relevante caso o projeto amplie escopo para competições femininas, e como prova formal de que o "ajuste Dixon-Coles" é caso especial de uma classe maior de modelos.

7. **Using ELO Ratings for Match Result Prediction in Association Football**
   - Autores: Lars Magnus Hvattum, Halvard Arntzen
   - Ano: 2010
   - Venue/Instituição: International Journal of Forecasting, vol. 26, nº 3, pp. 460–470
   - Link: https://doi.org/10.1016/j.ijforecast.2009.10.002
   - Resumo: Um dos primeiros estudos sistemáticos a adaptar o Elo (originado no xadrez) ao futebol, incluindo uma variante ponderada pela diferença de gols. Conclui que o Elo capta bem a força histórica dos times e supera métodos de frequência histórica simples, mas fica atrás das odds de mercado — achado citado exaustivamente na literatura posterior de rating dinâmico, incluindo o Elo já usado como feature no projeto.

8. **Determining the Level of Ability of Football Teams by Dynamic Ratings Based on the Relative Discrepancies in Scores Between Adversaries**
   - Autores: Anthony C. Constantinou, Norman E. Fenton
   - Ano: 2013
   - Venue/Instituição: Journal of Quantitative Analysis in Sports, vol. 9, nº 1, pp. 37–50
   - Link: https://doi.org/10.1515/jqas-2012-0036
   - Resumo: Introduz o "pi-rating", sistema dinâmico alternativo ao Elo que incorpora a margem de placar e separa desempenho em casa/fora, mostrando lucro contra odds de bookmakers em cinco temporadas da Premier League. Referência padrão de comparação ao avaliar se um rating dinâmico (Elo, pi-rating, Glicko) agrega sinal além de outro.

9. **Forecasting Football Matches by Predicting Match Statistics**
   - Autores: Edward Wheatcroft
   - Ano: 2020
   - Venue/Instituição: arXiv (stat.AP) — London School of Economics and Political Science
   - Link: https://arxiv.org/abs/2001.09097
   - Resumo: Introduz e aplica o **"GAP rating"** (Generalised Attacking Performance) — ratings separados de ataque/defesa em casa/fora, por estatística (chutes, chutes no alvo, escanteios) — para prever essas estatísticas pré-jogo e, a partir delas, o resultado e o mercado over/under 2.5. É a fonte direta da terminologia "GAP ratings" que o próprio projeto promoveu ao DC-NB de clube em 2026-07-19 (§17 da doc-mestre) para chutes e escanteios; sugere ainda extensão a handicap asiático e mercados de meio-tempo.

10. **Investigating the Efficiency of the Asian Handicap Football Betting Market with Ratings and Bayesian Networks**
    - Autores: Anthony C. Constantinou
    - Ano: 2019 (preprint 2020)
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/2003.09384
    - Resumo: Primeiro modelo publicado especificamente voltado à previsão e avaliação de eficiência do mercado de handicap asiático, combinando sistemas de rating com redes Bayesianas, testado em 13 temporadas da Premier League. Referência direta para validar o mercado de handicap asiático que o projeto deriva no predictor.

11. **A Goal Scoring Probability Model for Shots Based on Synchronized Positional and Event Data in Football (Soccer)**
    - Autores: Gabriel Anzer, Pascal Bauer
    - Ano: 2021
    - Venue/Instituição: Frontiers in Sports and Active Living (PMC8056301)
    - Link: https://pmc.ncbi.nlm.nih.gov/articles/PMC8056301/
    - Resumo: Constrói um modelo de xG usando dados posicionais sincronizados com eventos, capturando contexto de defensores/goleiro, não só a localização do chute. Ilustra o estado da arte de xG "com tracking", útil como teto de qualidade para uma eventual expansão do projeto além de contagens agregadas.

12. **The Application of Machine Learning Techniques for Predicting Results in Team Sport: A Review**
    - Autores: Rory Bunker, Teo Sušnjak
    - Ano: 2019 (revisão cobrindo 1996–2019)
    - Venue/Instituição: Applied Computing and Informatics / arXiv:1912.11762
    - Link: https://arxiv.org/abs/1912.11762
    - Resumo: Revisão sistemática de duas décadas de uso de machine learning para prever resultados em esportes de equipe, catalogando algoritmos, features e práticas de validação mais usadas — mapa de "o que já foi tentado" antes de propor um novo classificador de resultado, no espírito das regras de checar a literatura antes de testar hipótese nova.

13. **Worldwide Regional Variations in Home Advantage in Association Football**
    - Autores: Richard Pollard
    - Ano: 2006
    - Venue/Instituição: Journal of Sports Sciences, vol. 24, nº 3, pp. 231–240
    - Link: https://doi.org/10.1080/02640410500141836
    - Resumo: Estima a vantagem de mandante em dezenas de países e mostra que ela varia sistematicamente por região (maior na América do Sul, menor em partes da Europa/Ásia), sugerindo causas como viagem, altitude e cultura. Relevante para o parâmetro de vantagem de mandante do Dixon-Coles, especialmente se a coleta multi-competição (68 competições) motivar um "home advantage" por região/país em vez de global.

14. **Beating the Bookies with Their Own Numbers — And How the Online Sports Betting Market Is Rigged**
    - Autores: Lisandro N. Kaunitz, Shenjun Zhong, Javier Kreiner
    - Ano: 2017
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/1710.02824
    - Resumo: Em vez de construir um modelo próprio para competir com as odds, os autores exploram diretamente inconsistências nas odds publicadas (viés de linha, arbitragem de probabilidade implícita) para gerar retorno positivo. Lembrete de que "bater o mercado" pode vir de detectar ineficiência na própria odds, linha de pesquisa distinta da perseguida hoje pelo projeto (modelo de gols vs. mercado).

15. **Forecasting Number of Corner Kicks Taken in Association Football Using Compound Poisson Distribution**
    - Autores: não confirmado com certeza nas fontes acessadas
    - Ano: 2021
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/2112.13001
    - Resumo: Propõe uma família de Poisson composto (incluindo variante geométrica-Poisson Bayesiana) para escanteios, motivada por eles ocorrerem "em lote" com clustering serial dentro do jogo — diferente de uma contagem Poisson simples. Diretamente relevante ao mercado de escanteios do projeto, cujo doc-mestre já registrou que os ratings de escanteio em produção não passaram no gate estatístico (memória "Validação trilha B"); sugere estrutura de distribuição ainda não testada.

16. **Learning about Corner Kicks in Soccer by Analysis of Event Times Using a Frailty Model**
    - Autores: não confirmado (paper estende Peng, Hu & Swartz, 2024, Computational Statistics)
    - Ano: 2026 (preprint)
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/2602.22684
    - Resumo: Estende a modelagem de tempos-até-o-próximo-escanteio (dados de sobrevivência censurados à direita) com um modelo de fragilidade (frailty) que acomoda correlação entre escanteios do mesmo time dentro do mesmo jogo. Segunda referência recente sobre escanteios como processo temporal, complementar ao item 15.

17. **Stochastic Modelling of Football Matches (via processos de Cox / Poisson duplamente estocástico)**
    - Autores: não confirmado
    - Ano: 2023
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/2312.04338
    - Resumo: Modela gols e outros eventos do jogo como processos de Cox, permitindo que a intensidade de eventos dependa de eventos já ocorridos e de fatores externos, com log-verossimilhança côncava. Framework mais geral que o Dixon-Coles clássico, útil como referência teórica para os mercados "em cascata" (gols → escanteios → cartões) já implementados via NB sequencial no projeto.

18. **An Adaptive Glicko-2 Rating Framework for Probabilistic Football Forecasting and Season Simulation**
    - Autores: não confirmado
    - Ano: 2026 (preprint)
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/2607.01722
    - Resumo: Estende o Glicko-2 (variante do Elo que modela explicitamente incerteza/volatilidade do rating, não só o ponto estimado) para previsão de futebol e simulação de temporada inteira, argumentando que o Elo clássico ignora incerteza e contexto específico do esporte. Alternativa direta ao Elo do projeto para explorar quantificação de incerteza do próprio rating.

19. **Match Predictions in Soccer: Machine Learning vs. Poisson Approaches**
    - Autores: não confirmado
    - Ano: 2024
    - Venue/Instituição: arXiv (stat.AP)
    - Link: https://arxiv.org/abs/2408.08331
    - Resumo: Compara diretamente modelos Poisson clássicos (do tipo Dixon-Coles) com abordagens de machine learning (redes neurais, random forest) para prever resultados de futebol, no mesmo conjunto de dados. Comparação equivalente ao teste já registrado na memória do projeto ("Regressor λ/μ" — XGBoost/LightGBM/HistGBM testados, nenhum bateu o GBM sklearn em produção), servindo de confirmação externa desse achado.

20. **Ranking Soccer Teams on Basis of Their Current Strength: A Comparison of Maximum Likelihood Approaches**
    - Autores: não confirmado (associado a versão de journal em Statistical Modelling, vol. 19, pp. 55–73, 2019)
    - Ano: 2017 (preprint) / 2019 (journal)
    - Venue/Instituição: arXiv:1705.09575 / Statistical Modelling
    - Link: https://arxiv.org/abs/1705.09575
    - Resumo: Compara dez modelos de força de time (Thurstone-Mosteller, Bradley-Terry, Poisson independente e Poisson bivariado), todos ajustados por máxima verossimilhança ponderada com fator de importância de jogo e fator de decaimento temporal. Relevante ao "sweep de pesos de gols" já testado no projeto (memória "Sweep pesos gols" — time-decay não ajudou, downweight de amistosos foi o único ganho), por comparar formalmente vários esquemas de ponderação temporal.

21. **Machine Learning Application in Soccer: A Systematic Review**
    - Autores: não confirmado
    - Ano: 2022
    - Venue/Instituição: revista de ciências do esporte/dados (PMC9806754)
    - Link: https://pmc.ncbi.nlm.nih.gov/articles/PMC9806754/
    - Resumo: Revisão sistemática identificando estudos originais que aplicaram ML ao futebol, mapeando domínios de aplicação (previsão de resultado, scouting, tática, lesões) e lacunas metodológicas comuns (vazamento de dados, validação temporal inadequada). Complementa o item 12 com foco mais recente e mais amplo que só previsão de resultado.

22. **TacticAI: An AI Assistant for Football Tactics**
    - Autores: Zhe Wang, Petar Veličković, Daniel Hennes et al. (Google DeepMind, em colaboração com o Liverpool FC)
    - Ano: 2024
    - Venue/Instituição: arXiv:2310.10553 / Nature Communications (PMC10951310)
    - Link: https://arxiv.org/abs/2310.10553
    - Resumo: Sistema de IA (componente preditivo + generativo, com redes neurais em grafo) desenvolvido e validado em parceria direta com o departamento de análise do Liverpool FC, focado em escanteios — prevê o desfecho tático de um escanteio e sugere posicionamentos alternativos que especialistas humanos preferiram em testes cegos na maioria dos casos. Caso público mais documentado de IA aplicada a tática de clube profissional (contraponto ao caso Ian Graham/Liverpool do item 7.6 da seção de livros).

23. **A Statistical Theory of Optimal Decision-Making in Sports Betting**
    - Autores: não confirmado
    - Ano: 2023
    - Venue/Instituição: PLOS ONE (PMC10306238)
    - Link: https://pmc.ncbi.nlm.nih.gov/articles/PMC10306238/
    - Resumo: Formaliza princípios de decisão ótima em apostas esportivas (dimensionamento de aposta, critério de Kelly, tratamento de incerteza do próprio modelo), motivado pela legalização recente de apostas esportivas na América do Norte. Relevante à camada de Bet Builder/EV do projeto além da modelagem de probabilidade pura.

24. **Data Analytics in the Football Industry: A Survey Investigating Operational Frameworks and Practices in Professional Clubs and National Federations from Around the World**
    - Autores: não confirmado
    - Ano: 2024
    - Venue/Instituição: journal de ciências do esporte (indexado PubMed, PMID 38745403)
    - Link: https://pubmed.ncbi.nlm.nih.gov/38745403/
    - Resumo: Levantamento com profissionais de clubes e federações nacionais sobre como analytics é efetivamente usado (ou não) na prática operacional, contrastando com o que a literatura acadêmica assume. Complementa a perspectiva puramente estatística dos demais itens com a lente de adoção organizacional real.

**Fontes consultadas:**
- https://doi.org/10.1111/1467-9876.00065
- https://www.ajbuckeconbikesail.net/wkpapers/Airports/MVPoisson/soccer_betting.pdf
- https://www.researchgate.net/publication/227719079
- https://www.jstor.org/stable/2681065
- https://doi.org/10.1016/j.ijforecast.2016.11.006
- https://arxiv.org/abs/2103.07272
- https://arxiv.org/abs/2307.02139
- https://doi.org/10.1016/j.ijforecast.2009.10.002
- https://doi.org/10.1515/jqas-2012-0036
- https://arxiv.org/abs/2001.09097
- https://arxiv.org/abs/2003.09384
- https://pmc.ncbi.nlm.nih.gov/articles/PMC8056301/
- https://arxiv.org/abs/1912.11762
- https://doi.org/10.1080/02640410500141836
- https://arxiv.org/abs/1710.02824
- https://arxiv.org/abs/2112.13001
- https://arxiv.org/abs/2602.22684
- https://arxiv.org/abs/2312.04338
- https://arxiv.org/abs/2607.01722
- https://arxiv.org/abs/2408.08331
- https://arxiv.org/abs/1705.09575
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9806754/
- https://arxiv.org/abs/2310.10553
- https://pmc.ncbi.nlm.nih.gov/articles/PMC10306238/
- https://pubmed.ncbi.nlm.nih.gov/38745403/

---

## 9. Blogs técnicos de referência

### David Sumpter — Soccermatics (livro, blog, YouTube, curso)
**Status: ativo** (post mais recente localizado: 15 de maio de 2026, "The Pyramids were not built in a day: how data brought long-term success"). Professor de matemática aplicada na Uppsala University, autor do livro *Soccermatics* (2016) e de obras subsequentes (*Outnumbered*, *The Ten Equations*, *Four Ways of Thinking*), Sumpter é uma das vozes mais duradouras da área. Hoje publica principalmente no Medium (`soccermatics.medium.com`), mantém documentação de curso em `soccermatics.readthedocs.io` e um canal ativo no X. Contribuições mais citadas: os fundamentos matemáticos de modelagem de futebol popularizados pelo livro *Soccermatics*, e a série de vídeos/curso **Friends of Tracking**, criada em parceria com analistas como John Muller, que se tornou referência introdutória de tracking data e xT para quem entra na área. Trabalha também como consultor de clubes (via a empresa Twelve) e recentemente tem escrito sobre uso de IA na análise de futebol.

### StatsBomb blog (statsbomb.com/articles)
**Status: ativo, mas migrado.** O blog histórico da StatsBomb (`blogarchive.statsbomb.com`) está congelado desde agosto de 2024 — a StatsBomb foi incorporada à Hudl e o conteúdo editorial passou para `hudl.com/blog` sob a categoria "Statsbomb" (posts confirmados até junho de 2026, ex.: "Defensive Responsibility: A New Way To Measure Defensive Output"). Foco: métricas de evento avançadas (xG, StatsBomb 360, **On-Ball Value/OBV**), dados de pressão para análise de oposição, e uma biblioteca de dados aberta amplamente usada por pesquisadores/estudantes como ponto de partida para portfólio em football analytics. Post mais citado historicamente: a série "How To Get Started In Football Analytics", que compila os artigos mais lidos do arquivo desde 2013; mais recentemente, o lançamento do OBV como métrica de valoração de ações de jogador tornou-se referência frequente em discussões de mercado.

### Karun Singh (karun.in)
**Status: inativo como blog regular** (apenas três posts publicados, o mais recente de 2020, sobre representações self-supervised para dados de tracking apresentadas no OptaPro Forum 2020; sem atualizações desde então). Apesar do baixo volume, seu impacto foi desproporcional: o post **"Introducing Expected Threat (xT)"** (karun.in/blog/expected-threat.html) se tornou uma das referências mais replicadas da comunidade de analytics para valorizar ações de posse de bola por localização no campo, citado e reimplementado em bibliotecas de terceiros (ex.: DataBallPy) e em palestras de conferência (StatsBomb Innovation in Football, 2019). O segundo post mais citado é sobre redes de passe interativas.

### John Burn-Murdoch (Financial Times)
**Status: ativo**, mas não é um blog de futebol dedicado — Burn-Murdoch é colunista e chief data reporter do FT, autor da coluna semanal "Data Points", cobrindo majoritariamente política, economia e saúde pública, com incursões ocasionais em futebol (visualizações de dados esportivos aparecem esporadicamente dentro do fluxo maior de jornalismo de dados do FT). Relevante para a base de conhecimento mais como referência de **prática de visualização e comunicação de incerteza estatística** do que como fonte de metodologia de modelagem de futebol propriamente dita.

### FiveThirtyEight soccer (SPI ratings)
**Status: encerrado.** O FiveThirtyEight foi desativado pela ABC News/Disney em 5 de março de 2025 (parte de uma rodada de cortes), e os artigos originais foram posteriormente removidos do ar pela ABC (redirecionados para abcnews.com/politics) — episódio que o próprio fundador Nate Silver criticou publicamente em maio de 2026 como apagamento do arquivo. O produto de futebol (Soccer Power Index/SPI, ratings de clubes e seleções com projeções de probabilidade de resultado) havia sido descontinuado antes mesmo do fechamento total do site. Os dados históricos permanecem arquivados publicamente no repositório GitHub `fivethirtyeight/data` (`soccer-spi/`), ainda usado por terceiros como base de replicação e ensino, mas não há mais atualização nem sucessor direto mantido pela ESPN/Disney no mesmo padrão de transparência metodológica. Nate Silver mantém a newsletter *Silver Bulletin*, sem foco em futebol.

### Outros relevantes

- **Opta Analyst / The Analyst (theanalyst.com, Stats Perform)** — status ativo, alto volume editorial (a própria Stats Perform declara mais de um milhão de visitantes/mês), cobrindo estatística de jogo, storytelling orientado a dados e definições oficiais de eventos Opta; é hoje a porta de entrada pública mais visível do ecossistema Opta.
- **Hudl StatsBomb / OBV** — ver acima; vale destacar separadamente como referência de métrica porque On-Ball Value se tornou um benchmark citado fora do próprio blog da empresa.
- **Twenty3** — empresa de dados e consultoria esportiva (antiga StatsPerform/OptaPro adjacent, hoje independente) com presença ativa via funcionários publicando em blogs pessoais e redes (ex.: Jan Van Haaren, cientista de dados na Twenty3, mantém blog próprio sobre "playing football's information game"); não identificado um blog institucional único com o mesmo volume dos anteriores.
- **Friends of Tracking (YouTube)** — canal citado junto com Sumpter acima; funciona como curso gratuito recorrente (convidados incluem John Muller, ex-analista da Arsenal/The Athletic) e é frequentemente apontado, junto ao curso "Introduction to Football Analytics" da StatsBomb, como um dos dois pontos de entrada mais recomendados para quem começa na área.
- **Analytics FC (analyticsfc.co.uk/blog)** — consultoria britânica de football intelligence com blog próprio ativo, citada em parcerias recentes (ex.: colaboração com a agência Sport Invest); volume editorial menor e mais voltado a estudos de caso comerciais que a metodologia aberta.
- **Get Goalside Analytics (getgoalsideanalytics.com)** — blog independente identificado durante a pesquisa com conteúdo técnico sobre xT e crítica de posicionamento de mercado dos provedores de dados; vale como fonte secundária, não como pilar da comunidade.

**Fontes consultadas:**
- https://soccermatics.medium.com/
- https://soccermatics.readthedocs.io/
- https://blogarchive.statsbomb.com/articles/
- https://www.hudl.com/blog/elite/statsbomb
- https://www.hudl.com/blog/statsbomb-on-ball-value
- https://courses.statsbomb.com/courses/introduction-to-football-analytics
- https://karun.in/blog/
- https://karun.in/blog/expected-threat.html
- https://karun.in/blog/ssr-tracking-data.html
- https://www.getgoalsideanalytics.com/research-focus-expected-threat-xt/
- https://www.ft.com/john-burn-murdoch
- https://professional.ft.com/en-gb/blog/data-visualisation-ft-qa-john-burn-murdoch/
- https://en.wikipedia.org/wiki/FiveThirtyEight
- https://www.natesilver.net/p/a-few-words-about-fivethirtyeight
- https://frontofficesports.com/abc-disney-layoffs-538-shuttered/
- https://nypost.com/2026/05/15/media/nate-silver-blasts-ex-bosses-at-abc-for-deleting-fivethirtyeight-archives-bunch-of-a-holes/
- https://github.com/fivethirtyeight/data/blob/master/soccer-spi/README.md
- https://theanalyst.com/
- https://www.statsperform.com/insights/opta-by-stats-perform-global-leader-ai-sports-data-analytics/
- https://analyticsfc.co.uk/blog/
- https://github.com/eddwebster/football_analytics
- https://bsky.app/profile/janvanhaaren.be

---

## 10. Fontes consolidadas

Lista consolidada de todos os links reais coletados por seção (ver também "Fontes consultadas" ao final de cada seção acima).

### Documentação/produto oficial (fontes primárias de dados)
- https://www.api-football.com/documentation-v3
- https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide
- https://www.api-football.com/news/post/how-ratelimit-works
- https://www.api-football.com/pricing
- https://api-sports.io/sports/football
- https://github.com/statsbomb/open-data
- https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json
- https://github.com/statsbomb/open-data/blob/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf
- https://github.com/statsbomb/statsbombpy
- https://blogarchive.statsbomb.com/news/statsbomb-360-freeze-frame-viewer-a-new-release-in-statsbomb-iq/
- https://understat.com/
- https://fbref.com/en/expected-goals-model-explained/
- https://fbref.com/en/about/
- https://fbref.com/en/comps/9/keepersadv/Premier-League-Stats
- https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/
- https://theanalyst.com/articles/who-are-the-best-football-team-in-the-world-opta-power-rankings
- https://theanalyst.com/articles/power-rankings-your-club-ranked
- https://theanalyst.com/articles/opta-football-predictions
- https://www.statsperform.com/products/opta-data/
- https://www.businesswire.com/news/home/20200623005577/en/Stats-Perform-Named-Exclusive-Official-Premier-League-Statistics-Partner
- https://www.hudl.com/blog/wyscout-video-data-sourcing-standard
- https://www.hudl.com/products/wyscout
- https://www.hudl.com/products/wyscout/scouting-area
- https://www.hudl.com/blog/kv-mechelen-wyscout-scouting
- https://www.hudl.com/blog/how-to-be-ahead-of-your-competition-with-data

### Jornalismo/imprensa do setor (contexto e verificação de fatos)
- https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/
- https://awfulannouncing.com/soccer/sports-reference-pulls-advanced-data-agreement-violation-dispute.html
- https://www.nytimes.com/athletic/7002196/2026/01/28/fbref-opta-football-data-soccer-analytics/
- https://en.wikipedia.org/wiki/FiveThirtyEight
- https://www.natesilver.net/p/a-few-words-about-fivethirtyeight
- https://frontofficesports.com/abc-disney-layoffs-538-shuttered/
- https://nypost.com/2026/05/15/media/nate-silver-blasts-ex-bosses-at-abc-for-deleting-fivethirtyeight-archives-bunch-of-a-holes/
- https://github.com/fivethirtyeight/data/blob/master/soccer-spi/README.md
- https://www.theguardian.com/books/2013/may/24/numbers-game-everything-football-wrong

### Análises/estudos comparativos independentes
- https://www.researchgate.net/publication/387250442_Comparative_Analysis_of_Expected_Goals_Models_Evaluating_Predictive_Accuracy_and_Feature_Importance_in_European_Soccer
- https://www.transferscience.com/p/which-xg-data-should-you-trust
- https://beatthebookie.blog/2024/01/06/comparing-the-predictive-power-of-different-xg-data-providers/
- https://www.socceredu.com/en-US/blog/soccer-databases
- https://www.liamhenshaw.com/writing/the-tools-every-football-analyst-should-know
- https://www.scout52.com/what-software-do-football-scouts-use
- https://scoutingstats.ai/premium

### Livros (editoras, resenhas, entrevistas)
- https://www.bloomsbury.com/us/soccermatics-9781472924148/
- https://www.taylorfrancis.com/books/mono/10.4324/9781351210164/data-analytics-football-daniel-memmert-dominik-raabe
- https://www.oreilly.com/library/view/sports-analytics-and/9780133887402/
- https://www.amazon.com/Sports-Analytics-Data-Science-Winning/dp/0133886433
- https://www.researchgate.net/publication/337339250_How_to_Find_Elementary_Football_Structures_in_Positional_Data
- https://www.scribd.com/document/831818697/Football-Analytics-Now-and-Beyond
- https://www.shortform.com/summary/the-expected-goals-philosophy-summary-james-tippett
- https://www.penguin.co.uk/books/462193/how-to-win-the-premier-league-by-graham-ian/9781804950302
- https://www.goodreads.com/book/show/218356861-how-to-win-the-premier-league
- https://www.amazon.com/Soccernomics-Australia-Turkey-Iraq-Are-Destined/dp/1568584253
- https://www.amazon.com/Inverting-Pyramid-History-Football-Tactics/dp/1399610090
- https://www.boldtypebooks.com/titles/jonathan-wilson/inverting-the-pyramid/9781645030522/

### Papers e teses acadêmicas (ver seção 8 para a lista completa com resumos)
- https://doi.org/10.1111/1467-9876.00065 (Dixon & Coles, 1997 — paper fundador)
- https://www.researchgate.net/publication/227719079 (Karlis & Ntzoufras, 2003)
- https://www.jstor.org/stable/2681065 (Rue & Salvesen, 2000)
- https://doi.org/10.1016/j.ijforecast.2016.11.006 (Boshnakov, Kharrat & McHale, 2017)
- https://arxiv.org/abs/2103.07272 (Egidi, Pauli & Torelli, 2021)
- https://arxiv.org/abs/2307.02139 (Michels, Ötting & Karlis, 2023)
- https://doi.org/10.1016/j.ijforecast.2009.10.002 (Hvattum & Arntzen, 2010 — Elo)
- https://doi.org/10.1515/jqas-2012-0036 (Constantinou & Fenton, 2013 — pi-rating)
- https://arxiv.org/abs/2001.09097 (Wheatcroft, 2020 — GAP rating)
- https://arxiv.org/abs/2003.09384 (Constantinou, 2019/2020 — handicap asiático)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC8056301/ (Anzer & Bauer, 2021 — xG com tracking)
- https://arxiv.org/abs/1912.11762 (Bunker & Sušnjak, 2019 — review ML)
- https://doi.org/10.1080/02640410500141836 (Pollard, 2006 — vantagem de mando)
- https://arxiv.org/abs/1710.02824 (Kaunitz, Zhong & Kreiner, 2017)
- https://arxiv.org/abs/2112.13001 (compound Poisson — escanteios)
- https://arxiv.org/abs/2602.22684 (frailty model — escanteios)
- https://arxiv.org/abs/2312.04338 (processos de Cox — gols)
- https://arxiv.org/abs/2607.01722 (Glicko-2 adaptativo)
- https://arxiv.org/abs/2408.08331 (ML vs. Poisson)
- https://arxiv.org/abs/1705.09575 (comparação de modelos de força de time)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9806754/ (review sistemático de ML no futebol)
- https://arxiv.org/abs/2310.10553 (TacticAI — DeepMind/Liverpool FC)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC10306238/ (decisão ótima em apostas esportivas)
- https://pubmed.ncbi.nlm.nih.gov/38745403/ (survey de adoção de analytics em clubes/federações)

### Blogs técnicos / comunidade
- https://soccermatics.medium.com/
- https://soccermatics.readthedocs.io/
- https://blogarchive.statsbomb.com/articles/
- https://www.hudl.com/blog/elite/statsbomb
- https://www.hudl.com/blog/statsbomb-on-ball-value
- https://courses.statsbomb.com/courses/introduction-to-football-analytics
- https://karun.in/blog/
- https://karun.in/blog/expected-threat.html
- https://karun.in/blog/ssr-tracking-data.html
- https://www.getgoalsideanalytics.com/research-focus-expected-threat-xt/
- https://www.ft.com/john-burn-murdoch
- https://professional.ft.com/en-gb/blog/data-visualisation-ft-qa-john-burn-murdoch/
- https://theanalyst.com/
- https://www.statsperform.com/insights/opta-by-stats-perform-global-leader-ai-sports-data-analytics/
- https://analyticsfc.co.uk/blog/
- https://github.com/eddwebster/football_analytics
- https://bsky.app/profile/janvanhaaren.be

**Total de fontes reais distintas citadas neste documento: ~90 URLs**, cobrindo documentação oficial de produto, repositórios de dados abertos, artigos de imprensa especializada, páginas de editoras/livrarias, e papers/preprints acadêmicos (arXiv, PMC/PubMed, DOIs de journal). Nenhum PDF/epub pirata de livro foi acessado; resumos de livros e papers foram escritos com palavras próprias a partir de descrições públicas (sumários, resenhas, abstracts, entrevistas).
