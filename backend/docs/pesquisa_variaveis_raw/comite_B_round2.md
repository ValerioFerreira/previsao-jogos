# Comitê B — Viabilidade de dados e engenharia — Round 2

**Data:** 2026-07-24
**Insumos:** `comite_A_round1.md` (rigor estatístico/viés), `comite_C_round1.md`
(estratégia/originalidade/roadmap), confrontados contra `comite_B_round1.md` (esta cadeira).
**Mandato deste round:** para cada ponto de convergência/divergência com A e C, decidir
explicitamente (a) concordo e incorporo, (b) discordo e explico por quê — em viabilidade/
engenharia, não preferência —, ou (c) fica em aberto (divergência de fato, não de julgamento).
Só revisão e documentação, nenhum código tocado.

---

## 1. Pontos em confronto com o Comitê A (rigor estatístico/viés)

### 1.1 Fusões de família (redundância) — item 1-9 da seção 1 do Comitê A

**(a) Concordo e incorporo.** O Comitê A tem razão em fundir "rating alternativo ao Elo" (G-Elo,
Adaptive Glicko-2, OpenSkill, Bradley-Terry, Opta Power Rankings, SciSkill agregado por time) numa
única entrada, e em separar "Elo ponderado por margem" (G-Elo formal + heurística ClubElo/SPI) como
subfamília distinta. Isso não muda minha reclassificação de complexidade (G-Elo e Elo-por-margem
continuam categoria **A** — zero dado novo, engenharia trivial), mas muda a *contagem* de itens
independentes no relatório final: o que eu tratei como 2 linhas separadas (G-Elo vs. Elo-margem
heurístico) deveria aparecer como 1 candidato com 2 implementações possíveis, priorizando a versão
G-Elo (derivação formal) sobre a heurística ClubElo, exatamente como o Comitê A recomenda. Incorporo
essa fusão na minha priorização final.

### 1.2 Rejeição por confounding de valor de mercado, Packing Rate, SciSkill — pergunta do
coordenador: isso muda minha priorização de viabilidade?

**(a) Concordo, e o efeito é reforçar (não contradizer) minha classificação, com uma ressalva.**

- **Packing Rate e SciSkill Index**: já estavam na minha categoria **F** (bloqueado por ausência
  real de dado — exige tracking x/y ou rating proprietário de jogador que não temos). O argumento de
  confounding do Comitê A (r=0,96 com força de equipe é quase tautológico, "versão mais elaborada do
  Elo") não muda a classificação de viabilidade — já eram inviáveis por falta de fonte — mas
  **fortalece a razão de exclusão**: mesmo que a fonte de dado aparecesse amanhã (ex. parceria com
  Impect/SciSports), o argumento estatístico do Comitê A já preveniria que a equipe gastasse um ciclo
  de gate nisso. Concordo em tratar como duplamente descartado (dado + confounding), não apenas
  bloqueado por dado.
- **Valor de mercado de elenco (Transfermarkt)**: aqui a reclassificação do Comitê A tem peso real
  sobre minha priorização. Eu já havia classificado como categoria **E** (fonte não-oficial, risco
  de ToS) e não o incluí no meu top 8. O Comitê A adiciona um segundo motivo independente de baixa
  prioridade (confounding não resolvido com Elo) mais um risco de leakage temporal concreto que eu
  não havia detalhado (valor de mercado é retroativamente revisado — precisa de série histórica com
  data, não snapshot corrente aplicado ao passado). **Isso não muda meu ranking** (já estava fora do
  top 8 por risco de ToS sozinho), mas muda a *natureza* da recomendação: antes eu diria "pode valer
  como piloto de pesquisa isolado, com ressalva de ToS"; agora, com confounding E leakage somados ao
  risco de ToS, a recomendação correta é não alocar esforço de piloto nisso a menos que o desenho do
  experimento seja explicitamente escopado a um recorte onde o Elo é estruturalmente fraco (ver §2.6
  sobre H5 do Comitê C) — três razões independentes convergindo é mais forte do que qualquer uma
  isolada.

**Ressalva (não é discordância, é nuance de mandato):** meu mandato é viabilidade/engenharia, não
mérito estatístico — não tenho posição própria sobre se r=0,96 é "quase tautológico" (isso é
julgamento de rigor, terreno do Comitê A). O que posso confirmar do lado de engenharia é que a
classificação de risco de fonte (E) já era suficiente, por si só, para manter esses candidatos fora
do meu top 8 — a convergência com o argumento de confounding só reforça a decisão, não a origina.

### 1.3 Riscos de leakage temporal (seção 3 do Comitê A) — coach_id, Sidelined, escalação lineup-aware

**(a) Concordo e incorporo integralmente.** Os quatro riscos que o Comitê A lista (valor de mercado
retroativo, "Sidelined" do Transfermarkt sem corte point-in-time, `coach_id` lido de página "atual"
em vez de reconstruído partida a partida, e o vetor fino do workflow leakage-aware sobre hora de
publicação de escalação) são exatamente do tipo que minha auditoria de código (item A da minha
tabela round 1, "workflow leakage-aware — auditoria de escalação point-in-time") deveria cobrir.
Incorporo os 4 riscos específicos como itens de checklist dentro dessa auditoria, que já estava no
meu top 8. Isso não muda a classificação de complexidade (continua **A** — é leitura de código, não
modelo novo) mas amplia o escopo do que a auditoria precisa checar.

### 1.4 Hierarquia de credibilidade por fonte (seção 4 do Comitê A)

**(c) Fica em aberto quanto à aplicação prática, mas sem divergência de julgamento.** Concordo com a
hierarquia de tiers proposta (peer-review com backtest > peer-review sem backtest > estudo terceiro
> Kaggle com desconto > blog transparente > claim de vendor). Isso é fora do meu mandato de
viabilidade — é avaliação de qualidade de evidência, terreno do Comitê A. Não tenho base para
concordar ou discordar do posicionamento específico de cada fonte nos tiers; sinalizo como aberto
porque decidir isso não é uma pergunta de "dá pra construir", é uma pergunta de "devemos confiar no
número reportado", que pertence a outro comitê.

### 1.5 Hipótese nova #2 do Comitê A — família "parâmetro global→específico" limitada por poder
estatístico, não pela escolha do parâmetro

**(a) Concordo e isso rebaixa minha classificação de "vantagem de mandante variável no tempo".** No
meu round 1, classifiquei esse candidato como **A/B** (zero dado novo, mas desenho estatístico real
— decidir forma funcional). O argumento do Comitê A (erro-padrão de qualquer parâmetro adicional
nesse nível de granularidade provavelmente é da mesma ordem do "sinal" relatado, dado o volume de
jogos por time por competição por temporada) é um argumento de viabilidade estatística que eu não
tinha considerado — e ele muda a prioridade prática: antes de gastar o esforço de desenho (a parte
**B** do meu B), vale rodar a análise de poder estatístico genérica que o Comitê A propõe como
gate de entrada. Incorporo essa ordem de execução: análise de poder primeiro (barata, quase
diagnóstico puro), desenho completo só se o poder for suficiente. Isso não muda a categoria de dado
(continua zero fonte nova) mas rebaixa a prioridade prática do item no meu ranking de "vale
implementar logo" para "vale primeiro descartar por poder estatístico antes de comprometer esforço".

### 1.6 Hipótese nova #4 do Comitê A — dispersão de odds cross-bookmaker como feature de incerteza

**(a) Concordo e incorporo como adição à minha combinação #5** (infraestrutura de odds
já coletada). É um candidato genuinamente barato sob minha lente: reusa 100% a tabela
`{,club_}odds_bookmaker_latest` já em produção, zero chamada de API nova, e o próprio Comitê A já
endereça o risco de circularidade (não entra como insumo do DC-NB, só da camada de
calibração/apresentação) — o que é exatamente o tipo de fronteira de dados que eu recomendaria do
ponto de vista de engenharia para evitar o problema de circularidade que também sinalizei no meu
round 1 sobre o blend Bayesiano modelo+odds. Reclassifico como categoria **A** e adiciono ao pool de
candidatos de baixo custo, ao lado de "overround por liga".

### 1.7 Hipótese nova #5 do Comitê A e H1/C4 do Comitê C — "distância entre escalação confirmada e
escalação histórica" / momentum de jogador agregado no DC-NB — pergunta explícita do coordenador

Trato esta pergunta em conjunto no §3 abaixo, porque o Comitê A (hipótese #5) e o Comitê C (H1 e C4)
convergem no mesmo território (granularidade de jogador → feature de time) por três caminhos
ligeiramente diferentes, e a resposta de viabilidade é a mesma para os três.

### 1.8 Hipótese nova #7 do Comitê A — clima pode estar sendo subestimado pela métrica de gate
agregada (efeito raro e forte diluído pela média)

**(a) Concordo e incorporo como refinamento do desenho de teste, sem mudar a classificação de
dado.** Continuo classificando clima como categoria **D** (fonte externa nova, barata) — isso não
muda. O que muda é a recomendação de *como testar*: segmentar por percentil de severidade
(top 5% de precipitação/vento) em vez de olhar só o delta médio full-sample, no mesmo espírito do
que já aconteceu com a dispersão dinâmica de escanteios (passou em log-loss agregado, reprovou em
Tail-ECE). Isso é uma correção de metodologia de teste, não de custo/complexidade de engenharia —
mantenho clima fora do meu top 8 principal (ganho esperado pequeno mesmo com o teste corrigido), mas
incorporo a ressalva para quem for desenhar o piloto.

### 1.9 Ranking rascunho do Comitê A (seção 6) vs. meu top 8

**(a) Concordo com 6 dos 8 itens do Comitê A** (G-Elo/Elo-margem, Beta/Dirichlet, ausência ponderada
por status, bias correction segmentada, auditoria leakage-aware, PSI) — são exatamente os mesmos 6
do meu próprio top 8, o que é convergência forte de dois mandatos diferentes (rigor e viabilidade)
chegando ao mesmo lugar por caminhos distintos. **Diferença de ênfase, não de fato:** o Comitê A
inclui CMP (barato/MLE) no lugar de "overround por liga" e "flag mesma competição" que eu tinha; do
lado de viabilidade, CMP-MLE é razoável (é a versão barata da família CMP, categoria **A/B** — sem
dado novo, mas precisa de otimização numérica iterativa, mais pesado que uma regressão logística
simples) mas ainda assim mais caro de implementar/validar que overround-por-liga ou a flag de
interação, que são triviais. **(c) Fica em aberto** se CMP-MLE deveria substituir um dos meus itens
mais baratos no top 8 conjunto do relatório final — isso depende de quanto peso o comitê dá a
"mecanismo estatístico novo" (critério do Comitê A) vs. "menor custo de implementação" (meu
critério); não é uma divergência de fato, é uma escolha de critério de corte que cabe à síntese
final, não a mim resolver sozinho.

---

## 2. Pontos em confronto com o Comitê C (estratégia/roadmap)

### 2.1 C1 — Rating unificado (margem de gols + ausência ponderada) testado como pacote único

**(b) Discordo parcialmente do desenho de teste, não do candidato em si.** Do ponto de vista de
engenharia/viabilidade, testar os dois efeitos (atualização do Elo por margem + penalidade de
ausência pré-jogo) como um único "pacote" desde o início tem um risco real: se o pacote passar no
gate mas um dos dois componentes for neutro/negativo isoladamente, fica mais caro reverter depois
(o pacote já está em produção, a decomposição vira trabalho extra). O próprio Comitê C já prescreve
a ablation de 4 variantes antes de promover — nesse ponto específico não há divergência de fato,
só quero deixar explícito, pela lente de engenharia, que a ordem correta é **testar isolado primeiro,
combinar depois só se ambos passarem isolados** (o que é exatamente minha combinação #6 do round 1
para o Elo por margem + a combinação #1 para ausência), não desenhar o experimento já como pacote
combinado desde o primeiro teste. Then, se ambos passarem isolados, aí sim testar a combinação para
capturar efeito conjunto. É uma diferença de sequenciamento de engenharia, não de mérito do
candidato — mas vale registrar porque o texto do Comitê C descreve o teste combinado como o
experimento principal e a decomposição como plano B, e eu inverteria essa ordem.

### 2.2 C2 — Calibração segmentada por liga + overround como peso de confiança

**(a) Concordo e incorporo — é uma síntese melhor do que eu tinha isoladamente.** No meu round 1,
tratei "bias correction segmentada" (categoria **B**) e "overround por liga" (categoria **A**) como
itens separados na minha combinação #5 (reuso de infraestrutura de odds), sem propor usá-los
JUNTOS como mecanismo de shrinkage. A ideia do Comitê C — overround da liga como peso de quanto
confiar na curva local vs. a curva global — é uma aplicação de engenharia concreta e barata (é só
mais um termo de ponderação sobre um cálculo que já faço) que resolve exatamente o risco que eu
mesmo sinalizei para a versão B pura ("precisa de shrinkage por volume para não recriar o overfit da
isotônica em amostra pequena"). Incorporo: a versão combinada C2 é estritamente melhor que testar os
dois separadamente, e ainda é zero dado novo — mantenho como categoria **B** (mesma complexidade
estatística que eu já tinha, mas com desenho mais defensável).

### 2.3 C3 — Cascata causal estendida (posse→chutes→escanteios→cartões→gols)

**(b) Discordo em um ponto de engenharia específico, que o próprio Comitê C já sinaliza mas
subestima o custo.** O Comitê C corretamente nota que "posse" não pode ser a posse do próprio jogo
(dado pós-jogo) — precisa ser posse histórica/média do time. Concordo com essa correção. Mas isso
muda a classificação de complexidade: não é mais **A** (zero dado novo, trivial) como a estrutura
causal poderia sugerir à primeira vista — é **B**, porque "posse histórica" como insumo de um nó de
uma rede causal é uma agregação nova (janela de quantos jogos? decaimento? por competição?) que
precisa ser desenhada e teria o mesmo tipo de decisão de design que "vantagem de mandante variável
no tempo" (§1.5) — não é dado bloqueado, mas também não é "só rodar o número que já existe". Concordo
com a ordem proposta pelo Comitê C (auditoria de leakage primeiro, extensão da cascata depois), mas
quero deixar registrado que a segunda etapa é mais cara em engenharia do que "reformulação natural
da arquitetura" sugere.

### 2.4 C4 — Índice de qualidade do XI titular (FSAA adaptado) e H1 — momentum de jogador agregado no
DC-NB de gols: pergunta explícita do coordenador

Trato junto com a hipótese #5 do Comitê A no §3 abaixo — os três (C4, H1, hipótese-A-#5) convergem no
mesmo bloqueio de engenharia real.

### 2.5 H2, H3 — diagnóstico primeiro, implementação depois

**(a) Concordo integralmente com ambos.** H2 (testar Dirichlet no 1X2 antes de aceitar "isotônica
reprovou = DC-NB já calibrado" como conclusão definitiva) e H3 (comparar ECE das competições novas
da expansão 2026 vs. antigas antes de implementar segmentação completa do bias_correction) são
exatamente o tipo de "gasta pouco, decide se vale gastar muito" que eu recomendaria pela lente de
engenharia. H3 em particular é uma boa refinamento do meu item de auditoria — adiciona um critério
objetivo de decisão (comparar ECE por safra de competição) em vez de "provavelmente ajuda mais em
clube". Incorporo H3 como parte explícita da fase de diagnóstico da minha combinação #3 (gate §6).

### 2.6 H4 — Choque de regime discreto (técnico novo, não decaimento contínuo)

**(a) Concordo com a versão piloto, mantenho minha classificação.** A versão piloto (só flag de
troca de técnico) já estava na minha lista como categoria **A** ("flag de continuidade de comissão
técnica", agente 5) — zero dado novo, `coach_id` já vem via lineup. A versão completa (+ atividade de
transferência via valor de mercado) herda a categoria **E** (risco de ToS do Transfermarkt) que já
apliquei a qualquer candidato dependente dessa fonte. Não há divergência — o Comitê C já separa as
duas versões nas Fases 2 e 3 do roadmap dele, o que bate exatamente com minha separação de
categorias A vs. E.

### 2.7 H5 — Valor de mercado só em mata-mata cross-divisão (escopo estreito)

**(b) Concordo com o valor estatístico do escopo estreito, mas discordo que isso mude a
classificação de risco de engenharia.** O argumento do Comitê C é bom pela lente estatística: restringir
o teste ao recorte onde o Elo é estruturalmente mais fraco (mata-mata cross-divisão, já identificável
via `predict_aggregate`/§17) reduz a diluição de sinal em ruído nos 90%+ dos jogos domésticos onde o
Elo já funciona bem — isso é um argumento de poder estatístico, não de engenharia, e não é meu
mandato contestar. **Mas** minha classificação de risco (categoria **E** — sem API oficial, ToS não
autoriza uso comercial, risco de leakage se mal implementado) não muda com o escopo do experimento:
o dado ainda vem do mesmo scraper de terceiro, com o mesmo risco de ToS, independente de quantos
jogos ele alimenta. Escopar o USO reduz o risco de diluição estatística, não o risco de
produto/ToS de trazer a fonte para dentro do pipeline. Concordo que, SE o dono do projeto aceitar o
risco de ToS, o escopo restrito é a forma certa de gastar esse risco — mas a decisão de aceitar o
risco em si continua sendo a mesma decisão de negócio que eu já sinalizei no round 1, não fica mais
fácil só porque o escopo é menor.

### 2.8 Ranking e roadmap de 4 fases do Comitê C

**(a) Concordo com a Fase 1 quase integralmente** — os 6 itens da Fase 1 do Comitê C (Dirichlet,
Beta, auditoria leakage-aware, PSI, diagnóstico bias-correction por safra, ausência ponderada por
status binário) são um subconjunto quase idêntico do meu top 8 de round 1. Convergência de 3 comitês
independentes na mesma lista de "baixo esforço, dado já disponível" é o sinal mais forte deste round
inteiro.

**(c) Fica em aberto** o posicionamento de "Elo ajustado por margem de gols" — o Comitê C classifica
como "Promissor" (Fase 2), não Fase 1, citando "ganho incerto, nunca medido" como motivo para não ser
prioritário. Do lado de viabilidade eu o coloquei no topo do meu ranking exatamente pela razão
oposta: é o item de MENOR custo/risco de todo o levantamento (zero dado novo, muda uma função já em
produção, não depende de nenhuma outra peça), então mesmo com valor esperado incerto, o custo de
descobrir se funciona é o mais baixo de todos — ordem de execução barata deveria vir cedo
independente do valor esperado, porque o objetivo de um teste barato é justamente resolver a
incerteza a baixo custo. Isso não é uma divergência de fato (concordamos no custo e na incerteza do
ganho) — é uma diferença de critério de priorização (meu mandato pondera custo de descoberta;
"ganho esperado" pondera valor esperado a priori) que cabe à síntese final decidir, não a mim
resolver unilateralmente.

---

## 3. Resposta direta às duas perguntas do coordenador

### 3.1 "Distância entre escalação confirmada e escalação histórica" (hipótese #5 do Comitê A) — é
computável hoje ou precisa de fonte nova?

**Resposta: nem A nem F puro — é categoria B, com uma pergunta de fato em aberto que só um grep no
código resolve.**

O dado subjacente (lineup/escalação por partida) **não é uma fonte nova** — a API-Football já expõe
`/fixtures/lineups`, e o próprio Agente 5 confirma que `coach_id`/staff já vem por fixture via
lineups na coleta atual. Isso, por si só, sugere categoria A. Mas construir a feature de fato exige
três coisas que nenhum dos 7 agentes nem o Comitê A detalhou:

1. **Confirmar que o lineup (XI titular, não só `coach_id`) está de fato persistido no espelho local**
   (`data/{club_,}raw_cache.sqlite`) para as competições relevantes, não só disponível "em tese" via
   API. O CLAUDE.md documenta scorer/shots_prop como lendo o espelho local para minutagem de jogador
   — é plausível que o dado já esteja lá, mas isso é uma verificação de código que este comitê não
   pode fazer sob o guarda-corpo de "só documentação" e que nenhum dos 7 agentes verificou.
2. **Construir a agregação "escalação histórica média/usual" por time** — quantos titulares habituais,
   ponderados por minutos recentes, definem o "XI esperado" de um time antes de qualquer jogo. Isso é
   trabalho de engenharia novo (não existe hoje), ainda que sobre dado já coletado.
3. **Respeitar o corte point-in-time correto**: a escalação confirmada de um jogo normalmente só é
   publicada ~1h antes do apito (achado do próprio workflow leakage-aware do Agente 6, endossado pelo
   Comitê A). Isso significa que a feature "distância escalação confirmada vs. histórica" só existe,
   de forma válida, na janela final antes do jogo — não é possível calculá-la com a mesma antecedência
   que outras features do modelo (Elo, forma recente) permitem hoje.

**Classificação final: categoria B** (zero fonte externa nova, mas engenharia real de agregação +
uma pergunta de fato não resolvida sobre cobertura do espelho local) — não é tão barato quanto "G-Elo"
ou "calibração Beta", mas também não é bloqueado como xT/Packing Rate. **Ponto em aberto (c):**
se o lineup completo já está no espelho local para as 72 competições de clube ou só `coach_id`/staff
— isso decide se o item 1 acima é trivial (dado já em mãos) ou vira mais um mini-job de coleta
(categoria C).

### 3.2 H1 do Comitê C (momentum de jogador agregado como feature do DC-NB de gols) — é "zero dado
novo" de fato, ou tem custo de engenharia escondido?

**Resposta: tem custo de engenharia escondido, e é o MESMO custo do item 3.1 — as duas hipóteses
(A#5 e C1/H1) colidem na mesma dependência de lineup pré-jogo que nenhum dos 7 agentes originais
tratou como candidato próprio.**

O Comitê C descreve H1 como "não precisa do shrinkage bayesiano completo do FSAA, só precisa testar
se a soma/média do `player_momentum_score` (já calculado e aprovado para o scorer_model) do XI
titular provável... reduz log-loss" — e é verdade que a PARTE MODELADA (a pontuação de momentum por
jogador) é genuinamente reaproveitável sem custo: essa hipótese estatística já passou o gate, não
precisa ser re-testada. **Mas a frase "do XI titular provável" esconde exatamente o mesmo problema
de engenharia do item 3.1:**

1. **Definir "titular provável" pré-jogo** exige ou (a) esperar a escalação confirmada (mesma janela
   de ~1h antes do apito do item 3.1 — ou seja, a feature só fica disponível tarde), ou (b) construir
   um sub-modelo de "probabilidade de titularidade" a partir de minutagem histórica recente (isso é
   um componente de modelagem novo, não trivial, que nenhum dos 7 agentes propôs construir).
2. **Cobertura desigual por competição** — o próprio Comitê C já sinaliza isso na validação proposta
   ("segmentar por competição, cobertura mais fraca em ligas menores"), o que é consistente com o
   padrão documentado no projeto de que dado de escalação/lesão é mais fraco em ligas menores da
   expansão de 83 competições.
3. **Pergunta de produto não endereçada por nenhum agente**: a plataforma gera "Análise Independente"
   e permite ao usuário configurar análises — não está documentado se as previsões são tipicamente
   consumidas horas/dias antes do jogo (quando lineup não está confirmado) ou próximo do kickoff. Se
   o uso típico é horas/dias antes, uma feature dependente de lineup confirmado teria cobertura de
   produção baixa (a maioria das previsões seria gerada sem o dado disponível ainda) — isso é uma
   restrição de viabilidade de produto, não só de modelagem, que caberia ao dono do projeto esclarecer
   antes de comprometer o esforço de implementação.

**Classificação final: categoria B**, igual ao item 3.1 (aliás, são a mesma dependência de
engenharia com duas aplicações diferentes — uma como feature de "distância" simples, outra como
agregação de momentum ponderado). **Concordo com o Comitê C que o NÚCLEO estatístico (momentum de
jogador prediz melhor que momentum de time) é a evidência mais forte e mais barata de re-testar em
outro mercado** — isso não tem custo de engenharia escondido, já está validado. **Discordo
respeitosamente da moldura "zero fonte de dado nova, reusa uma feature já validada sob o gate"** como
descrição completa do esforço: a parte que falta construir (agregação por XI provável, respeitando
corte point-in-time, com cobertura desigual por competição) é um projeto de engenharia de dados
médio, não a reutilização direta de uma feature pronta. Ambos H1 e a hipótese #5 do Comitê A deveriam
aparecer no relatório final como **um único candidato de engenharia compartilhada** ("agregação de
lineup pré-jogo — infraestrutura comum"), com dois usos possíveis a jusante (distância-da-escalação-
usual E momentum-agregado-do-XI), evitando que o relatório final conte isso como dois candidatos
independentes de custo diferente quando na prática é uma única peça de infraestrutura nova.

---

## 4. O que muda na minha posição de round 1 (resumo)

- **Reclassificações que incorporo:** "vantagem de mandante variável no tempo" desce de prioridade
  prática (deve passar por análise de poder estatístico antes de qualquer desenho, argumento do
  Comitê A); "dispersão de odds cross-bookmaker" entra como novo candidato barato (categoria A);
  "bias correction segmentada" ganha um desenho melhor combinando overround como peso (C2 do Comitê
  C, ainda categoria B mas mais defensável); clima ganha uma correção de metodologia de teste
  (segmentar por severidade) sem mudar sua categoria D.
- **Achado novo mais importante deste round:** tanto a hipótese #5 do Comitê A quanto H1/C4 do
  Comitê C miram a mesma pergunta de fora (granularidade de jogador bate granularidade de time) e
  ambos subestimam, do meu ângulo, o mesmo custo de engenharia escondido — agregação de lineup
  pré-jogo com corte point-in-time correto e cobertura desigual por competição. Isso não é "zero
  dado novo" como os dois comitês descreveram; é categoria B, e as duas propostas deveriam virar UM
  candidato de infraestrutura compartilhada no relatório final, não dois.
- **Divergências que ficam em aberto:** se "Elo por margem de gols" deveria estar na Fase 1 (minha
  posição, custo-de-descoberta baixo) ou Fase 2 (posição do Comitê C, valor esperado incerto) — é
  diferença de critério de priorização, não de fato; se CMP-MLE deveria substituir um item mais
  barato no top 8 do relatório final — depende de quanto peso dar a "mecanismo novo" vs. "custo
  mínimo"; e se o espelho local já contém lineup completo (XI titular) para as 72 competições de
  clube ou só `coach_id` — pergunta de fato que só uma verificação de código resolve, fora do
  guarda-corpo deste round.
- **Onde os três comitês convergem sem atrito:** a Fase 1 do roadmap (Beta/Dirichlet, auditoria
  leakage-aware, PSI, ausência ponderada por status binário) é praticamente idêntica nos três
  documentos, vinda de três mandatos diferentes — é o sinal mais forte de consenso genuíno deste
  material inteiro.

---

## Resumo (3-5 frases)

Depois de ler os Comitês A e C, minha priorização de viabilidade muda pouco no núcleo (Beta/Dirichlet,
auditoria leakage-aware, PSI, ausência ponderada por status, G-Elo/Elo-margem continuam meu top,
agora com forte convergência dos três comitês) mas ganha uma correção real: a hipótese mais
"estratégica" do Comitê C (H1 — levar momentum de jogador para o modelo de resultado) e a hipótese
mais "estatística" do Comitê A (distância escalação-confirmada vs. histórica) são, sob a lente de
engenharia, a MESMA dependência não resolvida — agregação de lineup pré-jogo com corte point-in-time
— que nenhum dos 7 agentes originais tratou como candidato próprio e que ambos os comitês
subestimaram ao chamar de "zero dado novo". Não mudo de posição sobre valor de mercado/Packing
Rate/SciSkill (já estavam fora do meu top 8 por risco de fonte, e o argumento de confounding do
Comitê A só reforça, não substitui, essa exclusão). A maior contribuição deste round foi transformar
duas propostas aparentemente independentes e "baratas" em uma única peça de infraestrutura de custo
médio com uma pergunta de fato em aberto (cobertura do espelho local de lineup), e não uma mudança
de rejeitar ou aceitar candidatos que eu já tinha avaliado.
