# Comitê A — Rigor estatístico e viés — Round 1

**Data:** 2026-07-24
**Revisor:** Comitê A (1 de 3), lente de ceticismo estatístico sobre a pesquisa bruta dos 7 agentes
de domínio (`PESQUISA_VARIAVEIS_EXTERNAS.md` + `pesquisa_variaveis_raw/wave1_agente{1..7}_*.md`).
**Mandato:** redundância, confounding com Elo/força, leakage temporal, ceticismo com material de
vendor, hipóteses novas próprias, ranking rascunho. Só leitura e documentação — nenhum código
tocado.

---

## 1. Redundâncias — candidatos que deveriam virar UMA entrada no relatório final

1. **Família "rating alternativo ao Elo"** — G-Elo (Ag.1), Adaptive Glicko-2 (Ag.1), Score-driven
   GAS genérico (Ag.1, já reprovado), OpenSkill/TrueSkill (Ag.4), Bradley-Terry (Ag.4), Opta Power
   Rankings (Ag.2), SciSkill Index em nível de time (Ag.2). Todos são "substituir/generalizar o
   mecanismo de atualização de força" — a MESMA pergunta que pi-ratings, Berrar ratings e o GAS de
   Koopman já responderam negativamente neste projeto. Recomendo fundir em uma única entrada
   "sistemas de rating alternativos" no relatório final, com nota de que só 2 sub-variantes têm
   ângulo genuinamente não testado (ver item 2) — o resto é reconfirmação, não descoberta.

2. **Elo ponderado por margem de gols** — G-Elo (Ag.1, formalização Adjacent-Categories de
   Szczecinski, derivação fechada) e "Elo ajustado por margem estilo ClubElo/SPI" (Ag.4,
   heurística de engenharia sem paper). São a MESMA ideia central (parar de descartar o placar e
   tratar só W/D/L) com dois níveis de rigor diferentes. Fundir em uma entrada só: "Elo/atualização
   ponderada por margem", priorizando testar a versão G-Elo (tem derivação formal e é
   drop-in-replacement do update já em produção) em vez de reinventar a heurística ClubElo do zero.

3. **Família "posse→ameaça→valor de ação" bloqueada por dado de evento/XY** — xT (Ag.2 e Ag.3,
   literalmente repetido), OBV (Ag.2 e Ag.3, repetido de novo), VAEP (Ag.4), xGOT/SGA (Ag.2),
   Packing Rate (Ag.2), SkillCorner físico/tático (Ag.2). Todos os 6 têm o mesmo veredito idêntico:
   bloqueados por ausência de coordenadas x/y na API-Football, o mesmo "muro de dados" que já matou
   xG 3 vezes. Fundir em UMA entrada "modelos de valorização posicional/evento — bloqueados por
   dado" em vez de 6 linhas repetindo o mesmo diagnóstico. Não há necessidade de reavaliar cada um
   separadamente até que a fonte de dado mude.

4. **Família "refinamento de xG"** — xG freeze-frame (Ag.2), xGOT/SGA (Ag.2), FSAA (Ag.3, depende
   de xG por chute), xSD (Ag.3, depende de XY do chute), xG via FotMob (Ag.7). Todos herdam o
   diagnóstico "xG já reprovado 3x por muro de dados/confounding de época" — nenhum resolve a causa
   raiz (cobertura), só sofisticam a fórmula em cima de um dado que não temos em escala. Fundir numa
   entrada "refinamentos de xG" com nota clara: sofisticar a fórmula não resolve o problema, que é
   de cobertura, não de metodologia.

5. **CMP (Conway-Maxwell-Poisson) para dispersão de gols** — versão MLE estática do `goalmodel`
   (Ag.4) e versão Bayesiana hierárquica com spike-and-slab team-specific (Ag.1, arXiv:2607.18009)
   são a mesma família distribucional em dois níveis de sofisticação. Fundir como "CMP para
   dispersão de gols (MLE barato vs. Bayesiano completo)" — recomendo testar a versão barata
   primeiro como filtro de sinal antes de justificar o custo do MCMC.

6. **Família "parâmetro global deveria variar por time/período"** — Ajuste Rue-Salvesen (Ag.4),
   Home advantage específico por time (Ag.1), Prior comensurável period-specific (Ag.1). As três são
   variações de "um único parâmetro fixo (força relativa, vantagem de mandante, taxa de
   esquecimento) na verdade deveria ter um efeito aleatório por time/período". O Perfil
   Elo-condicionado (slope de resposta ao Elo) já testou exatamente esse tipo de ideia e reprovou
   por **inconsistência entre competições** — sintoma clássico de parâmetro extra sendo alimentado
   por amostra pequena por segmento. Rue-Salvesen em particular é quase literalmente a mesma forma
   funcional (encolhe a intensidade esperada em função de `elo_diff`) do Perfil Elo-condicionado.
   Recomendo tratar as 3 como uma família só no relatório final, com a mesma ressalva de risco de
   overfitting por segmento antes de qualquer teste novo (ver hipótese nova #2 abaixo).

7. **Ausência ponderada, não binária** — "Dedução de rating por lesão ponderada por status" (Ag.5,
   Kaggle, ganho medido) e "Ausência ponderada por valor de mercado do jogador" (Ag.7,
   Transfermarkt) atacam o mesmo alvo (o projeto hoje trata `/injuries` como binário) com dois pesos
   diferentes (gravidade clínica vs. valor financeiro). Não são idênticos, mas são a mesma feature-
   mãe com implementações de custo/risco muito diferentes. Fundir como "ausência ponderada por
   impacto" no relatório, com recomendação explícita de testar primeiro a variante barata
   (status clínico, já temos `/injuries`) antes da variante cara (Transfermarkt, ToS + risco de
   leakage — ver §3).

8. **De-vig / eficiência de mercado (Ag.3, linhas 3-4)** — isto **não é um candidato**, é
   confirmação externa independente de um tema já fechado em §20 (bug do `shin_devig` corrigido,
   SEM edge robusto). Recomendo que o relatório final NÃO liste isso como candidato a testar — deve
   aparecer só como nota de rodapé corroborante, senão infla artificialmente a contagem de "achados".

9. **Bayesian Network causal para Asian Handicap (Ag.1)** — o componente de rating de entrada
   (pi-rating modificado) já foi testado e reprovado; o único ângulo novo é a estrutura causal em
   cascata (posse→chutes→SOT→gols) alimentando resultado/handicap. Vale manter como candidato
   distinto da cascata chutes→escanteios→cartões já em produção (que não alimenta gols/handicap),
   mas o relatório final deveria deixar explícito que "usa pi-rating" é a parte a descartar, e a
   estrutura DAG é a parte a eventualmente testar (substituindo a entrada pelo Elo real).

---

## 2. Candidatos com confounding/viés sério — "não confiaria sem teste de embaralhamento"

- **Valor de mercado de elenco (Transfermarkt, Ag.7)** — o próprio agente já registra "fortemente
  colinear com o Elo". Isso é estruturalmente idêntico ao padrão que já matou xG 3 vezes: uma
  variável que times fortes têm mais (dinheiro para comprar craques) sem que isso adicione sinal
  causal além do que o Elo (que já mede resultado real em campo) captura. Só teria valor genuíno em
  cenários específicos onde o Elo é ruidoso por si (mata-mata cross-divisão, cross-competição) — mas
  isso precisa ser a hipótese testada explicitamente (interação com "jogo entre divisões
  diferentes"), não a feature bruta. Exijo teste de embaralhamento contra `elo_diff` antes de
  qualquer promoção, exatamente como já se faz para os proxies táticos.

- **Packing Rate (Ag.2)** — a própria fonte que valida o método (não o vendor) reporta correlação de
  **0,96 com força de equipe**. Isso não é evidência de sinal incremental, é quase uma tautologia:
  times fortes "ultrapassam" mais adversários por passe porque são fortes. Um r=0,96 com a força já
  conhecida deixa espaço estatístico mínimo para qualquer ganho ortogonal — e mesmo que a fonte de
  dado existisse (não existe), eu não promoveria isso sem ver claramente o resíduo depois de
  regredir contra Elo.

- **SciSkill Index agregado por time (soma do XI titular, Ag.2)** — descrito pelo próprio vendor como
  "versão mais elaborada do Elo". Mesmo problema categórico dos ratings já reprovados (pi-rating,
  Berrar): é força de time reempacotada. O único ângulo potencialmente não-confundido seria a
  granularidade de jogador individual (quem exatamente está em campo), mas essa fonte de dado não
  existe no projeto — teria que ser aproximada e a aproximação mais óbvia (Elo do time inteiro) já
  está em produção.

- **"Quality wins" — bônus de força de adversário em camadas (Ag.5)** — o próprio agente já sinaliza
  "risco alto de colinearidade com o Elo contínuo". Um bônus categórico por "venceu adversário forte"
  é estritamente menos informativo que o Elo contínuo que já resolve isso de forma mais fina. Baixa
  prioridade, alto risco de redundância disfarçada de sinal novo.

- **Home advantage específico por time / Rue-Salvesen / prior period-specific (item 6 da seção 1)** —
  o risco aqui não é confounding com Elo, é **overfitting mascarado de heterogeneidade real**. Times
  com poucos jogos em casa por período dão estimativas ruidosas de um parâmetro extra; a variação
  "real" reportada nos papers observacionais (ex. PMC6189255) é estudo descritivo, não um teste
  preditivo out-of-sample. O precedente direto do projeto (Perfil Elo-condicionado reprovado por
  inconsistência entre competições) é o resultado esperado para qualquer membro desta família.

- **Opta Power Rankings e qualquer claim de acurácia de rating que já misture odds de mercado** —
  ver §4, mas resumindo aqui: uma "acurácia de 60-65%" que já embute blend com odds de mercado não
  isola o que vem do rating proprietário vs. o que vem do mercado. Comparar isso contra o DC-NB de
  produção seria comparar maçã com salada de fruta.

- **FSAA adaptado ao proxy de finalizações, se implementado sem cuidado** — não é confounding com
  Elo, mas há um paper citado pelo próprio Agente 1 (arXiv:2401.09940, "vieses em modelos de xG
  confundindo finishing ability") que documenta exatamente o risco de o "acima da média em
  finalização" ser artefato de qualidade de chance mal controlada, não habilidade real. Se testado,
  precisa de controle explícito para qualidade de oportunidade, não só volume de chutes.

---

## 3. Riscos de leakage temporal identificados

- **Valor de mercado de elenco / ausência ponderada por valor (Transfermarkt, Ag.7)** — risco real
  se o scraper capturar o "valor atual" do jogador (que é atualizado retroativamente conforme
  desempenho recente/transferências) e aplicar esse valor a jogos passados. Precisa de série
  histórica de avaliação com data, não snapshot corrente aplicado ao passado. Isso é estruturalmente
  o mesmo tipo de erro que o projeto já corrigiu no vazamento de calendário do Brasileirão (§20) —
  vale tratar com a mesma seriedade antes de qualquer teste.

- **Ausência/lesão "Sidelined" do Transfermarkt** — se a feature usar a duração final da lesão (só
  conhecida depois que o jogador volta), há vazamento indireto do futuro. Só o status conhecido *na
  data do jogo* (fora/dúvida/confirmado) pode entrar — igual ao cuidado que já existe com o
  `/injuries` da API-Football, mas o histórico de "Sidelined" do Transfermarkt tem motivo real para
  ser mais malicioso aqui porque é apresentado como registro retrospectivo completo.

- **Flag de continuidade de comissão técnica (Ag.5)** — se `coach_id` for lido de uma página de
  elenco "atual" em vez de reconstruído partida a partida a partir do lineup histórico, a flag
  "mesmo treinador" pode refletir o técnico no momento da coleta, não no momento do jogo histórico —
  um erro sutil de rotulagem retroativa, não um vazamento do resultado em si, mas com efeito
  parecido (inflar artificialmente a "continuidade" de times que trocaram de técnico recentemente).

- **Workflow leakage-aware de mercados secundários (Ag.6, LaLiga 2026)** — o achado mais acionável
  aqui não é um novo vazamento confirmado, é um **vetor específico ainda não auditado**: o paper
  usa "agregação lineup-aware" que só considera escalação quando ela é conhecida antes do corte
  **de cada partida individualmente**, não só antes da data do jogo. Se o projeto usa escalação como
  feature em algum mercado (ex. via `/injuries`/lineup), vale confirmar que o corte respeita a hora
  de publicação da escalação (tipicamente ~1h antes do apito), não só a data — um vazamento de
  "mesmo dia" é mais difícil de pegar que um vazamento de calendário grosseiro.

- **Blend Bayesiano modelo+odds como input generativo (Ag.1)** — não é leakage temporal clássico
  (a odds pré-jogo é point-in-time válida), mas é um risco de **circularidade metodológica**
  adjacente: se o modelo de gols passar a consumir a odds como insumo e o detector de valor (§22)
  compara a saída do modelo contra a mesma odds, o "sinal de valor" reportado ao usuário fica
  mecanicamente comprimido por construção — o modelo aprende a concordar com o mercado que está
  sendo usado para julgá-lo. Qualquer teste desta ideia precisa isolar o pipeline de treino do
  pipeline de detecção de valor com uma fronteira de dados explícita (odds de treino ≠ odds
  usadas no comparador de EV em produção).

- **Fontes de xG scraped não-oficiais (FotMob/SofaScore/Understat)** — risco secundário, baixa
  probabilidade mas vale nota: providers de xG às vezes revisam retroativamente seus modelos de xG
  (recalibração do próprio vendor). Se o scraping capturar o valor "atual" (pós-revisão) para jogos
  antigos, isso é uma forma sutil de vazamento de informação-do-futuro-do-modelo-do-vendor. Só
  relevante se o projeto decidir perseguir essas fontes — o que, dado o "muro de dados" já
  documentado, não recomendamos como prioridade.

---

## 4. Credibilidade por fonte — aplicada aos candidatos mais duvidosos

**Hierarquia adotada** (da mais para a menos confiável):
1. Paper peer-reviewed com backtest contra dado real de mercado/dinheiro real.
2. Paper peer-reviewed/preprint sem backtest de mercado, mas com validação estatística honesta
   (inclusive quando o resultado é "perde para o mercado" — isso é sinal de honestidade, não de
   fraqueza).
3. Estudo acadêmico terceiro que analisa/valida um produto de vendor (não é o vendor falando de si).
4. Write-up de competição (Kaggle) — trata-se de evidência empírica em escala, mas com um viés
   metodológico confirmado nesta própria pesquisa (ver abaixo) que exige desconto.
5. Blog técnico de praticante reconhecido, com dado real e metodologia transparente (mesmo sem
   peer-review).
6. Claim do próprio vendor sobre o próprio produto, sem validação externa.

Aplicando aos casos mais espinhosos que o Agente 2 trouxe:

- **SciSkill ROI de 9,4% (SciSports)** — **rejeitaria como evidência.** É tier 6 (claim do vendor
  sobre o próprio produto). Não há período/amostra/metodologia de backtest divulgados, há risco de
  seleção do melhor resultado para publicidade, e o "paper" citado ao lado (arXiv:2502.07528) é
  sobre *previsão da evolução do próprio índice*, não validação independente do poder preditivo de
  resultado. Não dá para saber se 9,4% é sobre uma amostra de 50 jogos ou 5000, nem contra qual
  baseline. Tratar como zero peso em qualquer ranking.

- **Opta Power Rankings, 60-65% de acurácia (Stats Perform)** — **rejeitaria como evidência de
  mérito do rating em si**, por dois motivos simultâneos: (1) é tier 6, claim do vendor; (2) o
  próprio texto do vendor admite que o número é "combinado com odds de mercado" — ou seja, mesmo se
  o número fosse honesto, não isola o que vem do Elo hierárquico próprio vs. o que vem do blend com
  mercado. O projeto já tem evidência direta e muito mais forte contra isso: comparação nosso-modelo
  vs. `/predictions` nativo da API-Football em 8117 jogos (§21), nosso modelo vence em 26/26
  competições. Não há motivo para dar crédito a um número de marketing quando já existe um
  benchmark interno superior sobre essencialmente o mesmo tipo de produto.

- **Packing Rate, correlação 0,96 (fonte que "analisa", arXiv indexado)** — **aceitaria o número
  como fato mensurado** (é tier 3, fonte que analisa o método, não o vendor Impect falando de si),
  mas rejeitaria a implicação de que isso é "candidato promissor" — na verdade a correlação alta é
  evidência CONTRA valor incremental (ver §2). A fonte é confiável; a inferência que o índice mestre
  fez a partir dela ("nota-chave: correlação 0,96... exige tracking x/y") já está correta em
  reconhecer o bloqueio de dado, mas eu adicionaria que mesmo com o dado disponível, o r=0,96 por si
  seria motivo para ceticismo, não só o custo de aquisição.

- **Adaptive Glicko-2, +4,04% Brier vs. Glicko-2 padrão, mas 1-3% atrás do mercado (Ag.1,
  arXiv:2607.01722)** — **aceitaria com confiança média-alta.** É tier 2 (peer-review, sem backtest
  de mercado real, mas honesto sobre perder para odds implícitas) — o padrão de "admite que perde
  para o mercado" é exatamente o tipo de honestidade que aumenta credibilidade nesta hierarquia,
  simétrico ao motivo pelo qual aceito o paper de blend Bayesiano (também admite perder em acurácia
  pura).

- **Compound Poisson para escanteios, Sharpe 3,07 vs 1,52 (Ag.1, arXiv:2112.13001)** — **aceitaria
  como a evidência mais forte de todo o levantamento.** É tier 1 — backtest com dinheiro real contra
  odds reais da HKJC, não é log-loss acadêmico isolado. É o único candidato de todo o material com
  esse nível de prova. Ainda assim, adiciono uma ressalva de rigor: o gate §6 do projeto exige CV
  temporal expanding e o paper não deixa claro se o backtest 2016-2021 usou uma metodologia de
  validação equivalente (point-in-time estrito) — vale re-verificar a seção de validação do paper
  antes de tratar o Sharpe como garantido.

- **1º lugar Kaggle "Football Match Probability Prediction" — features "A-Z", ganho de bloco
  ~0,001 log-loss (Ag.5)** — **aceitaria com desconto significativo (tier 4 rebaixado).** Dois
  problemas: (a) o ganho é de um bloco de 6+ features, não isolado — não dá para saber se a feature
  específica de interesse (ex. "mesma competição × mando de campo") contribui 90% ou 5% do ganho;
  (b) o próprio Agente 5 descobriu que o desenvolvimento interno de features desta solução usou
  **KFold aleatório**, não CV temporal — exatamente o viés metodológico que o gate §6 do projeto foi
  desenhado para evitar (e que já produziu um falso-positivo real aqui, o achado de forma de
  jogador). Qualquer feature originada desta fonte precisa entrar no gate §6 completo sem
  atalho, tratando o "ganho" reportado como hipótese a testar, não como evidência pré-validada.

- **Martin Eastwood (penaltyblog) — de-vig em 250M linhas, FSAA com shrinkage bayesiano** —
  **aceitaria com confiança alta para tier 5.** Autor de referência citado recorrentemente na
  curadoria anual do campo (Jan Van Haaren), metodologia declarada e replicável (multilevel Bayesian
  logistic regression, r_hat<1.01 documentado), resultados batem com senso comum de scout. Não é
  peer-review, mas a transparência metodológica e o tamanho de amostra (250M linhas) compensam boa
  parte da distância para tier 1-2.

---

## 5. Hipóteses estatísticas novas (síntese cruzada, não explícitas em nenhum agente isolado)

1. **O "muro de dados" é uma categoria, não um caso isolado de xG.** Lendo os 7 agentes juntos, pelo
   menos 4 domínios (Empresas, Blogs, Open source, e indiretamente Papers) convergem
   independentemente no mesmo bloqueio: qualquer variável que dependa de coordenadas x/y de evento
   (xT, OBV, VAEP, Packing, xGOT, SkillCorner) é categoricamente inacessível pela API-Football, não
   "difícil" — é um bloqueio binário de disponibilidade. Proponho formalizar isso como um **filtro
   de triagem rápido** para pesquisas futuras: antes de aprofundar qualquer candidato novo, checar
   em 1 pergunta "isso precisa de posição x/y de jogador/bola em algum momento do pipeline?" — se
   sim, descartar sem gastar mais tempo de pesquisa, a menos que uma fonte de tracking realmente
   nova apareça (o que o Agente 7 já checou e não achou nenhuma acessível ao porte do projeto).

2. **A família "parâmetro global deveria ser específico por time/período" provavelmente está
   estruturalmente limitada pelo volume de dado por segmento, não pela escolha de QUAL parâmetro
   generalizar.** O Perfil Elo-condicionado (slope) já falhou por inconsistência entre competições —
   um sintoma clássico de estimativa ruidosa por segmento pequeno. Antes de testar Rue-Salvesen,
   home-advantage-por-time ou o prior comensurável period-specific (item 6 da seção 1) do zero,
   recomendo uma análise de poder estatístico genérica primeiro: dado o número médio de jogos por
   time por competição por temporada no dataset atual, qual é o erro-padrão esperado de QUALQUER
   parâmetro adicional nesse nível de granularidade, sob o ruído real de margem de gols do esporte?
   Se o erro-padrão for da mesma ordem do "sinal" que os papers observacionais relatam, isso prediz
   o fracasso de toda a família sem precisar rodar cada variante separadamente — economiza ciclos de
   pesquisa reais.

3. **As claims de acurácia de vendor convergem numa faixa estreita (~60-65%) que provavelmente é um
   teto alcançável por qualquer modelo razoável nesse tipo de dado, não uma prova de mérito
   específico do método proprietário.** Opta Power Rankings (60-65%), estudo acadêmico de tracking
   holandês sobre KPIs off-ball (64,0%), pi-rating+CatBoost de blog (55,82%) — a proximidade desses
   números, combinada com o fato de que o próprio modelo do projeto já vence o produto nativo da
   API-Football em 26/26 competições (§21) usando só box-score agregado, sugere que essa faixa é
   mais uma "cota de dificuldade intrínseca do problema" do que evidência de que xT/tracking/rating
   proprietário adiciona sinal incremental real. Vale documentar essa faixa como referência de "teto
   de sanidade" para julgar futuros claims de vendor sem precisar re-analisar cada um do zero.

4. **Dispersão de odds entre casas de apostas (cross-bookmaker), não só o overround médio de uma
   liga, pode ser uma feature de incerteza de partida ainda não explorada.** O Agente 3 traz
   overround por liga como proxy de eficiência de mercado (nível liga); o Agente 1 traz blend
   Bayesiano modelo+odds (nível ponto único). Nenhum dos dois propõe usar a **variância entre casas
   para o MESMO jogo** (já disponível via `{,club_}odds_bookmaker_latest`, §22) como sinal de
   incerteza específico daquela partida — jogos onde as casas discordam mais entre si podem ser
   sistematicamente mais difíceis de precificar (elenco desfalcado, mudança recente de técnico,
   informação assimétrica), o que poderia alimentar não um preditor de resultado, mas um multiplicador
   de incerteza/intervalo de confiança na saída do modelo, sem risco de circularidade porque não
   entra como insumo do DC-NB, só da camada de calibração/apresentação.

5. **O padrão "sinal em nível de jogador bate sinal em nível de time" pode não ser sobre qual
   métrica (forma, habilidade, posicionamento), e sim sobre o que o Elo por-time estruturalmente não
   consegue enxergar: mudança de escalação entre partidas.** Momentum de jogador passou (AUC
   0,68→0,71) onde momentum de time reprovou; FSAA, SciSkill e Packing Rate são todos agregados de
   jogador (mesmo que hoje inacessíveis por dado). Isso sugere uma hipótese testável e nova, não
   levantada por nenhum agente: uma feature de **"distância entre a escalação confirmada desta
   partida e a escalação histórica média que gerou o Elo atual do time"** (ex.: quantos titulares
   habituais estão ausentes, ponderado por minutos jogados recentes de cada um) capturaria o mesmo
   tipo de informação de nível-de-jogador que já demonstrou funcionar, sem precisar de rating de
   jogador externo — usando só lineup + histórico de minutagem já potencialmente acessível via
   API-Football. Diferente de "ausência ponderada por lesão" (que é sobre o motivo da ausência),
   esta feature seria sobre o efeito agregado de qualquer ausência (lesão, suspensão, rotação,
   opção técnica) na composição do time em campo.

6. **Risco de "retestar a mesma ideia travestida de nova" é real e crescente conforme a pesquisa
   externa se aprofunda — recomendo um filtro de similaridade antes de qualquer implementação.**
   Vários candidatos (CMP, GAS, Rue-Salvesen, prior comensurável) são matematicamente próximos de
   hipóteses já reprovadas. Proponho, como processo (não como candidato de feature): antes de
   implementar qualquer candidato da família "generalização de algo já testado", rodar um teste
   barato de correlação entre as predições do candidato novo e as predições do modelo antigo já
   reprovado, numa amostra pequena — se a correlação for muito alta (>0,98), é a mesma ideia com
   roupagem nova e não justifica o custo de um teste completo sob gate §6.

7. **O efeito de clima pode estar sendo subestimado pela própria forma como será testado, não
   por ser realmente nulo.** O Agente 7 já assume "ganho esperado pequeno" para clima, citando que o
   efeito é historicamente fraco *em média*. Mas se o teste seguir o padrão do projeto (delta médio
   agregado sob CV temporal), um efeito real e forte, porém raro (jogos de neve/tempestade), seria
   diluído pela maioria esmagadora de jogos com clima ameno e reprovado no agregado — o mesmo padrão
   de falha que já aconteceu com a dispersão dinâmica de escanteios (passou em log-loss agregado,
   reprovou em Tail-ECE). Se esse candidato for testado, recomendo segmentar explicitamente por
   percentil de severidade climática (ex. top 5% de precipitação/vento), não só olhar o delta médio
   full-sample — outro caso onde a métrica de gate precisa ser ajustada ao tipo de efeito esperado
   antes de descartar.

---

## 6. Ranking rascunho — top 8-10 candidatos a testar primeiro (lente de rigor/viés, não de facilidade)

Critério: prioriza candidatos com (a) mecanismo estatístico genuinamente distinto do que já foi
testado, (b) baixo risco de confounding com Elo/força já capturada, (c) evidência de fonte
confiável (tier 1-4), (d) dado já disponível ou barato/sem risco de ToS/leakage.

1. **G-Elo / Elo ponderado por margem de gols** (fusão dos itens 2 da seção 1) — derivação formal,
   drop-in no update já em produção, zero dado novo, zero overlap direto com o que já foi reprovado.
   Menor risco de todo o conjunto.
2. **Calibração Beta e Dirichlet** (Ag.6) — ataca diretamente os dois pontos documentados onde a
   isotônica falhou (chutes, 1X2), mecanismo claramente distinto (paramétrico vs. não-paramétrico),
   zero dado novo, complexidade baixa.
3. **CMP (barato, MLE) para dispersão de gols** — testar a versão simples do `goalmodel` primeiro
   como filtro antes de justificar a versão Bayesiana completa; cobre sub-dispersão que a NB de
   produção estruturalmente não cobre — mecanismo novo de verdade, não reempacotamento de rating.
4. **Ausência ponderada por status de lesão (via `/injuries` já coletado)** — ganho medido e
   replicado por 2 competidores independentes numa fonte tier 4, dado já em mãos, sem risco de ToS
   ou leakage se implementado com cuidado de point-in-time.
5. **Bias correction segmentado por liga/mercado** — não é uma "hipótese de sinal novo", é correção
   de uma lacuna de processo confirmada por leitura direta de código (não é claim de terceiro) — 72
   torneios heterogêneos compartilhando uma correção global é implausível a priori.
6. **Auditoria leakage-aware da cascata chutes→escanteios→cartões (lineup-aware cut, Ag.6)** —
   prioridade alta não por ser "descoberta", mas porque é o tipo exato de vetor de leakage fino que
   já mordeu o projeto duas vezes (calendário, CV aleatória); custo de auditoria é baixo comparado
   ao risco.
7. **PSI para monitoramento de drift** — mesma lógica: lacuna de processo confirmada, protege contra
   degradação silenciosa do `bias_correction` já em produção, custo baixo.
8. **Compound Poisson / geometric-Poisson para escanteios com regressão no parâmetro de forma** —
   a evidência mais forte de todo o levantamento (Sharpe real contra odds reais), mas entra depois
   dos itens acima porque é adjacente a uma hipótese já reprovada (dispersão dinâmica/Tail-ECE) e
   exige cuidado explícito para mostrar que ataca o mecanismo de forma diferente (rajadas/cluster,
   não suavização contínua) antes de comprometer o esforço de implementação (MCMC/Stan).
9. **Dispersão de odds cross-bookmaker como feature de incerteza** (hipótese nova #4, seção 5) —
   dado já coletado (§22), sem risco de circularidade se usado só na camada de calibração/exibição,
   mecanismo genuinamente não testado no projeto.
10. **Distância escalação-confirmada vs. escalação-histórica-média** (hipótese nova #5, seção 5) —
    é a entrada mais especulativa do ranking (não testada por nenhum agente, precisa de design antes
    de ser "pronta para testar"), mas motivada por um padrão real e repetido no histórico do projeto
    (sinal de jogador > sinal de time) e não depende de nenhuma fonte de dado nova.

**Fora do top 10 por decisão explícita, apesar de aparecerem como "achado forte" no índice mestre:**
valor de mercado de elenco (confounding com Elo não resolvido, risco de leakage se mal implementado),
Packing Rate/SciSkill/Opta Power Rankings (confounding com força já demonstrado pela própria fonte
ou blend com mercado não isolado), qualquer variante de "parâmetro global vira específico por
time/período" sem antes fazer a análise de poder estatístico da hipótese nova #2.

---

## Resumo executivo (3-5 frases)

O achado mais importante deste round é que boa parte do material dos 7 agentes se reduz, sob lente
de rigor, a **3 padrões recorrentes já conhecidos pelo projeto**: (1) qualquer coisa que exija
coordenadas x/y de evento é categoricamente bloqueada pela API-Football — o mesmo muro que já matou
xG 3 vezes, não um problema novo por domínio; (2) qualquer rating "alternativo" ao Elo (SciSkill,
Opta Power Rankings, Packing Rate, OpenSkill) tende a ser Elo/força-de-time reempacotado, com
correlações declaradas de até 0,96 com força já conhecida — confounding, não sinal ortogonal; e (3)
qualquer "parâmetro global deveria variar por time/período" (Rue-Salvesen, home-advantage-por-time,
prior period-specific) provavelmente esbarra no mesmo limite de amostra por segmento que já
reprovou o Perfil Elo-condicionado. As claims de vendor mais quantificadas (SciSkill ROI 9,4%, Opta
60-65%) devem ser tratadas como marketing sem peso probatório — a segunda, em particular, já mistura
odds de mercado, então nem isola o que estaria sendo vendido. Os candidatos que sobrevivem ao
ceticismo são majoritariamente de baixo glamour: ajuste formal do Elo por margem (G-Elo), calibração
paramétrica nos dois pontos onde a isotônica já reprovou, correção de viés segmentada e auditoria de
leakage — nenhum promete um salto grande, mas todos têm mecanismo genuinamente distinto e evidência
que não depende de confiar em vendor.
