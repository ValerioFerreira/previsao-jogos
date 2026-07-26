# Wave 1 — Agente 5: Competições de Machine Learning (Kaggle e similares)

Data: 2026-07-24

## Escopo e método

Pesquisa restrita a competições de ML sobre previsão esportiva (futebol e, por extensão
explícita do briefing, "esportes" em geral — usei o March Machine Learning Mania/NCAA como
proxy de competição de apostas esportivas de alto rigor metodológico, já que é a competição
Kaggle de esporte mais longeva e mais documentada em write-ups públicos de 1º lugar). Fontes
primárias raspadas via `firecrawl_scrape` (páginas Kaggle são SPA, `WebFetch` puro não renderiza
o conteúdo — confirmado empiricamente, ver §Fontes). Termos de busca usados (não exaustivo):
"Kaggle football prediction competition top solution feature engineering", "Kaggle European
Soccer Database notebook feature engineering", "Football Match Probability Prediction 1st place
solution", "Kaggle Football Match Probability Prediction validation strategy", "kaggle soccer
match prediction feature importance days rest squad value elo xgboost", "kaggle sports betting
odds prediction competition value bet machine learning", "Kaggle March Machine Learning Mania
winning solution write-up Massey ratings logistic regression", "kaggle football prediction
competition lessons learned soccer", entre outras variações.

Competição central: **Football Match Probability Prediction** (Kaggle, organizada por
Octosport/Sportmonks, 2022, >150.000 partidas de 2019-2021, >860 ligas, >9.500 times, 382
equipes competindo — a competição de futebol mais rigorosa e documentada do Kaggle, com
prêmio em dinheiro e leaderboard privado). Competição secundária usada como proxy metodológico:
**March Machine Learning Mania** (NCAA basquete, anual desde 2014, dezenas de write-ups
públicos de 1º lugar por edição — usei a edição 2026, mais recente e mais bem documentada).

## Tabela de candidatos

| nome | descrição | fórmula/como é calculada | mercados impactados | ganho esperado | complexidade | fonte de dado (API-Football já traz? senão qual) | disponibilidade (seleção/clube/ambos) | evidência (link + o que a solução mostrou) |
|---|---|---|---|---|---|---|---|---|
| Dedução de rating por lesão ponderada por status | Em vez de só exibir lesões (o projeto já tem `/injuries`, mas como informação de UI, não como feature do modelo — ver `backend/docs` e `fixture_fetch.py`), subtrair do rating pré-jogo do time uma penalidade proporcional à gravidade/confirmação da lesão de jogadores-chave (titular provável) | Penalidade = Σ (BPR/impacto do jogador ausente) × peso_status, com peso_status categórico (ex. "fora da temporada"=1.0, "fora"=0.75, "dúvida"=0.5); resultado subtraído do Elo/rating do time antes de calcular λ/μ | Resultado 1X2, handicap, todos os mercados de gols (indireto via rating) | Marginal mas real e mensurado: -0,0081 Brier (masculino) / -0,0041 Brier (geral) na fonte — ordem de grandeza pequena mas positiva e teoricamente distinta do que já foi testado | média (a API-Football já retorna `/injuries`; falta status/gravidade estruturado e mapear "titular provável" x impacto — hoje o dado é só exibido, não normalizado numa penalidade de rating) | API-Football já traz `/injuries` (usado hoje só para exibição); falta granularidade de status ("dúvida" vs "confirmado fora") e medida de impacto por jogador (ex. minutos jogados/rating do jogador ausente) | ambos (mas exige granularidade de escalação — API-Football é mais fraca nisso para ligas menores) | [March Mania 2026 — 1º lugar](https://www.kaggle.com/competitions/march-machine-learning-mania-2026/writeups/march-machine-learning-mania-2026-1st-place-solut): dedução manual de rating por status de lesão (rotowire + rating de jogador), ganho medido e citado explicitamente pelo autor; outro competidor (Ryan Armstrong, comentário no mesmo write-up) replicou e mediu +0,00022 no score final |
| Flag de continuidade de comissão técnica no histórico recente | Para cada jogo do histórico recente (l3/l5/l10) do time, marcar se foi disputado sob o mesmo técnico atual (não é "quanto tempo desde a troca", é uma flag binária de comparabilidade do histórico) | `mesmo_treinador_i = 1 se treinador(jogo_i) == treinador_atual senão 0`, usada como peso/filtro na forma recente (ex.: só contar gols/resultado do jogo no cálculo de forma se `mesmo_treinador=1`, ou como feature de interação separada) | Resultado 1X2, forma recente (indireto) | Não quantificado isoladamente pela fonte (a solução só reporta o ganho agregado de um bloco de 6 features novas, "features A-Z", ~-0,001 log-loss no total) — plausível mas não isolado | baixa (a API-Football já retorna `coach_id`/nome do técnico por partida no lineup; é só um join histórico) | API-Football já traz `coach`/staff por fixture (via lineups) — precisa confirmar cobertura em ligas menores | ambos | [1º lugar — Football Match Probability Prediction](https://www.kaggle.com/code/seraquevence/1st-place-solution-football-prob-pred): feature `home_team_history_SAME_coaX_i` explicitamente citada como parte do bloco de features que "reduziu o loss em quase 0,001 (0,996→0,995)" — mas o autor não isola o efeito de cada sub-feature, é um bloco conjunto |
| Flag "mesma competição" como interação explícita (não como peso de decaimento) | Restringir/marcar explicitamente se cada jogo do histórico recente foi na mesma competição do confronto atual, multiplicando essa flag pelo rating/Elo do jogo histórico e por mando de campo — ângulo distinto do "downweight de amistosos" já testado (que é um peso contínuo de decaimento, não uma flag categórica multiplicativa combinada com mando de campo) | `feature = ELO_historico_i × is_mandante_i × mesma_competicao_i` (replica literalmente as `feature_A..Z` do 1º lugar) | Resultado 1X2, forma recente | Contribuiu para os ~0,001 de log-loss do bloco de features do 1º lugar, mas não isolado; risco de ser majoritariamente redundante com o K por competição que o Elo do projeto já usa | média (é uma interação multiplicativa simples, mas exige reestruturar a pipeline de forma recente para separar por competição por partida, não só por peso agregado) | 100% derivável do dataset já coletado (Elo, mando, id de competição por partida) — sem API nova | ambos | [1º lugar — Football Match Probability Prediction](https://www.kaggle.com/code/seraquevence/1st-place-solution-football-prob-pred), bloco "feature_A" a "feature_Z" — nota importante: **cruza parcialmente com "downweight de amistosos" já testado e aprovado como único ganho pequeno** (ver `sweep-pesos-gols.md`); o ângulo novo aqui é o filtro binário por competição em vez de peso contínuo, e a interação com mando de campo, não testada isoladamente no projeto |
| Rating de força externo pré-calculado (ex. clubElo/SPI-like) como feature complementar ao Elo próprio | Importar um rating de time já calculado por terceiros (fora do próprio histórico de partidas do projeto) como feature adicional ao lado do Elo interno, em vez de tentar reconstruir Elo/pi-ratings/Berrar internamente (todos já reprovados) | Feature = valor do rating externo na data do jogo (ou diferença do rating externo entre os times), usado como input adicional do DC-NB, não como substituto | Resultado 1X2, todos os mercados que dependem de λ/μ | Incerto — a fonte mostra ganho para ratings externos profissionais (Pomeroy/Sagarin/Moore) vs Elo próprio no basquete, mas o projeto já teve "arquitetura atual venceu tudo, sem exceção de push" na pesquisa de clubes (§13), o que sugere baixa probabilidade de ganho | alta (**quebra a regra de ouro de "quase 100% API-Football"** — exige nova fonte de dado externa, scraping/parsing de site de terceiro, manutenção de outra pipeline) | **NÃO vem da API-Football** — precisaria de fonte nova tipo clubelo.com, FiveThirtyEight SPI (descontinuado) ou similar; alto custo de manutenção e risco de licenciamento | ambos (mas cobertura de ratings públicos de clube é mais fraca em ligas menores) | [March Mania 2023 — top 1% gold write-up](https://medium.com/@maze508/top-1-gold-kaggle-march-machine-learning-mania-2023-solution-writeup-2c0273a62a78): autor tentou Elo próprio e relatou "não consegui fazer funcionar melhor que só usar ratings externos" (Pomeroy/Moore/Sagarin) |
| "Quality wins" — bônus de força de adversário em camadas (tiers), separado do Elo/rating contínuo | Sistema de pontos categóricos por qualidade do adversário batido (ex.: tier 1 = adversário forte, tier 4 = adversário fraco/sem torneio), somado como feature de "vitórias de qualidade" na temporada, além (não em vez) do rating contínuo | `quality_pts_diff = Σ(pontos_tier do adversário em cada vitória do time A) − Σ(idem time B)` | Resultado 1X2 | Baixo/incerto — correlação reportada de r=0,46 (masculino) e r=0,64 (feminino) com o resultado, mas é quase certamente colinear com o Elo/rating contínuo que o projeto já tem (que já captura força do adversário de forma contínua e mais fina) | baixa (é um agregado categórico simples sobre dados já coletados) | derivável dos dados já coletados (times/torneios/temporada) — sem API nova | ambos | [March Mania 2026 — 1º lugar](https://www.kaggle.com/competitions/march-machine-learning-mania-2026/writeups/march-machine-learning-mania-2026-1st-place-solut): feature usada no modelo vencedor, mas o próprio autor não testa isoladamente contra um rating contínuo puro — **risco alto de redundância com o Elo do projeto**, priorizar por último |
| Ensemble por diversidade de sementes/hiperparâmetros do mesmo tipo de modelo (bagging, não stacking heterogêneo) | Treinar N variações do mesmo modelo (mesma arquitetura-base, hiperparâmetros levemente diferentes, sementes diferentes) e fazer média simples das probabilidades — distinto de "stacking/ensemble heterogêneo" (já reprovado no projeto) | `pred_final = média(pred_modelo_1, ..., pred_modelo_N)`, N pequeno (4 no caso da fonte) | Resultado 1X2 | Baixo — a fonte só reporta que "parar de conseguir reduzir o log-loss, então empilhei os mesmos LSTMs com pequenas modificações até o log-loss começar a piorar de novo"; ganho não quantificado isoladamente, soa mais como redução de variância de treino (relevante para redes neurais, MUITO menos para GBM determinístico que o projeto já usa) | baixa (mecanicamente simples) | N/A — é técnica de treino, não feature | ambos | [1º lugar — Football Match Probability Prediction](https://www.kaggle.com/code/seraquevence/1st-place-solution-football-prob-pred): "no final, o resultado final foi a média de quatro modelos LSTM" — **atenção: isto é bagging de variância de rede neural, ângulo diferente do "ensemble/stacking" já reprovado no projeto (que testava blend de modelos heterogêneos e MLP/deep learning tabular, ambos reprovados)**; mas o ganho prático para um GBM/DC-NB determinístico é questionável e provavelmente marginal — prioridade baixa |

## Cruzamento com reprovados

- **pi-ratings / Berrar ratings / ratings alternativos ao Elo interno**: um dos poucos artigos
  encontrados fora do Kaggle-competição-formal (blog "thexgfootballclub", citando CatBoost +
  pi-ratings com 55,82% de acurácia num dataset de 2017) reforça pi-ratings como candidato — mas
  isso **já está na lista de ~60 hipóteses reprovadas do projeto** (pi-ratings, Berrar ratings). Não
  proponho de novo; cito só para registrar que a literatura de competição não trouxe nada que
  mude essa conclusão.
- **Calibração pós-hoc (isotônica) no resultado 1X2**: a solução vencedora do March Mania 2026
  usa calibração isotônica sobre as previsões OOF do 1X2 (masculino/feminino) e reporta ganho
  real (Brier 0,1850→0,1822 masculino, 0,1390→0,1357 feminino). Isso **parece contradizer** o
  achado do projeto ("calibração pós-hoc no resultado 1X2: reprovada, piora"). Mas há uma
  diferença estrutural importante: o March Mania é um problema **binário** (vitória/derrota, sem
  empate) resolvido por regressão de margem de vitória, enquanto o 1X2 do projeto é **multinomial
  de 3 classes com empate explícito** — o projeto já testou calibração pós-hoc especificamente
  nesse contexto multinomial e reprovou. Não é o mesmo experimento; cito para registrar a diferença
  de estrutura do problema, não como refutação do achado do projeto.
- **Ensemble/stacking heterogêneo, MLP/deep learning tabular**: mencionados na literatura de
  competição (o 1º lugar do Football Match Probability Prediction usa LSTM, que é a categoria
  "deep learning tabular/sequencial" já reprovada no projeto para dados de futebol tabular — e o
  próprio autor da solução vencedora admite que "uma LSTM enorme piora" e que a acurácia final
  ficou em ~50,15%, "quase aleatório" — **é uma confirmação indireta e independente**, vinda de
  uma fonte que não conhece o projeto, de que arquiteturas de rede neural mais complexas não
  batem abordagens mais simples nesse domínio de dados, indo na mesma direção do achado do
  projeto sobre LightGBM/XGBoost/HistGBM/MLP não baterem o GBM de produção.
- **Time-decay/recência**: contestado dentro da própria literatura de competição — o 1º lugar do
  March Mania 2026 relata que "recompensar desempenho recente" piorou o modelo dele, mas no
  mesmo tópico de comentários outro competidor (Ryan Armstrong) diz "historicamente vi valor em
  dar peso maior a jogos recentes". **Não é conclusivo nem na própria comunidade de competição** —
  isso é consistente com o achado do projeto de que time-decay "nunca ajuda, xi ótimo colapsa perto
  de 0" em gols/ratings, mas mostra que o sinal é genuinamente frágil/dependente do domínio, não
  um erro de implementação do projeto.

## Armadilha metodológica confirmada (importante para o comitê)

A própria competição Football Match Probability Prediction define o split treino/teste como
**temporal** (treino = 1 ano e 5 meses, teste = 7 meses seguintes, sem sobreposição), mas o
notebook de 1º lugar validado internamente usa **KFold aleatório (`sklearn.model_selection.KFold`,
`shuffle=True` em alguns folds)** para todo o treino/validação interna — não CV temporal
expanding. Isso é exatamente a armadilha que o briefing pediu para sinalizar: uma solução pode
vencer o leaderboard privado (que É temporal, então o home-field advantage do "vencer o
leaderboard" força alguma generalização temporal mínima) enquanto todo o desenvolvimento interno
de features/hiperparâmetros foi guiado por CV aleatória, que infla otimisticamente o desempenho
percebido de cada feature durante a iteração. Um participante (Redha C., 16º colocado) levantou
essa exata dúvida na discussão ["Validation strategy"](https://www.kaggle.com/competitions/football-match-probability-prediction/discussion/315706)
e a resposta do organizador foi vaga ("garanta que a correlação entre seu CV loss e o loss do
leaderboard seja alta", sem prescrever CV temporal). Isso reforça — de forma independente e vinda
de fora do projeto — por que o **gate §6** do projeto (CV temporal expanding, point-in-time
estrito) é a escolha metodológica correta e por que resultados de notebooks Kaggle otimizados em
CV aleatória (a maioria dos notebooks públicos revisados) devem ser tratados com ceticismo
adicional antes de qualquer replicação.

Outro ponto relevante: o "sharpening the edges" do 1º lugar do March Mania 2026 (arredondar
previsões ≥97% para 100% e ≤3% para 0%) é uma jogada de **EV negativo deliberada**, ótima para
uma métrica de competição de bracket fixo (Brier score sobre um conjunto fechado de jogos), mas
o oposto do que se quer numa plataforma que expõe probabilidades para o usuário comparar com odds
reais — **não é um candidato, é um anti-padrão a evitar** caso alguém tente replicar táticas de
"otimizar para vencer o leaderboard" no produto real.

## Fontes consultadas

- [Football Match Probability Prediction (competição, Kaggle)](https://www.kaggle.com/competitions/football-match-probability-prediction)
- [1st place solution: Football prob pred (notebook)](https://www.kaggle.com/code/seraquevence/1st-place-solution-football-prob-pred)
- [TOP 7: Football Match Probability Prediction (notebook)](https://www.kaggle.com/code/hamzaouammou/top-7-football-match-probability-prediction/output)
- [Discussão: Validation strategy](https://www.kaggle.com/competitions/football-match-probability-prediction/discussion/315706)
- [Discussão geral da competição (ordenada por votos)](https://www.kaggle.com/competitions/football-match-probability-prediction/discussion?sort=votes)
- [March Machine Learning Mania 2026: 1st Place Solution (write-up oficial Kaggle)](https://www.kaggle.com/competitions/march-machine-learning-mania-2026/writeups/march-machine-learning-mania-2026-1st-place-solut)
- [[Top 1% Gold] Kaggle — March Machine Learning Mania 2023 Solution Writeup (Medium)](https://medium.com/@maze508/top-1-gold-kaggle-march-machine-learning-mania-2023-solution-writeup-2c0273a62a78)
- [Which Machine Learning Models Perform Best for Football Match Prediction? (thexgfootballclub, Substack)](https://thexgfootballclub.substack.com/p/which-machine-learning-models-perform)
- [Football Predictions: Kaggle competition (Sportmonks blog, contexto da competição)](https://www.sportmonks.com/blogs/football-predictions-kaggle-competition/)
- [GitHub — talestsp/football-match-prediction (repositório de participante)](https://github.com/talestsp/football-match-prediction)
- Buscas gerais sem fonte única citável diretamente (usadas para triangular achados): "Kaggle
  European Soccer Database" notebooks de match outcome prediction, "March Machine Learning
  Mania" interviews de 1º/4º lugar de edições anteriores (Andrew Landgraf 2017, Erik Forseth
  2017), "kaggle sports betting odds prediction" (DataBall/NBA, "Can Machine Learning Beat the
  Bookies?").

## Nota sobre ferramentas

`WebFetch` não conseguiu extrair conteúdo de nenhuma página do Kaggle (retorna só o título — as
páginas são SPA client-side rendered). Todo o conteúdo substantivo de notebooks/discussões do
Kaggle neste relatório veio de `firecrawl_scrape` com `waitFor: 4000`, que renderiza JS
corretamente.
