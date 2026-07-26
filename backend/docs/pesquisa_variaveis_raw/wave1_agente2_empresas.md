# Wave 1 — Agente 2: métricas avançadas de empresas de análise de futebol

**Data:** 2026-07-24
**Escopo:** o que StatsBomb/Hudl, Opta/Stats Perform, SciSports, Wyscout, SkillCorner e Impect
publicam sobre suas próprias metodologias de rating/métricas avançadas (xG/xA/xT, ratings de
jogador proprietários, tracking físico/tático, modelos de previsão comercializados). Fonte
majoritariamente institucional (blogs de produto, whitepapers, páginas de metodologia) — **tratar
como marketing, não peer-review**, exceto onde indicado um paper acadêmico independente.

## Tabela de candidatos

| nome | descrição | fórmula/como é calculada | mercados impactados | ganho esperado (qualitativo + número se a fonte citar) | complexidade de implementação | fonte de dado (API-Football já traz? senão, qual fonte) | disponibilidade (seleção/clube/ambos) | evidência (link + por quê confiar / alerta de marketing) |
|---|---|---|---|---|---|---|---|---|
| **xG "avançado" com freeze-frame** (StatsBomb/Opta) | xG que soma à distância/ângulo do chute a posição de goleiro, defensores e atacantes no frame do chute (dado posicional, não só o box-score do evento) | Modelo supervisionado (GBM/regressão logística) treinado em milhões de chutes rotulados, com features de freeze-frame (posição de até 22 jogadores no momento do chute) além de distância/ângulo/altura de impacto; pênalti fixado em ~0,78 xG histórico | Resultado (DC-NB), BTTS, O/U gols | Qualitativo: StatsBomb afirma ser o xG "mais calibrado" do mercado por causa do freeze-frame; **nenhum número de log-loss/Brier público** — só comparação indireta em paper acadêmico (StatsBomb citado como benchmark de melhor calibração entre providers públicos) | Alta (exigiria não só a métrica, mas o dado posicional subjacente) | **Não.** API-Football não traz freeze-frame/posição de jogadores no chute — só teria acesso ao xG final como número pronto, se comercializado | Ambos (produto comercial cobre ligas de clube; seleção teria cobertura pior) | https://statsbomb.com (via redirect hudl.com) — descrição de produto sem paper público; comparação de calibração aparece só em paper terceiro (arXiv Bayes-xG) citando StatsBomb como benchmark, não é validação própria divulgada. **Marcar como marketing** para a parte qualitativa. |
| **Expected Threat — xT** (popularizado por Karun Singh, replicado por Stats Perform/StatsBomb/Soccerment) | Valor de ameaça por zona do campo (grade 12×8 ou 16×12); ação de passe/condução vale a diferença de xT entre zona de origem e destino | Cadeia de Markov: probabilidade de transição entre zonas + probabilidade de finalizar a partir de cada zona, resolvida por iteração de valor (value iteration) sobre um grafo de estados-zona | Resultado (via feature agregada de "ameaça média gerada/permitida"), possivelmente handicap | Qualitativo apenas — é um framework de atribuição de valor a ações, não um preditor de resultado com número de acurácia publicado pelos criadores | Alta — precisa de sequência de eventos com coordenadas x/y de cada passe/condução por toda a partida, não só o placar/box-score | **Não.** Requer stream de eventos com localização — API-Football não fornece x/y de passes/conduções, só contagens agregadas | Ambos, em tese, mas só onde há dado de eventos com coordenadas (nenhuma fonte atual do projeto tem isso) | https://soccermatics.medium.com/explaining-expected-threat-cbc775d97935 (blog técnico do criador do conceito original, não é vendor, mas também não é paper com validação estatística de ganho preditivo em resultado de partida — é uma proposta metodológica) |
| **On-Ball Value — OBV** (StatsBomb/Hudl) | Modelo de "possession state value": cada ação (passe, condução, drible, ação defensiva) recebe um valor = mudança na probabilidade de gol a favor menos mudança na probabilidade de gol contra, com componentes ofensivo e defensivo treinados separadamente | Modelo treinado no **xG do próprio StatsBomb** (não em gols brutos, p/ reduzir variância) sobre features de localização (x/y, distância/ângulo ao gol), tipo de jogada (aberta vs. bola parada), pressão defensiva e parte do corpo; explicitamente **exclui features de posse histórica** para não confundir com força do time | Resultado, handicap (via força agregada ofensiva/defensiva por equipe) | Qualitativo — StatsBomb afirma ser "mensuravelmente melhor que a concorrência" em whitepaper pago a clientes; **nenhum número público de AUC/log-loss/R²** foi encontrado | Alta — exige stream de eventos completo com coordenadas, não só box-score agregado | **Não.** Mesma barreira do xT: precisa de eventos com x/y, que a API-Football não fornece | Ambos (cobertura comercial: top-5 ligas europeias + 140 competições, majoritariamente clube) | https://www.hudl.com/blog/introducing-on-ball-value-obv — página de produto; confirma modelo e desenho de features mas **nenhuma métrica de validação divulgada publicamente** — tratar como marketing |
| **xGOT / Shooting Goals Added (SGA)** (Stats Perform/Opta) | xG "corrigido" pela execução do chute: usa a posição onde a bola cruzaria a linha do gol (não só se foi no alvo) para estimar probabilidade de gol dado que o chute foi no alvo; SGA = xGOT − xG, mede se o jogador finaliza melhor ou pior que a qualidade da chance | Regressão logística treinada em centenas de milhares de chutes no alvo, usando xG original + coordenadas do ponto de cruzamento da linha do gol + ângulo visível do gol naquele ponto | Props de jogador (goleador/finalizações) — não é orientado a resultado de partida | Qualitativo — Stats Perform o descreve como métrica de "execução do chutador" separando sorte/qualidade de chance de habilidade de finalização; sem número de AUC/log-loss público para prop de jogador | Alta — precisa da coordenada exata de onde o chute cruzaria a linha do gol (dado de rastreamento do chute), inexistente no box-score da API-Football | Ambos em tese, mas sem fonte de dado disponível hoje | https://www.statsperform.com/insights/introducing-expected-goals-on-target-xgot/ — página de metodologia do vendor, sem validação estatística pública própria |
| **Opta Power Rankings** (Stats Perform) | Rating de força de time em escala 0–100, arquitetura hierárquica tipo Elo, ajustado por resultado de +2,5 milhões de jogos desde 1990; usado como input (junto com odds de mercado) num modelo de simulação Monte Carlo do restante da temporada | Elo hierárquico (troca de pontos entre mandante/visitante conforme resultado, com fator K provavelmente ajustado por competição/margem) + blend com odds de mercado de apostas para estimar probabilidade de W/D/L, simulado milhares de vezes | Resultado (1X2), classificação final de campeonato | **Número citado pela própria fonte: ~60–65% de acurácia em previsão de resultado (W/D/L) globalmente** — mas é combinado com odds de mercado, não é o rating isolado | Média — a arquitetura (Elo hierárquico) é essencialmente o que o projeto já roda; o diferencial é o blend com odds, já testado no projeto (ver colisão abaixo) | Odds de clube parcial via `collect_club_odds_forward.py`; combinar Elo+odds não depende de fonte nova | Ambos | https://theanalyst.com/articles/opta-football-predictions — página do vendor cita a % de acurácia mas sem log-loss/calibração/segmentação por competição; **tratar com ceticismo, é número de marketing sem metodologia de validação divulgada** |
| **SciSkill Index** (SciSports) | Rating composto por jogador (ofensivo + defensivo) derivado de dados de evento e tracking em ~2.000 jogos/semana e 244 ligas; a soma/agregação do SciSkill dos titulares de cada time serve de proxy de força de equipe | Algoritmo proprietário não detalhado publicamente ("industry-validated, elaborate version of Elo" — descrição do próprio vendor); combina rating ofensivo e defensivo por jogador, ajustado por nível relativo de liga | Resultado (via força agregada do XI titular) | **Número citado pela própria fonte: ROI médio de 9,4% batendo as casas de apostas** usando o SciSkill do line-up esperado — número forte, mas **sem paper de validação estatística pública, é claim de marketing/vendas** | Alta — exige rating por jogador de fonte própria (tracking+evento), inexistente no projeto; teria de ser aproximado com Elo de time (já existe) sem o componente de jogador | **Não.** Precisa de dado de jogador individual em escala (nome, posição, minutagem) cruzado com tracking — API-Football não cobre isso a esse nível | Ambos (cobertura declarada de 244 ligas) | https://www.scisports.com/sciskill-index-why-and-how/ e paper relacionado (arXiv 2502.07528, sobre previsão de evolução do SciSkill/ETV) — o paper é sobre *forecasting* do próprio índice, não validação independente do poder preditivo de resultado; **claim de ROI de 9,4% é só do vendor, não replicado externamente** |
| **SkillCorner Physical/Tactical Data** (PSV99, Off-Ball Runs / "Game Intelligence") | Métricas físicas (distância em zonas de velocidade, PSV99 = "peak sprint velocity" percentil 99, contagens de alta intensidade) e táticas (volume/tipo/efetividade de corridas sem bola, normalizado por tempo de posse) extraídas de vídeo de transmissão via visão computacional (sem necessidade de câmeras no estádio) | Modelo de visão computacional (tracking por vídeo de broadcast) + classificação de tipo de corrida (10 categorias) e cálculo de métricas de velocidade/aceleração por jogador-frame | Resultado (indiretamente, via features táticas agregadas de equipe), props de jogador (raro, não é o produto central) | Qualitativo: SkillCorner destaca correlação com "eficácia" de jogadas, mas **nenhum número de AUC/log-loss para previsão de resultado de partida foi encontrado**; achado acadêmico correlato (não do vendor): estudo com dados de tracking em 118 jogos da liga holandesa achou KPIs off-ball como melhor preditor de resultado, com **acurácia de 64,0%** — mesma ordem de grandeza do baseline atual do projeto, não uma melhora clara | Alta — exige vídeo de transmissão de qualidade broadcast processado por CV, fora do escopo de dado do projeto | **Não.** Não é dado de box-score, é extraído de vídeo — a API-Football não fornece nada equivalente | Majoritariamente clube (broadcast de seleção também coberto em grandes torneios, mas cobertura desigual) | https://skillcorner.com/products/football/physical-data e https://medium.com/@SkillCorner/evaluating-off-ball-movement-in-football — página de produto, sem validação estatística própria publicada. O número de 64,0% de acurácia é de um **estudo acadêmico terceiro (Dutch Eredivisie, tracking data)**, não do vendor — citado aqui só como referência de ordem de grandeza, não é o mesmo produto |
| **Packing Rate / Impect** | Mede quantos jogadores adversários são "ultrapassados" (saem da posição relevante entre o passador/condutor e o gol) por passe ou condução; pontua tanto quem executa quanto quem recebe | Fórmula simples e divulgada: `Packing = jogadores adversários ultrapassados / total de ações (passes+conduções)`; só conta defensores que estavam "no escopo" da jogada (entre bola e gol na direção do passe), não todos os 11 | Resultado (via força agregada ofensiva/defensiva de time), possivelmente handicap | **Número citado (fonte acadêmica que estudou o Packing, não o vendor diretamente): correlação de 0,96 com força de equipe** e "redução de conteúdo de informação por ruído" de apenas 0,98 (ou seja, métrica estável) — é o achado mais quantificado de todos os candidatos desta tabela | Alta — precisa de posição x/y de todos os jogadores em campo no momento do passe/condução (dado de tracking ou event data com freeze-frame), não só o resultado do passe | **Não.** API-Football não traz posição de jogadores em campo por evento | Ambos em tese (Impect cobre principalmente clube europeu) | https://the-footballanalyst.com/packing-rate-football-statistics-explained/ e artigo indexado no arXiv (Identification of relevant performance indicators in round-robin tournaments) — a correlação de 0,96 aparece em fonte que **analisa** o Packing, dá mais confiança que puro press-release do vendor, mas ainda não é um teste de ganho incremental de log-loss num modelo de previsão real |

## Cruzamento com reprovados

- **xG "avançado" (freeze-frame) e xGOT/SGA colidem diretamente com a hipótese já reprovada 3× de
  xG como feature do DC-NB** (documentado como "muro de dados": cobertura concentrada em anos/ligas
  recentes gera confounding, não sinal causal). O ângulo aqui (freeze-frame/posição no chute,
  execução do chutador) não muda o diagnóstico — é uma variante *mais* difícil de obter (exige dado
  posicional que nem o xG simples tinha), então **não haveria motivo para esperar resultado
  diferente**; na prática nem é testável, pois a API-Football não expõe esse dado. Não propor
  reteste sem uma fonte de dado nova que resolva a cobertura, não só a sofisticação da fórmula.
- **Opta Power Rankings é, na descrição do próprio vendor, um Elo hierárquico combinado com odds de
  mercado.** O projeto já usa Elo como feature central (158/170 `base_feats`) e já teve uma bateria
  inteira dedicada a de-vig/valor de odds de mercado (W1-W4, 2026-07-22) que **não achou edge robusto
  em nenhum mercado/liga**, e a comparação nosso-modelo-vs-vendor (§21 do doc-mestre, 8117 jogos)
  já mostrou nosso modelo vencendo em log-loss/Brier/ECE/acurácia em 26/26 competições contra um
  produto comercial nativo da mesma API. Não há ângulo novo aqui — é reconfirmação do que já se
  sabe, não um candidato a testar.
- **pi-ratings e Berrar ratings já foram testados e perderam contra o DC-NB de produção em 54k jogos
  de clube.** O SciSkill Index da SciSports é descrito pelo próprio vendor como "uma versão mais
  elaborada do Elo" — mesma família conceitual dos ratings já reprovados, mas com um diferencial
  genuíno: é agregado **por jogador** (soma do XI titular), não por time inteiro como pi-rating/
  Berrar. Esse é o único ângulo potencialmente novo (granularidade de jogador via lineup), mas a
  fonte de dado necessária (rating de jogador em escala, de tracking+evento) não existe no projeto
  hoje — não dá para testar sem comprar o produto ou substituir por um proxy grosseiro (ex.: Elo do
  time inteiro já cobre o mesmo território).
- **Momentum de equipe já foi reprovado repetidamente; momentum de jogador passou (AUC goleador
  0,68→0,71).** O Packing Rate e o SciSkill Index de jogador são adjacentes ao "momentum de jogador
  que passou" no sentido de granularidade (jogador, não time), mas medem coisa diferente (qualidade/
  posicionamento, não tendência recente) — não é o mesmo teste, mas reforça que sinal em nível de
  jogador tende a ser mais promissor que em nível de time neste projeto, o que é consistente com o
  motivo de ambos aparecerem aqui como "interessante mas sem fonte de dado".
- **Nenhum dos 8 candidatos desta tabela tem fonte de dado disponível na API-Football hoje.** Todos
  exigem ou (a) stream de eventos com coordenadas x/y (xT, OBV, Packing), ou (b) dado de tracking/
  vídeo de transmissão (SkillCorner), ou (c) rating proprietário de jogador não publicado (SciSkill),
  ou (d) coordenada exata de cruzamento do chute na linha do gol (xGOT). Isso não é um "quase-empate"
  como as hipóteses de rating já testadas — é um bloqueio de disponibilidade de dado, categoricamente
  diferente de "testamos e perdeu". Se algum desses métodos merecer teste real no futuro, o gargalo
  prático é conseguir a fonte de dado (parceria/compra com StatsBomb/Opta/SkillCorner/Impect), não a
  engenharia de feature em si.

## Fontes consultadas

- https://statsbomb.com/articles/soccer/introducing-on-ball-value-obv/ (redireciona para
  https://www.hudl.com/blog/introducing-on-ball-value-obv)
- https://www.hudl.com/blog/expected-goals-xg-explained
- https://blogarchive.statsbomb.com/articles/soccer/on-ball-value-obv-in-the-2020-21-premier-league/
- https://theanalyst.com/articles/opta-football-predictions
- https://theanalyst.com/articles/power-rankings-your-club-ranked
- https://kiqiq.com/blog/opta-power-rankings
- https://www.statsperform.com/insights/introducing-expected-goals-on-target-xgot/
- https://www.statsperform.com/insights/enhancing-expected-goals-on-target/
- https://theanalyst.com/articles/what-are-expected-goals-on-target-xgot
- https://www.scisports.com/sciskill-index-why-and-how/
- https://researchoutreach.org/articles/scisports-football-data-intelligence/
- https://arxiv.org/html/2502.07528v3 (forecasting SciSkill/ETV — SciSports)
- https://skillcorner.com/products/football/physical-data
- https://skillcorner.com/products/physical-data-football
- https://medium.com/@SkillCorner/evaluating-off-ball-movement-in-football-e85cb1af48c7
- https://medium.com/@SkillCorner/game-intelligence-the-other-97-b5485b14d7a7
- https://the-footballanalyst.com/packing-rate-football-statistics-explained/
- https://arxiv.org/pdf/2003.03774 (Identification of relevant performance indicators in round-robin tournaments — cita correlação Packing×força de equipe)
- https://soccermatics.medium.com/explaining-expected-threat-cbc775d97935 (David Sumpter, explicação do xT — não é vendor)
- https://medium.com/after-the-full-time-whistle/explaining-expected-threat-xt-in-football-analytics-using-markov-models-its-history-part-i-20d4d31e2ea9
- https://www.hudl.com/blog/generate-accurate-football-predictions-by-training-your-algorithms-with-wyscout-data
- https://www.hudl.com/products/wyscout e https://en.wikipedia.org/wiki/Wyscout
- Estudo acadêmico terceiro sobre tracking data holandesa (KPIs off-ball, acurácia 64,0%) e estudo
  Bundesliga EPV vs. xG (Frontiers, acurácia 0,656 para xG pós-jogo) — encontrados via busca, citados
  como referência de ordem de grandeza de ganho preditivo relatado na literatura para métricas do
  mesmo tipo (não são publicações do vendor, mas ajudam a calibrar expectativa de quanto essas
  métricas de fato adicionam sobre baseline).
