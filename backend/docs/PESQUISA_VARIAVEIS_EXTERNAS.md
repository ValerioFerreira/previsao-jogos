# Pesquisa ampla de novas variáveis/dados/abordagens — ApostaInfo

**Data:** 2026-07-24
**Escopo:** pesquisa externa (papers, empresas, blogs, open source, Kaggle, engenharia de ML,
fontes de dados) para identificar candidatos capazes de aumentar a capacidade preditiva dos
modelos em produção. 7 agentes de domínio rodaram em paralelo; este arquivo é a compilação bruta
dos 7 achados (diário citável, análogo a `PESQUISA_CLUBES.md`). A curadoria de mérito (redundância,
viés, viabilidade, ranking, roadmap) está em `RELATORIO_NOVAS_VARIAVEIS.md`, produzida por um
comitê técnico de 3 agentes em 2 rounds a partir deste material.

**Nada aqui foi implementado ou testado sob o gate §6** — é levantamento bruto, não veredito.

---

## Índice mestre

Todos os candidatos de variável/abordagem encontrados pelos 7 agentes, uma linha por candidato.
Tabelas completas (fórmula, ganho esperado, evidência, link) estão nas seções por agente abaixo.

| nome | agente/domínio | disponibilidade | complexidade | nota-chave |
|---|---|---|---|---|
| CMP univariado dispersão team-specific (spike-and-slab) | 1 Papers | Ambos | Alta | Sem colisão — cobre sub-dispersão que a NB de produção não cobre |
| CMP bivariado (correlação casa/fora via efeito aleatório) | 1 Papers | Ambos | Alta | Sem colisão — alternativa ao τ do Dixon-Coles |
| Compound Poisson/geom-Poisson escanteios + regressão de forma | 1 Papers | Ambos | Alta | Backtest real (Sharpe 3,07 vs 1,52 Poisson simples, odds HKJC) |
| Frailty model tempos de escanteio (rajadas) | 1 Papers | Ambos (se dado existir) | Alta | Provável gap de dado — precisa timestamp de escanteio |
| Adaptive Glicko-2 (MOV+dominance+shocks+ordinal) | 1 Papers | Ambos | Média | +4,04% Brier vs Glicko-2 padrão; fica ~1-3% atrás do mercado |
| G-Elo (Adjacent-Categories, margem discretizada) | 1 Papers | Ambos | Baixa/Média | Drop-in replacement do update do Elo já em produção |
| Score-driven rating genérico (GAS) | 1 Papers | Ambos | Alta | **Sem ângulo novo** — mesma família do Koopman já reprovado |
| Prior comensurável period-specific (dynamic discrete-time) | 1 Papers | Ambos | Alta | Colide parcialmente com time-decay e Perfil Elo-condicionado reprovados |
| Blend Bayesiano modelo+odds (combinação convexa) | 1 Papers | Ambos (odds já coletadas) | Média | Perde em acurácia pura vs mercado; risco de circularidade com detector de EV |
| Bayesian Network causal posse→chutes→SOT→gols (Asian Handicap) | 1 Papers | Ambos | Alta | Usa pi-rating (já reprovado); ângulo novo é a estrutura causal em cascata |
| Home advantage específico por time (não constante global) | 1 Papers | Ambos | Baixa | Sem teste preditivo publicado, é estudo descritivo |
| Extensão Sarmanov do Dixon-Coles | 1 Papers | Ambos | Alta | Só validado em futebol feminino |
| xG avançado com freeze-frame | 2 Empresas | Bloqueado | Alta | Colide com xG já reprovado 3x; dado inexistente na API-Football |
| Expected Threat (xT) | 2 Empresas / 3 Blogs | Bloqueado | Alta | Exige coordenadas x/y de toda ação — muro de dados |
| On-Ball Value (OBV) | 2 Empresas / 3 Blogs | Bloqueado | Alta | Mesma barreira do xT |
| xGOT / Shooting Goals Added | 2 Empresas | Bloqueado | Alta | Exige coordenada de cruzamento na linha do gol |
| Opta Power Rankings | 2 Empresas | — | Média | **Sem ângulo novo** — Elo hierárquico + odds, já testado (W1-W4 sem edge) |
| SciSkill Index (rating por jogador, SciSports) | 2 Empresas | Bloqueado | Alta | Único ângulo novo é granularidade de jogador; sem fonte de dado |
| SkillCorner Physical/Tactical Data | 2 Empresas | Bloqueado | Alta | Exige vídeo broadcast + CV; sem tier self-service |
| Packing Rate (Impect) | 2 Empresas | Bloqueado | Alta | Correlação 0,96 com força de equipe (fonte terceira); exige tracking x/y |
| FSAA — Finishing Skill Above Average (shrinkage bayesiano) | 3 Blogs | Clube (proxy) | Alta | Adaptável ao proxy de finalizações já coletado, não ao xG literal |
| Expected Shot Danger (xSD, 2 estágios com bloqueados) | 3 Blogs | Clube | Alta | Exige coordenada XY do chute; só `shots.blocked` agregado disponível |
| Overround por liga como sinal de confiança/eficiência | 3 Blogs | Ambos | Baixa | Feature de ponderação para ligas com mercado mais raso |
| Vantagem de mandante variável no tempo (tendência, não constante) | 3 Blogs | Ambos | Média | Ângulo novo; pode já estar implicitamente capturado pelos retreinos |
| Ajuste Rue-Salvesen ("efeito psicológico") | 4 Open source | Ambos | Baixa | Primo do Perfil Elo-condicionado já reprovado; próprio autor do pacote avisa ganho mínimo |
| **Elo ajustado por margem de gols (estilo ClubElo/SPI)** | 4 Open source | Ambos | Baixa/Média | **Único ângulo sem sobreposição — barato, sem dado novo, nunca testado no projeto** |
| CMP para dispersão de gols (estático) | 4 Open source | Ambos | Média | Mesma família da dispersão dinâmica já reprovada por Tail-ECE |
| VAEP/xT (`socceraction`) | 4 Open source | Bloqueado | Alta | Muro de dados |
| OpenSkill/TrueSkill | 4 Open source | Ambos | Média | Mesma categoria de pi-ratings/Berrar já reprovados |
| Bradley-Terry | 4 Open source | Ambos | Baixa | Estritamente menos informativo que o DC-NB já em produção |
| Hurdle model para gols | 4 Open source | Ambos | Média | Mesma conclusão do estudo BTTS (DC já ótimo); predição nem implementada na lib-fonte |
| **Dedução de rating por lesão ponderada por status** | 5 Kaggle | Ambos | Média | Ganho medido (-0,0081 Brier); `/injuries` já coletado, só falta virar feature |
| Flag de continuidade de comissão técnica | 5 Kaggle | Ambos | Baixa | Não isolado no ganho agregado da fonte (~-0,001 log-loss em bloco) |
| Flag "mesma competição" como interação (não peso de decaimento) | 5 Kaggle | Ambos | Média | Parcialmente redundante com downweight de amistosos já aprovado |
| Rating externo pré-calculado (tipo clubElo/SPI) | 5 Kaggle | Ambos | Alta | Quebra a regra de "quase 100% API-Football"; baixa prioridade |
| "Quality wins" — bônus de força de adversário em camadas | 5 Kaggle | Ambos | Baixa | Risco alto de colinearidade com o Elo contínuo já em produção |
| Ensemble por diversidade de sementes (bagging, não stacking) | 5 Kaggle | Ambos | Baixa | Ganho questionável para GBM determinístico (não é rede neural) |
| Calibração Beta | 6 Engenharia | Ambos | Baixa | Candidato direto para os casos onde isotônica reprovou (chutes) |
| Calibração de Dirichlet (multiclasse nativa) | 6 Engenharia | Ambos | Média | Único método que respeita soma=1 — candidato pro 1X2 nunca calibrado pós-hoc |
| Venn-Abers (calibração com intervalo) | 6 Engenharia | Ambos | Média | Extrapolação de domínio; sem aplicação a futebol encontrada |
| Purged K-Fold + Embargo | 6 Engenharia | Ambos | Média | Endurecimento do gate §6, não descoberta de mercado |
| Workflow leakage-aware mercados secundários (LaLiga, 2026) | 6 Engenharia | Ambos | Baixa (auditoria) | Correspondência quase perfeita com a cascata chutes→escanteios→cartões |
| PSI — monitoramento de drift em produção | 6 Engenharia | Ambos | Baixa-média | Lacuna de processo confirmada — nada documentado hoje |
| RPS como métrica complementar de gate | 6 Engenharia | Ambos | Baixa | Métrica secundária, não substitui log-loss |
| Tweedie GLM (Poisson-Gama) para cartões vermelhos | 6 Engenharia | Ambos | Média | Especulativo — sem aplicação publicada a futebol |
| **Bias correction segmentada por liga/mercado** | 6 Engenharia | Ambos (mais clube) | Média | Lacuna de processo confirmada por leitura de código — hoje é global |
| Imputação estruturada (MICE/KNN) para features com missing | 6 Engenharia | Ambos (mais clube) | Média-alta | Vale auditoria de código antes — não confirmado se já é tratado upstream |
| Clima no kickoff (temp/precip/vento) | 7 Fontes de dados | Ambos | Baixa | Custo trivial, ganho esperado pequeno |
| Valor de mercado de elenco (total e gap) | 7 Fontes de dados | Ambos (mais clube) | Média | Colinear com Elo; útil em mata-mata cross-divisão |
| Ausência ponderada por valor de mercado do jogador | 7 Fontes de dados | Ambos (mais clube) | Média | Combina `/injuries` já existente com peso de importância — hoje é binário |
| xG/nota via FotMob (fonte alternativa) | 7 Fontes de dados | Ambos | Média-alta | Não resolve o problema de fundo — xG já reprovado 3x |
| Árbitro com granularidade maior (por competição/mando) | 7 Fontes de dados | Ambos | Baixa-média | Ganho marginal — é segmentação, não sinal novo |
| Importância de jogo via posição na tabela (dead rubber) | 7 Fontes de dados | Ambos | Baixa | Não precisa de fonte nova — derivável do histórico já coletado |

**Tabela de fontes de dados** (14 fontes avaliadas: SkillCorner, Second Spectrum, Tracab, Visual
Crossing, OpenWeatherMap, Transfermarkt, Understat, SofaScore, FBref, FotMob, WhoScored,
Sportmonks/referees, OddAlerts/referees, Catapult/STATSports, PhysioRoom) — ver seção do Agente 7
abaixo para a tabela completa com custo/cobertura/prioridade.

---

## Agente 1 — Papers acadêmicos

**Método:** ~20 buscas semânticas via `firecrawl_research_search_papers` cobrindo outcome
prediction, extensões de Dixon-Coles, xG, modelos bayesianos hierárquicos, escanteios, ratings
(Elo/Glicko/pi-ratings/GAS), BTTS/O-U/handicap/placar exato, calibração, in-play, dependência
bivariada de contagens, GNNs, cartões, eficiência de mercado, EPV/xT, home advantage, decaimento
temporal. Leitura de texto completo nos 8 candidatos mais fortes. 13 candidatos, mínimo 5 cumprido.

**Achados mais fortes:** compound Poisson para escanteios com backtest real contra odds HKJC
(Sharpe 3,07 vs 1,52 do Poisson simples); CMP uni/bivariado (cobre sub-dispersão, algo que a NB de
produção não cobre); G-Elo (generalização formal de baixo risco do Elo já em produção); blend
Bayesiano modelo+odds (ângulo novo dado que o projeto agora tem odds reais via §22, com ressalva de
risco de circularidade).

Tabela completa de 13 candidatos, seção "Cruzamento com reprovados" e 32 fontes consultadas:
ver `pesquisa_variaveis_raw/wave1_agente1_papers.md`.

---

## Agente 2 — Empresas de análise de futebol

**Método:** WebSearch + `firecrawl_scrape` em páginas de produto/metodologia de StatsBomb/Hudl,
Opta/Stats Perform, SciSports, SkillCorner, Impect. Material tratado como marketing, não
peer-review, exceto onde há paper acadêmico independente citando o método.

**Achado central:** nenhum dos 8 candidatos (xG avançado, xT, OBV, xGOT, Opta Power Rankings,
SciSkill Index, SkillCorner físico/tático, Packing Rate) tem fonte de dado disponível na
API-Football hoje — é um bloqueio categórico de disponibilidade, diferente de "testamos e
perdeu". O achado mais quantificado é o Packing Rate (correlação 0,96 com força de equipe, fonte
que analisa o método, não só o vendor), mas exige posição x/y de jogadores por passe.

Tabela completa, seção "Cruzamento com reprovados" e fontes: ver
`pesquisa_variaveis_raw/wave1_agente2_empresas.md`.

---

## Agente 3 — Blogs técnicos e artigos especializados

**Método:** curadoria anual de Jan Van Haaren como índice, leitura integral de posts de Martin
Eastwood (penaltyblog), Marc Lamberts, e busca ampla em PT/EN/ES (~17 queries). Conteúdo em
português/espanhol majoritariamente institucional, sem metodologia própria testada.

**Achados mais fortes:** FSAA (habilidade de finalização com shrinkage bayesiano, complementar ao
momentum de jogador que já passou o gate — mas depende de xG por chute, precisa adaptação ao proxy
de finalizações já coletado); comparação de métodos de de-vig em 250M linhas de odds reais
(confirmação externa independente de que o projeto já fechou corretamente o tema em §20); vantagem
de mandante variável no tempo (ângulo novo, não testado como tendência temporal explícita).

Tabela completa, cruzamento e fontes: ver `pesquisa_variaveis_raw/wave1_agente3_blogs.md`.

---

## Agente 4 — Repositórios open source

**Método:** busca em GitHub (`firecrawl_research_search_github`) por soccerAction/VAEP/xT,
mplsoccer, kloppy, pacotes de modelagem (`goalmodel`, `regista`), sistemas de rating alternativos
(OpenSkill/TrueSkill), repositórios de competições passadas. Atenção a issues/discussions de
projetos maduros.

**Achado central:** o único ângulo sem sobreposição direta com o histórico do projeto é o **Elo
ajustado por margem de gols** (estilo ClubElo/FiveThirtyEight SPI) — barato, sem dado novo, nunca
testado no projeto. Todo o resto do ecossistema mais "badalado" (socceraction/VAEP/xT, kloppy)
esbarra no mesmo muro de dados que já reprovou xG 3 vezes.

Tabela completa, cruzamento e fontes: ver `pesquisa_variaveis_raw/wave1_agente4_opensource.md`.

---

## Agente 5 — Competições de Machine Learning (Kaggle)

**Método:** competição central "Football Match Probability Prediction" (Octosport/Sportmonks,
>150k partidas), competição secundária "March Machine Learning Mania" (NCAA, usada como proxy de
rigor metodológico). `firecrawl_scrape` necessário (páginas Kaggle são SPA).

**Achado mais concreto:** dedução de rating por lesão ponderada por status (ganho medido e
replicado por 2 competidores independentes; `/injuries` já é coletado pelo projeto, só falta virar
feature estruturada). **Achado metodológico mais importante:** confirmação independente da
armadilha de CV aleatória — mesmo a solução vencedora da competição mais rigorosa de futebol do
Kaggle usa KFold aleatório para desenvolvimento interno de features, validando externamente por que
o gate §6 (CV temporal expanding) é a escolha certa.

Tabela completa, armadilha metodológica detalhada e fontes: ver
`pesquisa_variaveis_raw/wave1_agente5_kaggle.md`.

---

## Agente 6 — Engenharia de features e ML aplicado à previsão esportiva

**Método:** foco em técnica de produção (calibração, missing data, leakage, drift, ensembling),
não achado de variável nova. Inclui 2 achados por leitura direta do código do projeto (grep em
`predictor.py` e `build_bias_correction.py`).

**Achados mais fortes:** calibração Beta e Dirichlet como substitutas paramétricas da isotônica
especificamente nos dois casos onde ela reprovou (chutes = amostra pequena; 1X2 = multiclasse, onde
isotônica one-vs-rest quebra a restrição soma-1); confirmação de que `bias_correction.joblib` é
global, sem segmentação por liga, apesar de 72 torneios heterogêneos em produção de clube; ausência
de qualquer monitoramento de drift (PSI) documentado; paper de 2026 sobre workflow leakage-aware
para exatamente os mercados da cascata do projeto (shots/corners/cards/fouls).

Tabela completa de 10 candidatos, cruzamento e fontes: ver
`pesquisa_variaveis_raw/wave1_agente6_feature_eng.md`.

---

## Agente 7 — Fontes de dados comerciais/gratuitas ainda não usadas

**Método:** WebSearch/WebFetch em documentação de API e pricing de 14 fontes (tracking,
clima, valor de mercado, xG alternativo, árbitro, GPS/fisiológico, lesões).

**As 3 fontes mais promissoras:** dados climáticos históricos (Visual Crossing/OpenWeatherMap,
custo trivial, cruzável via `venue`+`date` já existente, ganho esperado pequeno); Transfermarkt via
scraper de terceiro (valor de mercado de elenco e ausências ponderadas por valor — variável
genuinamente nova, risco de ToS real); FotMob (xG/nota de jogador com cobertura de ligas maior que
Understat, mas não resolve o problema de fundo do xG já reprovado). Tracking de posicionamento
(SkillCorner/Second Spectrum/Tracab) é o dado mais rico mas só vendido por negociação enterprise,
inviável no porte atual. GPS/fisiológico é 100% proprietário de clube, sem marketplace público.

Tabela completa de variáveis + tabela completa de 14 fontes de dados (custo/cobertura/API/
prioridade), cruzamento e fontes: ver `pesquisa_variaveis_raw/wave1_agente7_fontes_dados.md`.
