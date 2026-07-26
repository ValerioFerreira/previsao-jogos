# Comitê C — Estratégia, originalidade e roadmap (Round 1)

**Data:** 2026-07-24
**Mandato:** ler os 7 relatórios de domínio (`wave1_agente{1..7}_*.md`) e o índice mestre
(`PESQUISA_VARIAVEIS_EXTERNAS.md`) e pensar estrategicamente — não redigitar tabelas por agente,
mas encontrar combinações cross-domínio e hipóteses inéditas que nenhum agente sozinho propôs, e
montar ranking/roadmap preliminares para reconciliação com o Comitê B.

**Nada aqui foi implementado ou testado sob o gate §6.** Tudo é hipótese a priorizar, não veredito.

---

## 1. Combinações cross-domínio

### C1 — Rating unificado: margem de gols + ausência ponderada por importância

**Quem se combina:** Elo ajustado por margem de gols estilo ClubElo/SPI (Agente 4, "único ângulo
sem sobreposição — barato, sem dado novo, nunca testado") + G-Elo (Agente 1, formalização
acadêmica de baixo risco da mesma ideia, drop-in replacement do update já em produção) + dedução
de rating por lesão ponderada por status (Agente 5, ganho medido -0,0081 Brier, `/injuries` já
coletado) + ausência ponderada por valor de mercado do jogador (Agente 7, mesma ideia do Agente 5
mas pesando pela importância/valor do jogador ausente em vez de só status binário).

**Por que testar junto, não separado:** os quatro candidatos mexem no mesmo objeto — a estimativa
de força pré-jogo que alimenta λ/μ do DC-NB — mas em dois eixos ortogonais: (a) *como o rating se
atualiza depois do jogo* (margem de gols em vez de W/D/L binário) e (b) *como o rating é ajustado
antes do próximo jogo* (penalidade por ausência de jogador-chave). Testados isoladamente, cada um é
"marginal mas real"; a hipótese de comitê é que são **complementares, não substitutos**: a margem de
gols melhora a inferência de força de longo prazo, a penalidade de ausência corrige a força de
curto prazo (aquele jogo específico). Testar separado arrisca cada um passar/falhar no ruído de
um efeito pequeno isolado; testar como um único pacote "rating v2" sob o gate §6 dá ao efeito
conjunto uma chance melhor de cruzar o limiar de ≥4/5 folds com delta médio <−0,001. Risco a
controlar: se só um dos dois componentes carrega o ganho, decompor via ablation (rodar com/sem cada
peça) antes de promover o pacote inteiro.

**Como isolar o efeito de cada peça:** rodar 4 variantes sob o mesmo split temporal — (i) produção
atual, (ii) só margem de gols, (iii) só ausência ponderada (status binário, sem valor de mercado —
não depende de fonte nova), (iv) as duas juntas. Só promover a combinação se (iv) bater (ii) e (iii)
isoladamente, não só a produção.

### C2 — Calibração paramétrica segmentada por liga, nos dois mercados onde isotônica falhou

**Quem se combina:** calibração Beta e Dirichlet como substitutas da isotônica especificamente em
chutes (amostra pequena) e 1X2 (multiclasse, restrição soma-1) (Agente 6) + bias correction
segmentada por liga/mercado, hoje confirmada global por leitura de código (Agente 6, mesmo agente
mas achado distinto) + overround por liga como sinal de confiança/liquidez de mercado (Agente 3).

**Por que faz sentido testar junto:** o diagnóstico do Agente 6 é "isotônica falha por
viés-variância ruim com poucos dados por bin" — mas o projeto de clube cobre 72 torneios
heterogêneos (§19.8), então "poucos dados por bin" pode ser sintoma de heterogeneidade entre
ligas escondida atrás de uma calibração/correção única e global, não só de amostra pequena em
agregado. A combinação natural é: treinar Beta/Dirichlet **por cluster de liga** (não uma curva
global), com shrinkage para a curva global proporcional ao volume da liga (evitando reintroduzir o
próprio problema que derrubou a isotônica em amostra pequena), e usar o overround médio da liga
como peso de quão "líquida"/confiável é a curva de referência de mercado daquela competição — ligas
com mercado mais raso (overround alto, Agente 3) puxam mais forte para a curva global; ligas
líquidas (overround baixo, top-5 europeu) confiam mais na própria curva local. Isso ataca ao mesmo
tempo (a) o motivo técnico da falha da isotônica e (b) a lacuna de processo já confirmada por grep
(`bias_correction.joblib` sem `groupby`), com uma única implementação em vez de duas.

**Validação:** gate §6 com métrica nativa por mercado, segmentado por liga/continente (já exigido
pela regra do próprio gate) — o teste decisivo é justamente se a curva segmentada bate a curva
global nas ligas menores da expansão 2026-07-19/22 (as 15 novas competições) sem piorar as ligas
grandes que já estavam bem calibradas pela curva global.

### C3 — Cascata causal explícita estendida: posse→chutes→escanteios→cartões→gols

**Quem se combina:** estrutura causal em cascata da Bayesian Network para Asian Handicap (Agente 1,
posse→chutes→chutes-no-alvo→gols, com o alerta de trocar pi-rating pelo Elo real do projeto) + a
cascata NB/GP já em produção do projeto (chutes→escanteios→cartões, "único encadeamento explícito
hoje", conforme CLAUDE.md) + workflow leakage-aware para exatamente os mercados dessa cascata
(Agente 6, paper 2026 sobre LaLiga shots/corners/cards/fouls, achado central: auditar se o corte
point-in-time é por variável e não só por linha, incluindo o momento de publicação da escalação).

**Por que faz sentido testar junto:** a cascata de produção hoje já é "saída de um modelo vira
feature de outro" mas só *downstream* de chutes (chutes→escanteios→cartões) — nunca formaliza o que
vem *antes* dos chutes (posse) nem reconecta ao resultado/gols no fim da cadeia. O paper do Agente 1
propõe exatamente estender a cadeia para trás (posse alimenta chutes) e para frente (chutes-no-alvo
alimenta gols) como um DAG causal único, o que é uma generalização natural da arquitetura que o
projeto já escolheu (cascata explícita > features soltas). Antes de qualquer expansão da cascata,
porém, o workflow leakage-aware do Agente 6 é o guardrail certo — audita se `predictor.py::build_row()`
já trata corte por variável (não só por linha) e se a hora de publicação da escalação é usada como
corte, não a hora do jogo; isso é relevante especialmente se "posse" for adicionada como nó de
entrada, pois posse é um dado disponível só pós-jogo (não é feature pré-jogo utilizável diretamente
— precisaria ser a posse **histórica/média** do time, não a do jogo em si, ponto que o comitê deve
deixar explícito para quem for propor o teste).

**Validação:** (1) primeiro rodar só a auditoria de leakage (barata, não é modelo novo) sobre a
cascata já em produção; (2) só depois, se a auditoria não achar problema, testar a extensão
posse-histórica→chutes como camada adicional da cascata, com Elo real substituindo pi-rating,
sob o gate §6 mercado a mercado (a cascata inteira não deve ser promovida em bloco).

### C4 — Índice de qualidade do XI titular (agregação de sinal de jogador, não de time)

**Quem se combina:** FSAA — Finishing Skill Above Average com shrinkage bayesiano (Agente 3,
adaptável ao proxy de finalizações `shots_prop_model` em vez de xG por chute literal) + a
observação do Agente 2 de que o único ângulo não-bloqueado do SciSkill Index é justamente ser
"agregado por jogador (soma do XI titular), não por time inteiro como pi-rating/Berrar" (que já
perderam) + o momentum de jogador já **aprovado** no gate (AUC goleador 0,68→0,71) — a única
exceção positiva em ~60 hipóteses testadas.

**Por que faz sentido testar junto:** os três domínios, lidos separadamente, cada um bateu na
mesma parede de um jeito diferente — Agente 2 não tem fonte de dado para o SciSkill em si (é
proprietário), Agente 3 não tem xG por chute em nível de evento para o FSAA literal, mas os dois
convergem na mesma conclusão estrutural: "granularidade de jogador aparenta ser mais promissora que
granularidade de time neste projeto" — e o projeto já tem uma prova disso (momentum de jogador
passou, momentum de time não). A combinação testável de fato (sem fonte de dado nova) é: aplicar o
shrinkage bayesiano do FSAA sobre o resíduo `gols_marcados − esperado_por_shots_prop_model` por
jogador (não por chute), agregar essa habilidade de finalização estimada dos titulares prováveis
do XI (ponderada por probabilidade de titularidade/minutos históricos) num único índice de "poder
de fogo do XI", e testar esse índice como feature de ENTRADA do DC-NB de gols — não só como prop de
jogador isolada (uso atual do momentum de jogador, restrito ao scorer_model). Isso é diferente de
"momentum de equipe" (que é forma recente do time como unidade, já reprovado): é bottom-up, soma de
sinais individuais avaliados com shrinkage, não uma média de estatísticas de time.

**Validação:** gate §6 padrão do DC-NB (log-loss/Brier de gols, não a métrica de prop de jogador),
já que a feature entraria no modelo de resultado/gols, não substituiria o scorer_model. Segmentar
por competição (o índice depende de cobertura de escalação prévia, mais fraca em ligas menores).

---

## 2. Hipóteses inéditas motivadas pela leitura cruzada

### H1 — Sinal de jogador agregado bate sinal de time também no modelo de RESULTADO, não só em props

**Motivação:** momentum de jogador passou o gate (AUC 0,68→0,71); momentum de time foi reprovado
repetidas vezes (documentado em `bateria-momentum-jogador.md` e no histórico §9). Toda a evidência
de "granularidade de jogador > granularidade de time" no projeto, até hoje, vem de mercados de PROP
(goleador/assistência/finalizações) — nunca foi testada como insumo do modelo principal de
resultado/gols (DC-NB). FSAA (Agente 3) e o ângulo de agregação-por-jogador do SciSkill (Agente 2)
reforçam esse padrão de fora do projeto, mas nenhum dos 7 agentes propôs explicitamente "leve o
sinal de jogador para o modelo de resultado", só para props.

**Fundamentação:** a razão estrutural mais provável de "time falha, jogador passa" é que agregados
de time (posse, forma de time, PPDA de time) são estatísticas já amplamente capturadas — de forma
mais estável e com menos ruído — pelo Elo/GAP ratings, então qualquer sinal adicional de time tende
a ser redundante ou é puro ruído de amostra pequena por jogo. Sinal de jogador, ao contrário, captura
algo que o rating de time genuinamente não vê: **quem está em campo** (line-up specific), que muda
jogo a jogo independente da força histórica do time. Isso é consistente com C4 acima, mas H1 é a
hipótese mais ampla e mais barata de testar primeiro: não precisa do shrinkage bayesiano completo do
FSAA, só precisa testar se a soma/média do `player_momentum_score` (já calculado e aprovado para o
scorer_model) do XI titular provável, como feature adicional do DC-NB de gols, reduz log-loss.

**Implementação:** reusar a feature de momentum de jogador já validada (não recriar do zero);
agregar por soma ponderada por minutos históricos dos titulares prováveis (via lineup, quando
disponível antes do corte point-in-time) em uma única feature por time por jogo; adicionar como
`base_feat` extra no `predictor.py` (171ª feature, mesmo padrão do GAP ratings de clube).

**Validação:** gate §6 completo — CV temporal expanding, comparar contra produção real, segmentar
por competição/continente/força de time (hipótese adicional: o ganho, se existir, deve ser maior em
jogos com escalações voláteis — copas com rotação de time reserva — do que em ligas de pontos
corridos com XI estável, o que seria uma assinatura útil para distinguir sinal real de acaso).

### H2 — A falha da isotônica no 1X2 pode ser artefato do método, não evidência de que o DC-NB já está bem calibrado

**Motivação:** o CLAUDE.md/memória registra "calibração isotônica reprovada para 1X2" como se fosse
evidência de que o DC-NB já é bem calibrado nesse mercado. O Agente 6 aponta uma explicação
técnica alternativa: isotônica one-vs-rest quebra a restrição soma=1 em problema multiclasse — ou
seja, o teste que reprovou pode ter reprovado por causa da ferramenta errada, não por ausência de
viés real. Nenhum agente cruzou isso explicitamente com a pergunta "será que há um viés real no 1X2
que só apareceria com o método certo?" — é uma lacuna que só aparece lendo o achado do Agente 6
contra a interpretação implícita do histórico do projeto.

**Fundamentação:** o benchmark citado pelo Agente 6 (Dirichlet vence 8/8 métricas contra 10 outros
métodos em 21 datasets × 11 modelos, Kull et al. NeurIPS 2019) é peer-reviewed e não específico de
futebol, mas é a família certa para o formato do problema (3 classes, soma=1) — diferente de
isotônica one-vs-rest, que nunca deveria ter sido o teste definitivo para essa pergunta.

**Implementação:** treinar Dirichlet calibration sobre as probabilidades OOF do 1X2 (DC-NB) via CV
temporal, olhando primeiro a curva de calibração/ECE por classe (casa/empate/fora) antes de decidir
se há algo a corrigir — o objetivo do primeiro passo é diagnóstico (existe viés residual?), não
promoção imediata.

**Validação:** gate §6 padrão, com atenção extra ao segmento "empate" — já documentado como
"reprovado calibrar τ, empate já calibrado" (bateria H1-H4 2026-07-21) para o *modelo* em si; testar
se isso continua verdadeiro quando a calibração é avaliada com a métrica certa (Dirichlet) em vez da
errada (isotônica one-vs-rest). Se Dirichlet também não achar viés, é uma confirmação mais forte
(com o método certo) do que a reprovação atual da isotônica — vale nos dois sentidos.

### H3 — Bias correction segmentada deveria priorizar exatamente as competições novas da expansão 2026, não todas

**Motivação:** o artefato de clube de produção cobre 72 torneios/5589 times (retreino 2026-07-22),
resultado de uma expansão de 60→68→83 competições ao longo de julho de 2026. O `bias_correction.joblib`
é global (confirmado por grep, Agente 6). Nenhum agente perguntou explicitamente "o viés é
provavelmente maior justamente nas competições coletadas por último, com menos histórico e volume
de dado de treino" — mas é a leitura natural de cruzar o achado de código do Agente 6 com o
cronograma de expansão documentado no CLAUDE.md.

**Fundamentação:** um `bias_correction` ajustado sobre um pool dominado por competições com mais
histórico (60 ligas originais) tende a generalizar mal para as ~15-23 competições adicionadas nas
últimas duas ondas (2026-07-19 e 2026-07-22), que têm menos jogos no artefato de produção e
potencialmente características de mercado diferentes (overround mais alto, conforme achado do
Agente 3 sobre ligas menores) — é exatamente o cenário em que uma correção pooled "dilui" o ajuste
correto para o segmento pequeno.

**Implementação:** não é uma correção segmentada por TODAS as 72 competições de uma vez (custo alto,
risco de overfit em ligas com poucos jogos) — é um teste dirigido: comparar erro de calibração
(ECE/Brier) do `bias_correction` atual especificamente nas competições da expansão 2026-07-19/22
contra as competições originais das 60 ligas; se a diferença for grande, o caso de negócio para
segmentar fica concreto e priorizável (em vez de "talvez ajude em algum lugar").

**Validação:** diagnóstico primeiro (sem código de produção, só análise), depois — se confirmado —
implementar segmentação com shrinkage por volume (ver C2), sob gate §6, comparando contra a correção
global atual competição por competição.

### H4 — Choques discretos de "mudança de regime" (técnico novo + janela de transferência) em vez de decaimento contínuo

**Motivação:** time-decay contínuo já foi testado e reprovado (`sweep-pesos-gols`: "xi ótimo colapsa
perto de 0"); o Perfil Elo-condicionado (slope contínuo de resposta ao Elo) também reprovou; o
prior comensurável period-specific do Agente 1 (mesma família, precisão de evolução por período)
provavelmente colide com os dois. Só o Adaptive Glicko-2 do Agente 1 tem um componente
estruturalmente diferente que ninguém isolou: "choques estruturais" que aumentam incerteza (RD/σ)
em eventos discretos específicos — não uma função contínua do tempo. O Agente 5 separadamente
achou "flag de continuidade de comissão técnica" (mudança de treinador) como parte de um bloco de
features vencedoras no Kaggle. Nenhum dos dois cruzou isso: "o que já falhou foi tratar toda
mudança de força como um processo contínuo suave; o que ainda não foi testado é tratá-la como um
evento discreto e raro".

**Fundamentação:** a razão mais provável de o time-decay contínuo e o slope Elo-condicionado terem
falhado é que a maior parte do tempo a força de um time É estável — um decaimento contínuo aplicado
a todo momento "gasta" sinal em ruído na maioria dos jogos para capturar uma mudança real que só
acontece ocasionalmente (troca de técnico, janela de transferência ativa). Um flag esparso e
discreto evita esse custo: só ativa a "reescala de confiança" nos poucos jogos em que há motivo
concreto para achar que a força mudou mais rápido que o normal.

**Implementação:** feature binária/categórica `regime_change_flag` = 1 se (a) troca de técnico nos
últimos N jogos (dado de coach já parcialmente disponível via lineups da API-Football, conforme
achado do Agente 5) OU (b) janela de transferência recente com atividade de mercado relevante
(proxy: mudança abrupta no valor de mercado do elenco, se/quando Transfermarkt for integrado — ver
Fase 3 do roadmap; na ausência dessa fonte, usar só o sinal de troca de técnico como piloto barato).
Uso: não como peso de decaimento, mas como interação — dar menos peso ao histórico pré-mudança
especificamente nesse jogo, sem alterar a curva de decaimento dos outros milhares de jogos.

**Validação:** gate §6, comparando explicitamente contra os dois experimentos já reprovados (time-decay
contínuo, Perfil Elo-condicionado) para deixar claro no relatório final que esta é uma hipótese
estruturalmente distinta (evento discreto vs. função contínua) e não uma terceira tentativa do
mesmo mecanismo com nome novo.

### H5 — Valor de mercado do elenco só deveria ser testado no recorte onde o Elo é estruturalmente mais fraco: mata-mata cross-divisão/continental

**Motivação:** o Agente 7 já sinaliza que o valor de mercado de elenco é "colinear com Elo; útil em
mata-mata cross-divisão", mas trata isso como uma nota de rodapé dentro de uma tabela de fonte de
dado, não como um desenho de experimento. O projeto já tem uma feature específica para esse
cenário exato — `mata_mata_agregado` / `GET /api/aggregate` (qualificação/agregado em mata-mata
ida-volta, §17 do doc-mestre) — que ninguém cruzou com a observação do Agente 7.

**Fundamentação:** Elo por competição (K por competição, conforme CLAUDE.md) é bom para comparar
times DENTRO da mesma liga, mas em copas continentais que cruzam divisões/países diferentes
(Champions/Libertadores/copas domésticas com times de divisões distintas), a comparabilidade entre
Elos calculados em populações diferentes é a fraqueza estrutural mais óbvia do sistema — exatamente
onde um sinal externo e absoluto (valor de mercado, não relativo à liga de origem) tem o maior
potencial de adicionar informação sem ser redundante. Testar valor de mercado como feature universal
arriscaria diluir esse ganho estreito em ruído/colinearidade nos 90%+ dos jogos de liga doméstica
onde o Elo já é confiável.

**Implementação:** escopar o experimento deliberadamente aos jogos que já passam por
`predict_aggregate`/mata-mata ida-volta cross-divisão (recorte pequeno mas já identificável no
dataset) — não ao dataset inteiro. Fonte de dado: Transfermarkt via scraper de terceiro (Apify/
Parse.bot, conforme Agente 7), com o risco de ToS já sinalizado e a decisão de uso comercial
reservada ao dono do projeto.

**Validação:** gate §6 restrito ao segmento de mata-mata cross-divisão (amostra menor, então o
limiar de significância deve ser mais conservador); comparar contra o `mata_mata_agregado` atual
(só Elo) com e sem a feature de valor de mercado.

---

## 3. Ranking preliminar

Escala qualitativa: Alto / Médio / Baixo (ganho, robustez); Alta/Média/Baixa (facilidade — Alta =
fácil); Nenhum/Baixo/Médio/Alto (custo de dado, Nenhum = já disponível).

| nome | ganho potencial | facilidade | custo de dado | robustez da evidência | aderência seleção | aderência clube | score geral |
|---|---|---|---|---|---|---|---|
| Calibração Dirichlet (1X2, first-scorer) | Médio-Alto | Alta | Nenhum | Alta (peer-reviewed, benchmark amplo) | Alta | Alta | **Prioritário** |
| Calibração Beta (chutes) | Médio | Alta | Nenhum | Alta (peer-reviewed) | Alta | Alta | **Prioritário** |
| Dedução de rating por lesão ponderada por status | Médio | Média | Nenhum (`/injuries` já coletado) | Média (medido, replicado por 2 competidores Kaggle) | Média | Alta | **Prioritário** |
| Elo ajustado por margem de gols (ClubElo/SPI) | Incerto (nunca medido) | Alta | Nenhum | Baixa (sem benchmark publicado, só ausência de teste anterior) | Alta | Alta | **Promissor** |
| Auditoria leakage-aware da cascata (chutes→escanteios→cartões) | Alto (se achar leak) | Alta (é auditoria) | Nenhum | Alta (paper 2026, mesmo domínio de mercado) | Média | Alta | **Prioritário** |
| Bias correction segmentada por liga (C2/H3) | Médio-Alto (mais em clube) | Média | Nenhum | Média (lacuna de processo confirmada, ganho não medido) | Baixa | Alta | **Promissor** |
| PSI — monitoramento de drift | Alto (processo) | Alta | Nenhum | Alta (prática de indústria consolidada) | Alta | Alta | **Prioritário (processo)** |
| Rating unificado (margem + ausência, C1) | Médio-Alto (efeito composto) | Média | Nenhum (status) / Médio (valor de mercado) | Média (dois sinais fracos combinados) | Média | Alta | **Promissor** |
| Sinal de jogador agregado no DC-NB de gols (H1) | Médio-Alto | Média | Nenhum (reusa momentum já aprovado) | Média (extrapolação de um resultado já aprovado em outro mercado) | Média | Alta | **Promissor** |
| G-Elo (formalização acadêmica) | Baixo-Médio | Alta | Nenhum | Média (paper formal, sem número de futebol específico) | Alta | Alta | Especulativo |
| Purged K-Fold + Embargo | Médio (endurecimento) | Média | Nenhum | Alta (literatura financeira consolidada) | Alta | Alta | Especulativo (processo) |
| RPS como métrica complementar | Baixo (não é ganho de modelo) | Alta | Nenhum | Média (debate acadêmico ativo) | Alta | Alta | Especulativo (processo) |
| Índice de qualidade do XI titular / FSAA adaptado (C4) | Médio-Alto | Baixa-Média | Nenhum (proxy) | Média (adaptação de método, não replicação literal) | Baixa (escalação de seleção mais rala) | Alta | Especulativo |
| Compound Poisson escanteios + regressão de forma | Alto (backtest real, Sharpe 3,07) | Baixa | Nenhum | Alta (validado contra odds reais HKJC) | Média | Alta | Especulativo (custo de implementação alto) |
| Adaptive Glicko-2 completo | Médio | Baixa | Nenhum | Média (honesto: fica atrás do mercado) | Alta | Alta | Especulativo |
| Choque de regime discreto (H4) | Incerto | Média | Nenhum (piloto) / Médio (versão completa) | Baixa (hipótese nova, sem precedente direto) | Média | Alta | Especulativo |
| BN causal estendida (posse→chutes→gols, C3) | Médio | Baixa | Nenhum | Média (valida em handicap, não gols diretamente) | Baixa | Alta | Especulativo |
| Tweedie GLM para cartões vermelhos | Baixo-Médio | Média | Nenhum | Baixa (nenhuma aplicação publicada a futebol) | Média | Alta | Especulativo |
| Venn-Abers (incerteza por predição) | Baixo (é feature de produto, não de acurácia) | Média | Nenhum | Média (literatura sólida, sem aplicação a futebol) | Alta | Alta | Especulativo |
| Ausência ponderada por valor de mercado (Transfermarkt) | Médio | Baixa | Alto (scraper terceiro, ToS, fuzzy match) | Baixa-Média | Baixa | Média | Baixa prioridade (fora do escopo cross-divisão) |
| Valor de mercado em mata-mata cross-divisão (H5) | Médio (escopo estreito) | Baixa | Alto (mesma fonte) | Baixa-Média | Baixa | Média | Baixa prioridade / nicho |
| Clima no kickoff | Baixo | Alta | Baixo | Baixa (efeito historicamente fraco) | Alta | Alta | Baixa prioridade |
| CMP uni/bivariado para gols | Incerto | Baixa (MCMC customizado) | Nenhum | Média (sem número de delta vs NB) | Alta | Alta | Baixa prioridade (custo/benefício ruim agora) |
| Blend Bayesiano modelo+odds | Baixo (perde em acurácia pura vs mercado) | Média | Nenhum (odds já coletadas) | Média (risco de circularidade com Verificador de Bets) | Média | Alta | Baixa prioridade / risco de produto |
| Home advantage por time / variável no tempo | Baixo-Médio | Média | Nenhum | Baixa (estudo descritivo, sem teste preditivo) | Alta | Alta | Baixa prioridade |

---

## 4. Esboço de roadmap em 4 fases

### Fase 1 — Alto impacto, baixo esforço (dado já disponível, implementação de dias)

1. **Calibração Dirichlet no 1X2 e no first-scorer** — único método que respeita soma=1; ataca
   diretamente o mercado onde isotônica falhou e nunca foi recalibrado desde então.
2. **Calibração Beta em chutes** — mesma lógica, para o outro mercado onde isotônica falhou por
   amostra pequena por bin.
3. **Auditoria leakage-aware da cascata chutes→escanteios→cartões** — é checklist, não modelo novo;
   deve rodar antes de qualquer expansão da cascata (C3) para não construir em cima de um vazamento
   não descoberto.
4. **PSI para drift de produção** — lacuna de processo confirmada (nenhum monitoramento hoje);
   barato e evita depender de reclamação de usuário para notar quando `bias_correction` ficou obsoleto.
5. **Diagnóstico de bias correction por competição nova vs. antiga (H3, fase de diagnóstico)** —
   só análise, decide se vale a pena implementar a segmentação completa depois.
6. **Dedução de rating por lesão ponderada por status (binário)** — `/injuries` já coletado, ganho
   medido externamente, só falta virar feature estruturada; começar pela versão binária de status
   (sem valor de mercado) para não depender de fonte nova.

### Fase 2 — Esforço médio (reengenharia de feature/pipeline existente, dado já disponível)

1. **Elo ajustado por margem de gols** — troca no update do Elo já em produção; testar isolado
   antes de combinar com ausência (ver C1).
2. **Rating unificado (C1)** — combinar margem de gols + ausência ponderada, com ablation para
   isolar a contribuição de cada peça.
3. **Sinal de jogador agregado no DC-NB de gols (H1)** — reusa momentum de jogador já aprovado,
   generaliza de prop para o modelo principal de resultado.
4. **Bias correction segmentada por liga com shrinkage por volume (C2/H3, fase de implementação)** —
   só depois do diagnóstico da Fase 1 confirmar que há sinal a capturar.
5. **Purged K-Fold + Embargo** — endurecimento do gate §6, relevante especialmente para os mercados
   recém-expandidos (72 torneios) com risco maior de sobreposição temporal não tratada.
6. **Diagnóstico Dirichlet no 1X2 vs. resultado da isotônica (H2)** — decide se a "aprovação
   implícita" do DC-NB no 1X2 é real ou artefato de método.

### Fase 3 — Avançado, depende de nova fonte de dado ou de MCMC/engenharia pesada

1. **Compound Poisson para escanteios + regressão de forma sobre supremacia** — maior evidência
   quantitativa de todo o levantamento (backtest real contra odds HKJC), mas exige PyMC/Stan e
   replicação cuidadosa da estrutura de regressão auxiliar no parâmetro de forma.
2. **Índice de qualidade do XI titular / FSAA adaptado (C4)** — depende de escalação prévia
   confiável (mais fraca em ligas menores e seleção) e do shrinkage bayesiano completo, não só do
   momentum já existente.
3. **Ausência ponderada por valor de mercado + valor de mercado em mata-mata cross-divisão (H5)** —
   depende de integrar Transfermarkt via scraper de terceiro (custo, risco de ToS, fuzzy match de
   nome de jogador contra a base da API-Football) — decisão de uso comercial cabe ao dono do projeto.
4. **Adaptive Glicko-2 completo (MOV+dominance+shocks+ordinal)** — mais rico que o Elo por margem
   isolado, mas exige reformular o sistema de rating inteiro, não só o update.
5. **Choque de regime discreto — versão completa (H4)** — a versão piloto (só troca de técnico) é
   Fase 2; a versão completa (+ atividade de transferência) depende da mesma fonte de valor de
   mercado da Fase 3.
6. **Clima no kickoff (Visual Crossing/OpenWeatherMap)** — custo trivial mas depende de integrar uma
   fonte nova; baixo ganho esperado, mas barato o suficiente para não competir por prioridade com
   itens de maior impacto.

### Fase 4 — Experimental / pesquisa (alto risco, alto custo de implementação, evidência fraca ou incerta)

1. **BN causal estendida posse→chutes→SOT→gols (C3, extensão completa)** — reformulação estrutural
   da cascata; só depois da auditoria de leakage e com desenho cuidadoso do corte point-in-time para
   posse histórica.
2. **CMP uni/bivariado para dispersão de gols** — MCMC customizado com likelihood intratável, sem
   número de delta de log-loss vs. NB publicado; alto custo de engenharia para ganho não quantificado.
3. **Blend Bayesiano modelo+odds** — evidência mista (perde em acurácia pura vs. mercado) e risco
   real de circularidade com o Verificador de Bets/detector de EV; exige isolamento cuidadoso de
   pipeline antes de qualquer teste.
4. **Extensão Sarmanov do Dixon-Coles** — ataca o núcleo estatístico do DC-NB de produção, mas só
   validado em futebol feminino; qualquer teste teria efeito cascata sobre todos os mercados
   derivados, exige cautela extra.
5. **Frailty model de tempos de escanteio (rajadas)** — provável gap de dado (timestamp de
   escanteio dentro da partida pode não existir na API-Football); confirmar disponibilidade antes de
   alocar qualquer esforço de engenharia.
6. **Venn-Abers (incerteza por predição)** — não é ganho de acurácia, é uma funcionalidade de
   produto (intervalo de confiança por previsão); avaliar como feature de UI, não como melhoria de
   modelo, e só depois que os itens de Fase 1-2 estiverem entregues.

---

## Achado mais importante deste round

A leitura cruzada dos 7 domínios aponta um padrão que nenhum agente isolado formulou: o projeto tem
uma evidência forte e pouco explorada — "sinal de jogador bate sinal de time" (momentum de jogador
passou, momentum de time reprovou repetidas vezes) — que hoje só é usada dentro dos mercados de prop
(scorer/assist/finalizações), nunca como insumo do modelo principal de resultado/gols. FSAA (Agente
3), o ângulo de agregação por jogador do SciSkill (Agente 2) e a observação geral do Agente 6 sobre
granularidade convergem, de fora do projeto, para a mesma conclusão. A hipótese H1 (testar o
momentum de jogador já aprovado como feature agregada do DC-NB de gols, não só do scorer_model) é
provavelmente o candidato de maior razão custo/benefício de todo o levantamento — zero fonte de
dado nova, reusa uma feature já validada sob o gate, e ataca diretamente o padrão mais consistente
que a história de ~60 hipóteses reprovadas do projeto revela. Em segundo lugar, o par
Beta/Dirichlet (Agente 6) é a resposta mais direta e barata às duas únicas falhas documentadas de
calibração (chutes e 1X2), e deveria ser resolvido antes de qualquer outro trabalho de calibração
mais sofisticado (Venn-Abers, blend com odds).
