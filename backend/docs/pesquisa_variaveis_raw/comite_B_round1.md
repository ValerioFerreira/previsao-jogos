# Comitê B — Round 1: Viabilidade de dados e engenharia

**Data:** 2026-07-24
**Revisor:** Comitê B ("Viabilidade de dados e engenharia") — 1 de 3 revisores independentes do
comitê técnico sobre `PESQUISA_VARIAVEIS_EXTERNAS.md` (7 agentes de domínio, wave 1).

**Mandato:** não reavaliar mérito estatístico (isso é trabalho dos outros comitês) — avaliar,
para cada candidato relevante, **o que dá pra construir hoje com o que já coletamos** vs **o que
exige orçamento/fonte nova**, e separar bloqueio real de dado de simples falta de um job de
coleta.

---

## 1. Reclassificação de complexidade

A tabela mestre marca "complexidade" como um único eixo (Baixa/Média/Alta), o que mistura duas
coisas muito diferentes: dificuldade **estatística/de engenharia** (quanto trabalho de código) e
dificuldade **de dado** (se a fonte já existe na coleta atual ou precisa de orçamento/parceria
nova). Uso 6 categorias para separar os dois eixos:

- **A** — zero dado novo, engenharia trivial-baixa (dias, reusa pipeline existente)
- **B** — zero dado novo, mas estatística/engenharia pesada (semanas, MCMC/reestruturação)
- **C** — dado já acessível via endpoint que já usamos, só falta um job de coleta em escala
- **D** — fonte externa nova, barata/estável, baixo risco (ex. clima)
- **E** — fonte externa nova, sem API oficial, risco de ToS/instabilidade real
- **F** — bloqueado por ausência real do dado (não existe caminho de aquisição realista no porte atual)

| candidato | agente(s) | complexidade original | reclassificação (comitê B) | por quê |
|---|---|---|---|---|
| **Elo ajustado por margem de gols** (ClubElo/SPI-style) | 4 | Baixa/Média | **A** | Troca só o termo de "resultado observado" na função de update do Elo já em produção por uma versão contínua de margem de gols. Placar já está no dataset de treino. Nenhuma fonte nova, nenhuma reestruturação — é um sweep de 1 parâmetro, no mesmo espírito de `sweep-pesos-gols.md`. |
| **G-Elo (Adjacent-Categories)** | 1 | Baixa/Média | **A** | Mantém a forma fechada do update do Elo; só troca a definição de y/G(z) por um modelo ordinal estimável por MLE simples a partir das frequências históricas de margem — sem MCMC, sem dado novo. Único cuidado real é reestimar α_h/δ_h por competição, o que já é rotina (K por competição já existe). |
| **Dedução de rating por lesão ponderada por status** | 5 | Média | **C+B** (misto) | O agente marcou "média" como se fosse um bloco único, mas são duas coisas distintas: (1) `/injuries` já é chamado pela API-Football — falta só um job de coleta em escala e estruturação de status/gravidade (isso é **C**, puramente engenharia de coleta); (2) definir o "peso de impacto" por jogador (minutos/rating) e testar sob gate é trabalho de modelagem real (**B**). Separar os dois evita subestimar quanto trabalho é coleta vs quanto é ciência de dados. |
| **`/injuries` de clube em massa** (job de coleta, não candidato de feature per se) | 5, 7 (implícito) | (não listado como item próprio na tabela mestre) | **A/C** | O endpoint já é usado para seleção sob demanda e já funciona tecnicamente para clube via `team_id` — é a MESMA chamada, só falta rodar em escala e persistir. Nenhum dos 7 agentes tratou isso como candidato de 1ª classe, mas é o pré-requisito comum de 3 candidatos diferentes (ver §2). Deveria ranquear mais alto do que "Média" sugere. |
| **Calibração Beta** | 6 | Baixa | **A** | Confirmado pelo próprio agente 6: reusa a saída do modelo já treinado + rótulo real, mesmo pipeline da isotônica atual. `sklearn.linear_model.LogisticRegression` sobre 2 colunas. Testável em 1 dia sob gate §6. |
| **Calibração de Dirichlet (multiclasse)** | 6 | Média | **A** | Implementação é 1 camada linear + softmax sobre log-probabilidades — mecanicamente simples. O "média" do agente reflete o cuidado de validar sob gate temporal, não dificuldade de construção. Sem dado novo. |
| **Bias correction segmentada por liga/mercado** | 6 | Média | **B** | Zero dado novo (reusa o dataset de `bias_correction.joblib` já existente), mas o "média" original subestima o risco: precisa de shrinkage por volume mínimo por segmento para não recriar o mesmo overfit de amostra pequena que já reprovou a isotônica em chutes — é desenho estatístico real, não só "adicionar um groupby". |
| **PSI — monitoramento de drift** | 6 | Baixa-média | **A** | Fórmula trivial, usa dados de treino/produção já existentes. O trabalho real é decidir cadência/quais variáveis — decisão de processo, não implementação. Confirmar: é lacuna de processo genuína (nada documentado hoje), não redescoberta. |
| **Workflow leakage-aware — auditoria de escalação point-in-time** | 6 | Baixa (auditoria) | **A** | É checklist de auditoria de código (`predictor.py::build_row()`), não modelo novo. Deveria ser praticamente gratuito de executar e é o tipo de achado que, se confirmar um leak fino, vale mais que qualquer feature nova da lista. |
| **Clima no kickoff** (temp/precip/vento) | 7 | Baixa | **D** | O agente 7 já é honesto que é "custo trivial", mas trivial não é o mesmo que "já temos" — é uma fonte externa nova (Visual Crossing/OpenWeatherMap), ainda que barata e estável. Reclassifico para deixar explícito que qualquer feature de clima adiciona uma dependência externa nova ao pipeline de treino, mesmo que pequena. |
| **Importância de jogo via posição na tabela (dead rubber)** | 7 | Baixa | **A** | O próprio agente 7 já nota: "a resposta correta é não precisa de fonte nova". Concordo e reforço — standings são reconstruíveis do histórico de resultados já coletado, sem chamada de API adicional. |
| **Valor de mercado de elenco** (Transfermarkt) | 7 | Média | **E** | "Média" esconde que não existe API oficial — depende de scraper de terceiro (Apify/Parse.bot) cujo ToS explicitamente não autoriza uso comercial dos dados extraídos. Para um produto que cobra do usuário (ApostaInfo é monetizado), isso é um risco de produto, não só de engenharia. Reclassifico para refletir o risco, não só o esforço de integração. |
| **Ausência ponderada por valor de mercado do jogador** | 7 | Média | **E** (herda de Transfermarkt) | Metade do candidato (`/injuries`) é categoria C; a outra metade (peso por valor de mercado) depende do mesmo scraper de Transfermarkt, incluindo fuzzy-match de nome de jogador entre fontes (risco técnico adicional citado pelo próprio agente). O candidato como um todo herda o risco da parte mais frágil. |
| **Overround por liga como feature de confiança/peso** | 3 | Baixa | **A** | Cálculo direto (`Σ(1/odds)−1`) sobre odds já coletadas via `{,club_}odds_bookmaker_latest` (§22). Nenhuma fonte nova, nenhuma modelagem pesada. |
| **Vantagem de mandante variável no tempo** | 1, 3 | Média | **A/B** | Não precisa de fonte nova (mando de campo, calendário e Elo pré-jogo já existem), mas decidir a forma funcional (tendência linear? spline? por-divisão?) é trabalho estatístico real, não trivial. Fica no meio: dado é grátis, desenho não é. |
| **Compound Poisson / geometric-Poisson escanteios com regressão de forma** | 1 | Alta | **B** (Alta confirmada, mas explicitamente "sem gap de dado") | É o candidato com evidência mais forte de toda a pesquisa (Sharpe 3,07 vs 1,52 contra odds reais da HKJC), mas a dificuldade é 100% estatística (MCMC/Stan, múltiplas equações simultâneas) — os insumos (TG, supremacia, médias móveis) já são exatamente os agregados que `aggregates.py` mantém. Não é um "não dá pra fazer" — é "dá pra fazer, mas é um sprint de pesquisa dedicado, não uma tarde". |
| **Flag "mesma competição" como interação explícita** | 5 | Média | **A** | 100% derivável do dataset já coletado (Elo, mando, id de competição por partida) — é reestruturar a pipeline de forma recente, não buscar dado novo. O "média" reflete o trabalho de engenharia de refatorar a feature de forma, não uma barreira de dado. |

**Padrão geral:** a maioria dos candidatos marcados "Média" pelos agentes de domínio na verdade
se decompõe em uma parte trivial (A) e uma parte de risco real (E) ou de esforço estatístico
genuíno (B) — a categoria única "Média" escondia essa mistura. Isso é o achado mais acionável
desta seção: **separar o candidato composto em suas partes reclassifica o ranking de prioridade**
(ex. lesão ponderada por status vira "fácil hoje" na parte de coleta + "vale testar depois" na
parte de peso; ausência ponderada por valor de mercado vira "arriscado" só por causa da metade
Transfermarkt, não por causa do `/injuries`).

---

## 2. Combinações que compartilham custo de coleta/engenharia

Candidatos de agentes DIFERENTES que, se implementados, reaproveitariam a mesma chamada de API
ou o mesmo pipeline de engenharia — vale sequenciar como um único esforço, não 3-4 separados:

1. **Job de coleta `/injuries` de clube em massa** (endpoint já usado sob demanda) é pré-requisito
   comum de: **dedução de rating por lesão ponderada por status** (agente 5), **ausência ponderada
   por valor de mercado** (agente 7 — metade não-Transfermarkt), e a própria melhoria incremental
   de "ausência binária → ausência com granularidade de status" já mencionada no índice mestre
   (linha 71). Construir o job uma vez abre os três.

2. **Pipeline de calibração pós-hoc já em produção** (isotônica para O/U) é a mesma infraestrutura
   que serve **Calibração Beta**, **Calibração Dirichlet** e **Venn-Abers** (todos agente 6) — os
   três reusam "saída do modelo já treinado + rótulo real + holdout temporal do gate §6". Testar os
   três como variações do mesmo experimento (não três PRs separados) é mais barato e comparável.

3. **Endurecimento do gate §6** (Purged K-Fold + Embargo, PSI, RPS como métrica complementar,
   auditoria leakage-aware de escalação — todos agente 6) tocam a mesma infraestrutura de CV
   temporal expanding já em produção. Vale tratar como um único "sprint de robustez de validação"
   em vez de 4 iniciativas independentes — o trabalho de mapear "qual período cada rótulo cobre"
   (Purged K-Fold) é o mesmo mapeamento que a auditoria leakage-aware precisa fazer.

4. **`venue` + `date` já existe como chave no dataset de treino** — serve tanto para **clima no
   kickoff** (agente 7) quanto para qualquer feature geoespacial futura (o projeto já testou
   altitude/viagem, ver CLAUDE.md). Um único pipeline de geocodificação de `venue.city` serve
   ambos sem chamada de API adicional por candidato.

5. **Tabela de odds já coletada** (`{,club_}odds_bookmaker_latest`, §22) é a fonte comum de
   **overround por liga como feature de confiança** (agente 3), **Blend Bayesiano modelo+odds**
   (agente 1) e a infraestrutura de devig já usada no Verificador de Bets/§20. Nenhum candidato
   aqui pede uma chamada de API nova — é reaproveitamento de dado já em produção.

6. **Update do Elo em `predictor.py`** é o ponto de mudança comum de **Elo ajustado por margem de
   gols** (agente 4), **G-Elo** (agente 1) e, parcialmente, **vantagem de mandante variável no
   tempo** (agentes 1/3, se implementada como termo do mesmo modelo hierárquico). Os três mexem na
   mesma função e podem ser testados no mesmo sweep experimental (mesmo padrão de
   `sweep-pesos-gols.md`).

7. **Pipeline de forma recente (l3/l5/l10)** é a base comum de **flag "mesma competição" como
   interação** (agente 5), **flag de continuidade de comissão técnica** (agente 5) e **"quality
   wins"** (agente 5) — os três são reestruturações da mesma janela de histórico recente, não
   fontes de dado novas. Vale testar como um bloco (como o próprio agente 5 relatou que a fonte
   original testou — "features A-Z" em bloco), não isoladamente.

---

## 3. Bloqueado por dado real vs. só falta engenharia de coleta

Esta distinção é o achado mais importante desta revisão: a lista abaixo separa o que é
genuinamente impossível de construir sem uma nova parceria/orçamento do que é "só falta alguém
rodar o job".

### Bloqueado por ausência real de dado (sem caminho de aquisição realista no porte atual)

- **xT / OBV / VAEP** (agentes 2, 3, 4) — exige coordenadas x/y de toda ação (passe, condução,
  drible), categoria de dado ("event stream") inteiramente diferente do box-score agregado da
  API-Football.
- **xGOT / Shooting Goals Added** (agente 2) — exige a coordenada exata de onde o chute cruzaria a
  linha do gol; não existe no box-score.
- **Expected Shot Danger (xSD)** (agente 3) — exige XY do chute por evento; a API-Football só
  entrega `shots.blocked`/`shots.on`/`shots.total` agregados por jogo, sem localização.
- **Packing Rate / SciSkill Index / SkillCorner físico-tático** (agente 2) — exige tracking de
  posição de todos os jogadores (vídeo broadcast + CV, ou chip GPS) — nenhum tier self-service
  acessível ao porte do projeto (confirmado pelo agente 7: "contact sales" em todos os provedores).
- **xG avançado com freeze-frame** (agente 2) — exige posição de goleiro/defensores no momento do
  chute; mesmo "muro de dados" que já reprovou xG simples 3x, agravado.
- **Frailty model de tempos de escanteio** (agente 1) — precisa do *timestamp* de cada escanteio
  dentro da partida; provável que `/fixtures/events` da API-Football não exponha isso com a
  granularidade necessária (verificação de código pendente, mas o agente já sinaliza "provável gap
  de dado").
- **GPS/fisiológico (Catapult/STATSports)** (agente 7) — 100% proprietário de clube, sem
  marketplace público, confirmado sem nenhum caminho de aquisição.

### Só falta engenharia de coleta (dado já acessível, endpoint já testado/usado)

- **`/injuries` de clube em massa** — o endpoint já é chamado para seleção sob demanda; falta só
  um job de backfill/cron em escala para clube (mesmo padrão de `prefetch_clubs.py`). Isso destrava
  3 candidatos diferentes (ver §2.1).
- **Standings / posição na tabela para "dead rubber"** — reconstruível do histórico de resultados
  já coletado, nem precisa do endpoint `/standings` dedicado.
- **Flag "mesma competição" / continuidade de comissão técnica** — `coach_id`/lineup já vem por
  fixture na coleta atual; é reestruturação de pipeline, não coleta nova.
- **Overround por liga** — odds já coletadas via `/api/odds/bookmakers` desde §22.
- **Bias correction segmentada, PSI, calibração Beta/Dirichlet, Purged K-Fold** — tudo reusa o
  dataset de treino/holdout já existente, zero chamada de API nova.
- **Elo por margem de gols, G-Elo, vantagem de mandante variável no tempo** — tudo derivável do
  dataset de treino atual (gols, mando, calendário).

**Conclusão desta seção:** a segunda lista é sistematicamente mais barata E mais rápida de testar
sob o gate §6 do que a primeira, mas nenhum dos 7 agentes a rankeou consistentemente acima da
primeira — a "novidade" da ideia (tracking, xT, freeze-frame) tende a soar mais impressionante do
que "rodar um cron que já existe", mesmo quando o segundo é estritamente mais acionável hoje.

---

## 4. Risco de ToS/estabilidade das fontes não-oficiais

| fonte | tipo de risco | avaliação |
|---|---|---|
| **Transfermarkt** (scraper Apify/Parse.bot) | ToS explícito não autoriza uso comercial dos dados extraídos | Risco real e direto — o ApostaInfo é um produto monetizado (créditos/assinatura), não um projeto acadêmico. Usar dado de Transfermarkt em produção (mesmo indiretamente, como feature de um modelo vendido) é uma decisão de risco de produto que deveria subir para o dono do projeto, não ser decidida só na camada de engenharia. Aceitável apenas como **piloto de pesquisa isolado e não-produtivo** (mesmo status que StatsBomb open-data hoje: "nunca em produção"). |
| **FotMob** (endpoint interno não documentado) | Sem contrato/SLA, endpoint pode mudar sem aviso | Mesmo problema estrutural do Transfermarkt, mas com um agravante: nem resolve um problema de fundo — xG já foi reprovado 3x independente da fonte (H4 fechado). Não há motivo para assumir o risco de instabilidade só para aumentar cobertura de uma feature já descartada. |
| **SofaScore** (API não-oficial) | Sem contrato, risco de bloqueio | Redundante com o que a API-Football Ultra já entrega num único fixture (statistics/events/lineups). Assumir risco de scraper para duplicar dado que já se paga por ter é um mau trade — nenhum ganho líquido. |
| **FBref / Stats Reference** (scraping HTML) | Rate limit rígido (10 req/min), risco de bloqueio de até 1 dia por violação | O mais hostil dos avaliados — 10 req/min é ~40x mais lento que o throttle atual da API-Football paga (380 req/min no modo paralelo). Inviabiliza qualquer coleta em escala; só serviria para validação pontual manual, nunca pipeline. |
| **WhoScored** (scraping) | Anti-bot Cloudflare ativo, documentado por terceiros | Mesma limitação estrutural do FBref, agravada por proteção anti-bot ativa — manutenção cara e instável, sem diferencial sobre o que já se tem. |
| **PhysioRoom** | Sem API, página editorial de conteúdo, cobertura só Premier League | Menor risco de ToS (é conteúdo público simples) mas também menor valor — cobertura de uma única liga não resolve a lacuna real (que é falta de job de coleta em massa do `/injuries` já oficial, não falta de fonte). |

**Recomendação geral de risco:** nenhuma fonte não-oficial desta lista deveria entrar em cron de
produção recorrente sem (a) avaliação jurídica explícita do ToS considerando que o produto é
comercial, e (b) plano de fallback caso o scraper quebre sem aviso — isso violaria também a regra
de ouro do projeto de manter "quase 100% API-Football" como fonte única de verdade. O único uso
defensável de qualquer uma delas hoje é como **piloto de pesquisa isolado, não-recorrente,
claramente rotulado como tal** — o mesmo tratamento que o projeto já dá a StatsBomb open-data.

---

## 5. Visão do Comitê B — candidatos mais viáveis de implementar HOJE

Priorizando baixo custo de engenharia + zero/baixo risco de dado + reaproveitamento de
infraestrutura já existente (não mérito estatístico puro — isso cabe aos outros comitês avaliar):

1. **Job de coleta `/injuries` de clube em massa** — não é "uma feature", é o pré-requisito de
   engenharia mais alavancado da lista inteira: destrava rating-por-lesão e ausência ponderada
   (parte não-Transfermarkt) com uma única mudança de infraestrutura, reusando exatamente o padrão
   de cron que já existe para outras coletas.
2. **Elo ajustado por margem de gols** (ClubElo/SPI-style) — zero dado novo, nunca testado no
   projeto, muda 1 função já existente. O candidato de menor custo/maior ineditismo de toda a
   pesquisa.
3. **G-Elo (Adjacent-Categories)** — mesma classe de baixo risco do item 2, drop-in replacement
   formal do update do Elo, sem MCMC.
4. **Calibração Beta e Dirichlet nos dois pontos onde a isotônica reprovou** (chutes, 1X2) —
   reusa 100% do pipeline de calibração já em produção; é o teste mais barato disponível para dois
   gaps já documentados e sem solução hoje.
5. **Auditoria leakage-aware de escalação point-in-time + auditoria de bias_correction sem
   segmentação** — praticamente gratuito (é leitura de código, não modelo novo) e o tipo de achado
   que pode revelar um problema real de produção sem qualquer custo de coleta.
6. **PSI de monitoramento de drift** — lacuna de processo confirmada por ausência total de
   documentação; implementação trivial, decisão real é só cadência.
7. **Overround por liga como peso de confiança no Verificador de Bets** — cálculo direto sobre
   odds já coletadas, zero dado novo, zero modelagem pesada.
8. **Flag "mesma competição" como interação explícita** (não redundante com o downweight de
   amistosos já aprovado) — 100% derivável do dataset atual, é reestruturação de pipeline de forma
   recente.

**Fora do top 8, mas vale nota separada:** o **Compound Poisson/geometric-Poisson para escanteios**
(agente 1) tem a evidência mais forte de toda a pesquisa — único candidato com backtest de dinheiro
real contra odds de mercado (Sharpe 3,07 vs 1,52) — e usa só dado já coletado. Não entra no top 8
porque é genuinamente Alta complexidade (MCMC/Stan), não porque falte dado; merece um sprint de
pesquisa dedicado, tratado como projeto à parte, não como item de backlog de engenharia rotineira.
**Clima no kickoff** é honesto o suficiente (custo trivial, ganho pequeno) para ser pilotado sem
arrependimento, mas não desloca nenhum dos 8 itens acima porque é o único deles que introduz uma
dependência de fonte externa nova, ainda que barata.

---

## Achado principal (resumo)

A pesquisa dos 7 agentes tratou "complexidade" como um único eixo e isso escondeu a distinção mais
acionável para este projeto: quase metade dos candidatos marcados "Média" na tabela mestre na
verdade se decompõe em uma parte trivial (zero dado novo, dias de trabalho, reusa pipeline
existente) e uma parte de risco real (fonte não-oficial sujeita a ToS, ou modelagem estatística
pesada tipo MCMC) — misturadas sob um único rótulo. Separando as duas, o ranking de prioridade
muda: o item mais alavancado de toda a pesquisa não é nenhuma feature nova, é um job de coleta que
falta rodar (`/injuries` de clube em massa, endpoint já usado para seleção), seguido por dois
ajustes ao Elo já em produção (margem de gols estilo ClubElo, G-Elo) e duas calibrações
paramétricas (Beta/Dirichlet) que resolvem exatamente os dois pontos onde a isotônica já reprovou
— todos com zero dado novo e reaproveitamento total da infraestrutura de gate §6 já existente. Em
contraste, as fontes não-oficiais (Transfermarkt, FotMob, SofaScore, FBref, WhoScored) carregam
risco real de ToS para um produto comercial e devem ficar restritas a pilotos de pesquisa isolados,
nunca a cron de produção, enquanto o candidato de maior evidência científica pura (Compound Poisson
para escanteios, backtest real contra odds de mercado) é legitimamente Alta complexidade — não por
falta de dado, mas por exigir um sprint de modelagem Bayesiana dedicado.
