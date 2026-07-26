# Comitê A — Round 2: reconciliação com Comitê B e Comitê C

**Data:** 2026-07-24
**Base:** `comite_A_round1.md` (rigor estatístico/viés) confrontado com `comite_B_round1.md`
(viabilidade de dados/engenharia) e `comite_C_round1.md` (estratégia/originalidade/roadmap).
**Regra deste round:** para cada ponto de divergência (ou de convergência que valha registrar),
decidir explicitamente (a) concordo e incorporo, (b) discordo e explico por quê (rigor
estatístico/viés, não preferência), ou (c) fica em aberto — divergência de fato não resolvida.
Só revisão e documentação, nenhum código tocado.

---

## 1. Divergências/convergências com o Comitê B (viabilidade de dados/engenharia)

O mandato do Comitê B é ortogonal ao meu por desenho (eles não avaliam mérito estatístico, eu não
avalio custo de engenharia) — a maioria dos pontos abaixo são **(a) concordo**, porque os dois
eixos são complementares, não competem pela mesma resposta. Sinalizo como (b)/(c) só onde a
reclassificação de complexidade do Comitê B carrega, implicitamente, uma afirmação sobre risco que
minha lente também precisa avaliar.

### 1.1 Elo ajustado por margem de gols e G-Elo → reclassificados como "A" (zero dado novo, trivial)

**(a) Concordo e incorporo.** A reclassificação de B não conflita com meu round 1 — reforça. Do
lado do rigor: essas duas ideias trocam a FORMA do update do Elo, não introduzem nenhuma variável
nova correlacionada com força de time (o placar já é o próprio alvo que o DC-NB modela). Isso é
estruturalmente o candidato de menor risco de confounding de toda a lista, porque não há espaço
para "times fortes têm mais X" — X aqui é literalmente o resultado que o modelo já usa. A
reclassificação de B para "A" e o meu ranking #1 no round 1 apontam para a mesma conclusão por
caminhos independentes (engenharia barata + risco estatístico baixo), o que é um sinal de
convergência genuína, não de um comitê copiando o outro.

### 1.2 Calibração Beta e Dirichlet → "A"

**(a) Concordo e incorporo, com um princípio geral a registrar no relatório final.** Vale nomear
explicitamente por que calibração pós-hoc é categoricamente de baixo risco de confounding: ela
opera só sobre a SAÍDA já treinada do modelo (probabilidade bruta → probabilidade calibrada), nunca
adiciona uma feature de entrada nova. Isso significa que praticamente todo o risco de confounding
com Elo/força que discuto no round 1 é, por construção, inaplicável aos candidatos de calibração —
o único risco real é estatístico-de-amostra (poucos dados por bin/segmento), que é exatamente o
tipo de risco que a reclassificação "B" do Comitê B para bias correction segmentada (ver 1.3) já
antecipa. Recomendo que o relatório final registre "calibração pós-hoc" como uma categoria de risco
à parte — sempre mais segura do ponto de vista de confounding do que qualquer feature de entrada
nova, mesmo quando a complexidade de engenharia é parecida.

### 1.3 Bias correction segmentada por liga → B rebaixa de "Média" para "B" (zero dado novo, mas estatística real)

**(a) Concordo plenamente — isso reforça, não conflita com, uma preocupação que eu já tinha
sinalizado de forma mais genérica.** No round 1 (seção 2), listei a família "parâmetro global
deveria variar por time/período" como de alto risco de overfitting mascarado de heterogeneidade
real, citando o precedente do Perfil Elo-condicionado (reprovado por inconsistência entre
competições). Bias correction segmentada por liga é estruturalmente o MESMO risco aplicado a um
objeto diferente (uma correção pós-hoc em vez de um parâmetro do modelo): 72 torneios heterogêneos,
vários com pouco volume, correndo o risco de reintroduzir exatamente o overfitting de amostra
pequena que já reprovou a isotônica em chutes. O aviso de B ("precisa de shrinkage por volume
mínimo por segmento para não recriar o mesmo overfit") e a minha ressalva de round 1 chegam à mesma
recomendação prática por lentes diferentes (engenharia vs. estatística) — vale que o relatório
final trate isso como um único ponto de atenção reforçado por dois comitês independentes, não dois
achados separados.

### 1.4 Job de coleta `/injuries` de clube em massa → maior item de alavancagem, não ranqueado como 1ª classe por nenhum dos 7 agentes

**(a) Concordo, com uma distinção que quero deixar explícita para não ser mal-lida como
discordância.** Do ponto de vista de rigor, coletar mais dado de lesão não introduz confounding
nem leakage por si — é infraestrutura neutra. O risco que sinalizei no round 1 (§2-3) está
inteiramente na camada SEGUINTE, quando alguém decide COMO pesar a ausência (status clínico vs.
valor de mercado) e QUANDO o status é considerado "conhecido" (point-in-time). Ou seja: concordo
que o job de coleta deveria ranquear mais alto na priorização de engenharia, mas isso não muda em
nada minha avaliação de risco da feature que será construída em cima dele — a parte barata
(coleta) e a parte que precisa de cuidado (ponderação point-in-time-correta) continuam sendo coisas
diferentes, e a reclassificação de B não elimina a segunda.

### 1.5 Valor de mercado de elenco (Transfermarkt) → B reclassifica para "E" (risco de ToS explícito, produto comercial)

**(a) Concordo e incorporo — isso ADICIONA uma terceira razão independente à minha desconfiança do
round 1, não substitui as outras duas.** No round 1 eu já rejeitava valor de mercado por dois
motivos: confounding com Elo (correlação alta, mesma família do "muro de dados" que matou xG) e
risco de leakage temporal se o scraper capturar valor corrente em vez de histórico point-in-time.
B adiciona um terceiro motivo, de natureza totalmente diferente (jurídico/produto: ToS do
Transfermarkt não autoriza uso comercial, e o ApostaInfo cobra do usuário). Os três motivos são
independentes entre si — nenhum decorre dos outros — o que deixa esse candidato com uma pilha de
razões para ficar fora do top de prioridade, não uma razão só reforçada três vezes. Concordo com a
recomendação de B de tratar isso, se algum dia testado, como piloto de pesquisa isolado e
não-produtivo, nunca como cron de produção.

### 1.6 "Flag mesma competição como interação explícita" → B classifica "A" e inclui no top-8 de viabilidade

**(b) Discordo parcialmente da priorização (não do fato de engenharia).** B tem razão que é
100% derivável do dataset já coletado — sem contestação no eixo de custo. Mas o próprio Agente 5
(fonte original) já registrou: "risco alto de redundância com o K por competição que o Elo do
projeto já usa" — ou seja, esse candidato específico carrega um risco de colinearidade documentado
pela própria fonte que nem B nem C endereçam nos seus rankings. "Barato de testar" não é o mesmo
que "deveria estar no topo da fila" quando a probabilidade a priori de o resultado ser nulo
(porque a informação já está capturada pelo K por competição) é alta — testar um candidato
provavelmente redundante ainda consome um slot de validação sob gate §6 e tempo de análise. Não
proponho remover do backlog (é barato o suficiente para não doer), mas rebaixaria a prioridade
relativa dentro do próprio grupo "A" de B, priorizando primeiro os itens "A" sem risco de
colinearidade documentado (Elo por margem, G-Elo, Beta/Dirichlet) antes deste.

### 1.7 Vantagem de mandante variável no tempo → B classifica "A/B" (dado grátis, desenho não é)

**(a) Concordo com a classificação, mas reafirmo a ressalva que B não faz por estar fora do seu
mandato.** B está certo que não precisa de fonte nova. Mas esse candidato está exatamente dentro da
família que eu classifiquei como "parâmetro global deveria variar" (round 1, §1 item 6 e §2) — o
"custo zero de dado" não resolve o risco de que qualquer forma funcional testada (tendência linear,
spline, por-divisão) tropece no mesmo limite de amostra por segmento que já reprovou o Perfil
Elo-condicionado. "Dado é grátis, desenho não é" (frase do próprio B) é exatamente o ponto: o custo
de ENGENHARIA é baixo, mas o risco ESTATÍSTICO de decidir mal a forma funcional é alto — os dois
comitês concordam no diagnóstico, só olhando eixos diferentes do mesmo problema.

### 1.8 Compound Poisson/geometric-Poisson para escanteios → B confirma "Alta complexidade, não falta de dado", trata como sprint à parte

**(a) Concordo integralmente.** É a mesma conclusão que cheguei no round 1 por um caminho
diferente: coloquei esse candidato em 8º no meu ranking (não mais alto, apesar de ser a evidência
mais forte de todo o levantamento) justamente porque, além do custo de implementação que B
identifica, ele é adjacente a uma hipótese já reprovada (dispersão dinâmica de escanteios,
Tail-ECE) e exige desenho cuidadoso para provar que ataca o mecanismo por um ângulo genuinamente
diferente (rajadas/cluster, não suavização contínua) antes de justificar o esforço. B e eu
convergimos em "não é para agora, é projeto à parte" por razões complementares (custo de engenharia
+ risco de repetir uma falha já conhecida) — vale que o relatório final registre as duas razões
juntas como justificativa, não só uma.

---

## 2. Divergências/convergências com o Comitê C (estratégia/originalidade/roadmap)

### 2.1 C1 — Rating unificado (margem de gols + ausência ponderada), testado como pacote com ablation

**(b) Concordo com a lógica de combinar, mas discordo que a ablation proposta seja suficiente
proteção metodológica — falta um ponto de rigor que C não menciona.** Testar sinais fracos
combinados para dar ao efeito conjunto uma chance melhor de cruzar o limiar do gate é uma prática
legítima, e o desenho de ablation de C (4 variantes: produção, só margem, só ausência, as duas)
é o jeito certo de isolar contribuição. Mas empacotar duas hipóteses e testá-las juntas
mecanicamente aumenta os "graus de liberdade do pesquisador" (quantas formas de combinar/pesar os
dois componentes existem?) em relação a testar cada hipótese isoladamente sob o mesmo threshold do
gate — isso é um risco de inflar falsamente a chance de "passar" que C não discute. Recomendo que o
relatório final exija, para qualquer teste de pacote combinado, um plano de ablation
pré-registrado (não ajustado depois de ver o resultado) e considere um limiar mais conservador do
que o padrão de hipótese única — sem isso, o risco é reproduzir, em miniatura, o mesmo tipo de
problema que motivou o item 2.1 do Agente 6 (CV aleatória infla otimisticamente o desempenho
percebido de cada feature).

### 2.2 C2 — Calibração segmentada por liga usando overround como peso de shrinkage

**(a) Concordo e incorporo — é um refinamento genuíno do meu candidato #5/#9 de round 1.** No round
1 eu já tinha bias correction segmentada (#5) e dispersão/overround como sinal de incerteza (#9,
hipótese nova) como itens separados. A proposta de C de usar o overround médio da liga como o
PESO de shrinkage (ligas líquidas confiam mais na própria curva local; ligas rasas puxam mais para
a curva global) é uma amarração mais elegante e estatisticamente mais defensável do que um
threshold de volume arbitrário — resolve o risco de overfitting em amostra pequena (minha
preocupação e a de B, ver 1.3) com um sinal já disponível e principiado, em vez de um número mágico
de "jogos mínimos por segmento". Recomendo que o relatório final funda os dois candidatos do meu
round 1 exatamente como C propõe.

### 2.3 C3 — Cascata causal estendida (posse→chutes→escanteios→cartões→gols)

**(a) Concordo e incorporo — C encontrou um risco de leakage mais grave e mais concreto do que o
que eu tinha sinalizado no round 1.** No round 1 (§3) eu tratei o risco de leakage da cascata como
uma questão de TIMING fino (corte por hora de publicação de escalação, não só por data). C aponta
algo mais sério: se "posse" entrar como nó de entrada da cascata causal, a posse de bola do PRÓPRIO
JOGO só é conhecida depois da partida — usar a posse do jogo como feature preditiva desse mesmo
jogo não é um vazamento sutil de timing, é vazamento direto e grosseiro de uma estatística pós-jogo
(exatamente a classe de erro que a nota de leakage do Agente 6 cita, "target leakage em esportes").
C já corrige isso propondo posse histórica/média do time (não a do jogo em si) — concordo com a
correção e reforço que isso deveria ser um guard-rail explícito e não-negociável no relatório final
para qualquer candidato desta família: qualquer estatística de box-score (posse, chutes, cartões)
só pode entrar como feature se for agregado histórico pré-jogo, nunca do jogo-alvo.

### 2.4 C4 — Índice de qualidade do XI titular (FSAA adaptado + shrinkage bayesiano por jogador)

**(a) Concordo com a convergência de origem, mas reafirmo uma ressalva do meu round 1 que a seção
de implementação de C não menciona.** C4 converge com a minha hipótese nova #5 do round 1 (mesma
leitura cruzada: sinal de jogador > sinal de time neste projeto). Mas C4 especificamente adapta o
FSAA, que depende de decompor `gols_marcados − esperado_por_shots_prop_model` por jogador — e
existe um paper citado pelo próprio Agente 1 (arXiv:2401.09940, "vieses em modelos de xG
confundindo finishing ability") que documenta exatamente o risco de essa decomposição confundir
"acima da média em finalização" com "recebeu chances melhores que a média por acaso de amostra
pequena", se a qualidade da oportunidade não for controlada com cuidado. C não cita esse risco na
seção de implementação do C4 — reforço aqui que qualquer teste desta ideia precisa de controle
explícito de qualidade de oportunidade (não só volume de chutes) antes de atribuir o resíduo a
habilidade real do jogador.

### 2.5 H2 — Falha da isotônica no 1X2 pode ser artefato do método, não evidência de boa calibração

**(a) Concordo sem ressalva.** É uma leitura correta e bem fundamentada do achado do Agente 6
(isotônica one-vs-rest quebra a restrição soma=1 em multiclasse) contra a interpretação implícita
do histórico do projeto. Não é uma reformulação de nada já reprovado — é um diagnóstico novo e
metodologicamente são. Concordo com o desenho de validação de C (Dirichlet sobre as probabilidades
OOF do 1X2, olhando primeiro a curva de calibração/ECE por classe antes de decidir se há algo a
corrigir).

### 2.6 H3 — Bias correction segmentada deveria priorizar as competições da expansão 2026

**(a) Concordo.** Consistente com minha posição de round 1 e com a análise de risco de B (§1.3
acima) — dirigir o diagnóstico primeiro às competições com menos histórico (onde o risco de
overfitting/viés mal calibrado é estruturalmente maior) é a sequência certa antes de segmentar
todos os 72 torneios de uma vez.

### 2.7 H4 — Choques discretos de mudança de regime (vs. decaimento contínuo)

**(a) Concordo que é uma família genuinamente distinta do que já reprovou, com uma ressalva nova de
rigor que C não menciona.** No round 1 eu agrupei "parâmetro global deveria variar por
time/período" (Rue-Salvesen, home-advantage-por-time, prior comensurável) como uma família de alto
risco por precedente (Perfil Elo-condicionado). H4 é estruturalmente diferente — não é um
parâmetro contínuo por time, é um flag esparso ativado só em eventos discretos e raros (troca de
técnico) — concordo que essa distinção é real e que C tem razão em não tratar isso como "mais uma
tentativa do mesmo mecanismo". Mas adiciono uma ressalva que é uma VARIANTE do mesmo risco
estrutural, não o risco original: o gate §6 exige segmentação por competição/continente, e trocas
de técnico são eventos raros — segmentado por competição, o número de jogos "pós-troca-de-técnico"
por liga pode ser pequeno demais para produzir uma estimativa estável, mesmo sendo uma feature
mecanicamente diferente da família já reprovada. Recomendo testar primeiro agregado (sem
segmentação fina) e só then avaliar se há amostra suficiente para segmentar.

### 2.8 H5 — Valor de mercado só em mata-mata cross-divisão/continental

**(a) Concordo — é exatamente o desenho que resolve minha objeção de confounding do round 1, mas
não resolve as outras duas objeções (leakage + ToS/B) que continuam de pé.** No round 1 eu rejeitei
valor de mercado de elenco citando confounding com Elo como motivo principal. C tem razão que o
motivo do confounding (Elo já captura força relativa DENTRO da mesma população/liga) não se aplica
da mesma forma em mata-mata cross-divisão, onde a comparabilidade do Elo entre populações
diferentes é a fraqueza estrutural conhecida do sistema — escopar o experimento a esse recorte é
precisamente o tipo de desenho que poderia sobreviver a um teste de embaralhamento contra
`elo_diff` onde a versão full-sample não sobreviveria. Incorporo essa correção: deixo de tratar
valor de mercado como "descartado por confounding" em qualquer escopo e passo a tratá-lo como
"descartado no escopo full-sample, candidato a piloto restrito em mata-mata cross-divisão" — mas
reitero que isso não elimina o risco de leakage (valor point-in-time vs. corrente) nem o risco de
ToS/produto comercial que B levantou (§1.5) — ambos são ortogonais ao escopo e continuam exigindo
resolução (decisão do dono do projeto, conforme já apontado por B e C) antes de qualquer piloto,
mesmo restrito.

---

## 3. Resposta direta às duas perguntas do coordenador

### 3.1 A reclassificação de complexidade de B ("zero dado novo") bate ou conflita com minha avaliação de confounding/robustez?

**Bate, nos quatro candidatos citados, sem exceção — mas por uma razão estrutural que vale deixar
explícita:** os quatro candidatos que B elevou por serem "zero dado novo" (Elo por margem,
calibração Beta/Dirichlet, bias correction segmentada, job de `/injuries`) são, cada um, candidatos
que ou (i) não introduzem nenhuma variável de entrada nova correlacionada com força de time — Elo
por margem só muda a FORMA do update, calibração só remapeia a SAÍDA — ou (ii) são infraestrutura
neutra cujo risco real mora inteiramente na camada de modelagem construída em cima (bias
correction segmentada, job de coleta). Ou seja: **"zero dado novo" e "baixo risco de confounding"
não são a mesma propriedade, mas neste conjunto específico de 4 candidatos elas coincidem por
construção**, porque nenhum dos quatro adiciona uma feature de entrada nova ao modelo de gols. Isso
não é garantido em geral — valor de mercado de elenco (Ag.7) também é "zero dado novo" no sentido
de já ter sido escopado por B como candidato barato de avaliar, mas carrega risco de confounding
alto porque É uma feature de entrada nova correlacionada com força. A lição que registro para o
relatório final: usar "custo de dado" como proxy de "risco estatístico" funciona bem para
calibração/ajuste-de-update, mas falha para qualquer candidato que seja, ele mesmo, uma feature de
entrada nova — os dois eixos precisam continuar sendo avaliados separadamente, não substituídos um
pelo outro.

### 3.2 H1 do Comitê C (momentum de jogador agregado como feature de entrada do DC-NB de gols) — risco de confounding/leakage não considerado por C

Encontrei dois riscos concretos que a seção de implementação/validação de C não aborda:

**Risco 1 — a agregação pode colapsar exatamente o mecanismo que fez o sinal de jogador funcionar,
regredindo para o "momentum de equipe" já reprovado.** A razão dada por C para o momentum de
jogador ter passado (AUC 0,68→0,71) enquanto momentum de time reprovou repetidamente é "captura
quem está em campo, line-up specific" — ou seja, o valor está na informação COMPOSICIONAL
(diferenciar jogador A de jogador B dentro do mesmo XI). Mas ao somar/agregar o momentum de todos
os titulares prováveis num único escalar por time por jogo, essa informação composicional é
justamente o que se perde — o agregado passa a ser, matematicamente, muito mais parecido com uma
média de forma recente DO TIME (que já foi testada e reprovada) do que com o sinal
"quem-está-jogando" que validou o momentum no scorer_model. Não é garantido que isso aconteça —
mas é um risco a priori real que nenhum agente nem C isolou, e que só um teste de embaralhamento
específico (embaralhar a atribuição jogador→time mantendo os escalares agregados) poderia
descartar antes de confiar no resultado do gate. C parcialmente antecipa isso ao propor segmentar
por "escalações voláteis" (copas com rotação) como assinatura de sinal real — concordo que é um
bom controle, mas ressalto que é o MESMO padrão estatístico que já me preocupou no round 1 para
clima (§5, hipótese nova #7): um efeito real mas concentrado num subconjunto raro de jogos (alta
rotação) pode ser diluído a zero pelo delta médio agregado do gate se a maioria dos jogos (times
com XI estável) não mostrar efeito nenhum — recomendo que, se H1 for testado, a segmentação por
volatilidade de escalação seja parte do desenho PRINCIPAL de validação, não uma checagem posterior.

**Risco 2 — descompasso entre treino (escalação confirmada, point-in-time) e produção (escalação
"provável", antes da confirmação oficial).** A escalação oficial normalmente só é publicada
~1h antes do apito (o mesmo ponto que a auditoria leakage-aware do Agente 6/C3 já levanta para a
cascata). Se a feature for treinada usando a escalação confirmada de jogos históricos (correto,
point-in-time válido), mas o ApostaInfo gera a análise para o usuário horas ou dias antes do jogo
(quando só existe uma escalação "provável", não confirmada), o conteúdo informacional da feature em
produção seria sistematicamente mais fraco e mais ruidoso do que em treino — não é leakage no
sentido clássico (não vaza informação do futuro), é um descompasso treino/produção que pode fazer
uma feature aprovada sob gate parecer boa no backtest e decepcionar quando servida de fato. Nenhum
dos 7 agentes nem C discutem em que momento, relativo ao kickoff, o ApostaInfo publica sua análise
— esse é um dado de produto que precisa ser confirmado antes de promover H1, não só um detalhe de
implementação.

**Como isso muda minha posição sobre H1:** não discordo da lógica central de C (o padrão
jogador-bate-time é real e vale perseguir) — concordo que é uma hipótese de mérito genuíno e uma
boa leitura cruzada dos 7 domínios. Mas rebaixaria a confiança de H1 de "Promissor"/quase-topo
(como C mesmo classificou, com a ressalva de que a prosa do resumo de C o chama de "melhor
custo-benefício", uma tensão que o próprio documento de C não resolve) para "testável, mas com dois
guard-rails obrigatórios antes de qualquer promoção": (1) teste de embaralhamento
jogador↔time sobre o agregado, não só o delta de log-loss agregado, e (2) confirmação de que a
escalação disponível no momento real de geração da análise em produção tem cobertura/qualidade
equivalente à usada no treino. Sem os dois, um resultado positivo no gate §6 padrão seria
insuficiente para descartar que H1 é, na prática, uma reencarnação do momentum de equipe já
reprovado, disfarçada pela agregação de um sinal que era, individualmente, mais fino.

---

## 4. Ajustes ao meu ranking de round 1

Nenhuma mudança de posição nos itens 1-8 do meu ranking de round 1 (G-Elo/margem, Beta/Dirichlet,
CMP barato, ausência ponderada por status, bias correction segmentada, auditoria leakage-aware,
PSI, Compound Poisson escanteios) — todos foram reforçados, não contestados, pela leitura de B e C.

Mudanças específicas:

- **Item #9 do meu round 1** (dispersão de odds cross-bookmaker como feature de incerteza) — fundo
  com a proposta de shrinkage-por-overround de C2, mantendo a posição no ranking mas como parte de
  um pacote maior (bias correction segmentada + overround) em vez de item isolado.
- **Item #10 do meu round 1** (distância escalação-confirmada vs. histórica) — mantenho, e agora
  registro explicitamente que é uma alternativa de desenho a H1 do Comitê C que evita o Risco 1
  descrito acima (uma métrica de DISTÂNCIA/mudança de composição preserva mais informação
  composicional do que uma SOMA/média de momentum, que tende a colapsar de volta para "forma média
  do time"). Recomendo ao relatório final apresentar os dois (H1 de C e minha hipótese #10) como
  duas implementações concorrentes da mesma ideia-mãe, não como itens redundantes — vale testar
  ambas e comparar.
- **"Flag mesma competição"** (top-8 de B) — não entra no meu top 10; risco de colinearidade
  documentado pela própria fonte (Ag.5) não foi endereçado por B nem C.
- **Valor de mercado de elenco** — sai de "fora do top 10 por três razões independentes" (round 1)
  para "fora do top 10 no escopo geral, mas candidato a piloto restrito e de baixa prioridade em
  mata-mata cross-divisão (H5 de C), condicionado a resolver leakage point-in-time e ToS antes de
  qualquer teste, mesmo restrito".
- **H1 (Comitê C)** — passa a constar explicitamente no meu ranking como candidato #11
  ("testável, com 2 guard-rails obrigatórios" — ver §3.2), não descartado, mas também não promovido
  ao top 10 sem os controles adicionais.

---

## O que mudou (ou não) na minha posição — resumo em 3-5 frases

A leitura dos rounds 1 de B e C não mudou nenhuma das minhas 8 principais recomendações de
prioridade — os dois comitês, por eixos diferentes (engenharia e estratégia), chegaram
independentemente às mesmas conclusões centrais que eu (Elo por margem/G-Elo e calibração
Beta/Dirichlet no topo; valor de mercado, ratings-vendor e a família "parâmetro global por
segmento" no fundo), o que aumenta minha confiança nessas posições em vez de exigir revisão. A
mudança real é de granularidade: incorporei o refinamento de C (overround como peso de shrinkage
para bias correction segmentada) e a correção de escopo de C para valor de mercado (mata-mata
cross-divisão em vez de full-sample) como melhorias genuínas às minhas próprias posições. O ponto
mais importante deste round é a resposta à pergunta sobre H1: identifiquei um risco real e
específico — a agregação de momentum de jogador em um escalar por time pode colapsar exatamente a
informação composicional que fez o sinal funcionar no scorer_model, regredindo para o "momentum de
equipe" já reprovado — que nem C nem nenhum dos 7 agentes de domínio havia isolado, e que exige
teste de embaralhamento jogador↔time (não só delta de log-loss agregado) antes de qualquer
promoção.
