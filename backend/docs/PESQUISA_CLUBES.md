# Pesquisa de Modelos para CLUBES — doc-mestre (branch `clubs`)

> Iniciada 2026-07-15, após conclusão da coleta de clubes (54.072 partidas, 13 competições,
> 2010→2026, tabela `club_match_detail_cache` + espelho local `data/club_raw_cache.sqlite`).
> Diretriz: duas linhas paralelas — **A** (recalibrar arquitetura atual com clubes) e
> **B** (pesquisa do zero, sem viés das decisões históricas). Tudo nesta branch; push só na
> exceção de melhoria comprovada em seleções.

## 0. Dados

| Item | Valor |
|---|---|
| Partidas coletadas | 54.072 (FT/AET/PEN) |
| Competições | Brasileirão A (6.206), Série A ITA (6.081), La Liga (6.080), Premier (6.080), Ligue 1 (5.767), Série B BRA (5.490), Bundesliga (4.912), UEL (4.362), UCL (3.341), UECL (2.100), Copa do Brasil (1.338), Libertadores (1.209), Sul-Americana (1.106) |
| Período | 2010/2011 → 2026 |
| Detalhe por jogo | statistics (box-score **com xG!**), events, lineups, players |
| **xG** | presente no box-score de clubes (cobertura a medir) — em seleções era ~6%; era apontado no doc-central §9 como "única fonte plausível de sinal novo ortogonal ao Elo" |

Pipeline: `scripts/mirror_club_cache.py` (espelho local, zero egress Neon — re-download via API
com cota ociosa) → `scripts/build_clubs_dataset.py` (parse + features com os MESMOS nomes de
coluna do `features_enriched` de seleções, p/ a Linha A rodar a arquitetura atual sem mudanças).

Decisões do dataset:
- Times = `Nome#id` (colisões River Plate ARG×URU etc.).
- Elo de clubes: K liga 20 / copa 24 / continental 28 (+6 em final), multiplicador de margem
  idêntico ao de seleções, HOME_ADV=65, time novo entra 1450 (chega promovido/classificado).
  Europa e América do Sul são componentes desconexos (nunca se enfrentam na base) — ok, o
  elo_diff é sempre intra-componente.
- `neutral=1` só em finais únicas continentais ≥2019 (aproximação documentada).
- Sem corte temporal na saída; `matches_played_before` permite descartar burn-in no treino.

## 1. Linha A — arquitetura atual re-treinada com clubes

Plano: (A1) retreinar DC-NB + cascatas NB/GP + calibradores com `club_features_enriched`,
recalcular hiperparâmetros (r, rho, GBM depth/lr/n) e recalibrar isotônicos; validação temporal
expandindo (gate §6 do doc-central). (A2) aplicar em seleções e comparar com produção.
(A3) reexecutar hipóteses reprovadas com a base ~10× maior no subconjunto com box-score
(54k vs 4.1k jogos): time-decay, forma/momentum, blend DC+HistGBM (BTTS), regressor λ
XGB/LGBM, calibração de resultado, perfil Elo-condicionado, xG-feature, GP vs NB.
Racional: várias reprovações tinham cara de "sem amostra para o sinal aparecer" — o veredito
pode virar com 13× mais jogos com box-score.

## 2. Linha B — pesquisa aberta (sem viés da arquitetura atual)

### 2.1 Revisão de literatura (2026-07-15)

**Consenso da literatura recente** (survey Bunker/Yeung/Fujii 2024; 2017/2023 Soccer Prediction
Challenges; Machine Learning journal):
- **GBM sobre ratings dinâmicos específicos de futebol** é o SOTA em W/D/L com dados só-de-gols:
  CatBoost + pi-ratings = RPS 0,1925 vs bookmakers 0,2020 no Open International Soccer Database
  (bateu as casas!). TabNet + pi-ratings próximo (0,1956) mas não supera GBM.
- **Ratings que a literatura valida** (todas as fórmulas extraídas do survey):
  - **pi-ratings** (Constantinou-Fenton): rating casa/fora por time, atualização por erro de
    saldo esperado com amortecimento log de goleadas; venceu 2017 e (com CatBoost) o pós-challenge.
  - **Berrar ratings**: força ofensiva/defensiva via logística de gols esperados, 4 updates/jogo.
  - **GAP ratings**: ataque/defesa casa/fora por ESTATÍSTICA (chutes, escanteios — não só gols) —
    candidato natural a alimentar nossos mercados de contagem.
- **Modelos estatísticos continuam fortes para PLACAR/mercados**: Poisson bivariado
  (Karlis-Ntzoufras), Double Poisson/Weibull, e sobretudo **state-space dinâmicos**
  (Koopman-Lit 2015, JRSS-A: Poisson bivariado com intensidades estocásticas evoluindo no tempo;
  **retorno positivo comprovado** contra odds na EPL 2010-12; versões score-driven em 2019 IJF).
- Deep learning tabular (TabNet, TFT) **não supera** GBM em datasets tabulares de futebol; DL só
  ganha com dados espaço-temporais (tracking) que não temos.
- Métrica de referência dos challenges: **RPS** (adicionar ao protocolo, além de log-loss/ECE).

Fontes: [survey arXiv 2403.07669](https://arxiv.org/pdf/2403.07669) · [Koopman-Lit JRSS-A](https://academic.oup.com/jrsssa/article/178/1/167/7058470) · [ML journal 2023 challenge](https://link.springer.com/article/10.1007/s10994-024-06608-w) · [state-space bayesiano EPL 2025](https://academic.oup.com/jrsssc/article/74/3/717/7929974)

### 2.2 Candidatos a implementar (ordem de prioridade)

| # | Candidato | Família | Por quê |
|---|---|---|---|
| B1 | **pi-ratings + CatBoost/LGBM** (W/D/L direto + ordered logit) | rating+GBM | SOTA nos challenges; barato |
| B2 | **Berrar ratings + GBM** | rating+GBM | 2º SOTA; ratings O/D alimentam λ/μ |
| B3 | **GAP ratings por estatística** → features p/ contagem | rating | única técnica da literatura desenhada p/ chutes/escanteios |
| B4 | **Dixon-Coles dinâmico** (time-decay ξ otimizado + re-fit rolling) | estatístico | o DC atual é estático; clubes têm 38 jogos/temporada (forma importa mais que em seleções) |
| B5 | **State-space Koopman-Lit** (intensidades AR(1), bivariado) | estatístico | único da literatura com lucro comprovado em backtest |
| B6 | **xG-híbrido**: λ/μ treinados em xG rolling (não gols) | feature nova | xG denso agora existe; era a janela §9.3 do doc-central |
| B7 | **Poisson bivariado Karlis-Ntzoufras** (λ3 de covariância) | estatístico | baseline forte; compara com DC-rho |
| B8 | **Ensemble/stacking** dos melhores (DC + ratings-GBM + odds?) | ensemble | literatura mostra ganho pequeno mas real |
| B9 | TabNet/FT-Transformer (só se B1-B8 saturarem) | DL | baixa prioridade — literatura diz que não bate GBM |

### 2.3 Features novas de clubes (não existiam em seleções)
xG rolling (l5/l10) e xG-diff; congestão de calendário (jogos em 7/14/30 dias — clubes jogam
2×/semana); viagem (venue_city → distância, altitude p/ Libertadores); fase da temporada
(`season_progress`, rodada); contexto de copa (mata-mata, ida/volta, agregado); descanso
assimétrico; densidade de competições simultâneas; árbitro (amostra por árbitro em clubes é
10-50× maior que em seleções — a reprovação de árbitro pode virar).

## 3. Protocolo único de avaliação (as duas linhas)

- **Split temporal expanding**: cortes 0,50→0,85 da linha do tempo (mesma malha do gate §6),
  seed 42, treino sempre estritamente anterior ao teste.
- **Métricas**: log-loss multiclasse (resultado) e da PMF (contagem), **RPS** (novo, padrão da
  literatura), Brier, ECE, MAE de contagem, cobertura de intervalo 80%, Tail-ECE.
- **ROI/EV**: quando aplicável, contra odds do `odds_registry` (cobertura recente apenas).
- **Segmentação**: por competição, por país/continente, por equilíbrio (|elo_diff|), por fase
  (liga×copa×continental), por temporada.
- **Comparação justa**: todo candidato compara contra o MESMO baseline (Linha A retreinada =
  "produção em clubes") no MESMO split. Nada de strawman.

## 4. Diário de experimentos

| Data | Experimento | Resultado | Veredito |
|---|---|---|---|
| 2026-07-15 | Setup: espelho local + dataset builder + doc | 54.072 jogos, 158/158 base_feats, NaN 1,33% | infra pronta |
| 2026-07-15 | **Fase 1 — bateria de resultado (8 candidatos, 49.999 jogos pós burn-in, 5 folds temporais)** | ver tabela abaixo | **A_dc_nb vence** |

### Fase 1 — resultado (H/D/A), ranking médio dos 5 folds

| Modelo | Log-loss | RPS | Brier | ECE | Acc | Tempo |
|---|---|---|---|---|---|---|
| **A_dc_nb** (produção retreinada) | **0,9935** | **0,2029** | **0,5928** | **0,0145** | **0,5227** | 412s |
| B1_cat_pi (CatBoost+pi-ratings) | 0,9985 | 0,2042 | 0,5960 | 0,0175 | 0,5148 | 12s |
| B3_ordlogit_pi (ordered logit+pi) | 0,9998 | 0,2048 | 0,5971 | 0,0164 | 0,5156 | 0s |
| B2_cat_berrar (CatBoost+Berrar) | 1,0072 | 0,2060 | 0,6011 | 0,0230 | 0,5085 | 12s |
| B1_lgbm_pi (LightGBM+pi-ratings) | 1,0134 | 0,2072 | 0,6042 | 0,0270 | 0,5097 | 6s |
| B7_bivpois (Poisson bivariado K&N, por liga) | 1,0407 | 0,2145 | 0,6178 | 0,0297 | 0,4951 | 731s |
| B4_dc_classic (DC clássico estático, por liga) | 1,0413 | 0,2144 | 0,6176 | 0,0284 | 0,4954 | 256s |
| B4_dc_dynamic (DC clássico xi=1,5, por liga) | 1,0599 | 0,2184 | 0,6265 | 0,0402 | 0,4897 | 419s |

**Achado principal:** a arquitetura de PRODUÇÃO (GBM→λ/μ por time via 158 features + acoplamento
Dixon-Coles + NB), simplesmente **retreinada em clubes sem nenhuma mudança estrutural**, bate
TODOS os candidatos da literatura testados — inclusive a combinação apontada como SOTA nos
Soccer Prediction Challenges (CatBoost+pi-ratings). Também vence folgadamente os modelos de
"força pura por time" (DC clássico, Poisson bivariado, ambos ajustados por liga) — confirma o
achado de seleções (Fase 7 do doc-central): força pura perde para GBM+features ricas.
**Responde a pergunta 1 da diretriz, parcialmente**: a arquitetura segue sendo a melhor
disponível — mas ainda não sabemos se seus HIPERPARÂMETROS (profundidade/nº árvores/rho) são
ótimos para o volume 5× maior de clubes (isso é a Fase 2.5, tuning).

**Segmentação (A_dc_nb, log-loss por segmento):** melhor em jogos desequilibrados (elo_desequil
0,888) e nas competições de elite (Champions League 0,921) — como em seleções, o Elo domina.
Pior em ligas nacionais equilibradas (Brasileirão B 1,046, elo_equil 1,061) — esperado, é onde
a incerteza estrutural é maior. ECE por segmento é baixo em toda parte (1,7%-7,5%), sem sinal de
descalibração sistemática por competição.

**xi do DC dinâmico piora** (0,0599 vs 1,041 do estático) — contrário à intuição de que "clubes
jogam mais, forma deveria pesar mais"; o time-decay como implementado (via MLE conjunto) não
ajuda aqui, consistente com o achado de seleções de que decay só ajudou finalizações, não
resultado. **Não repetir DC-dinâmico simples — testar decay embutido nas FEATURES de forma
(rolling l3/l5/l10, já presentes no base_feats) em vez de no peso da verossimilhança** (fica
registrado para Fase 4.1).

**Poisson bivariado** (λ3 de covariância) essencialmente empata com DC clássico — a correlação
positiva fraca de placares não ajuda no agregado, replicando o achado de seleções (Fase 1 do
doc-central: acoplamento aposentado em escanteios pelo mesmo motivo).

### Fase 2 — Contagem, calibração, tuning DC (Linha A completa)

**2.1 Cascata de contagem** (finalizações→escanteios/cartões, ortogonalização de estilo,
35.208 jogos com box-score, 5 folds):

| Mercado | Log-loss | MAE | Cobertura 80% |
|---|---|---|---|
| Finalizações | 3,1902 | 4,615 | 86,6% |
| Finalizações a gol | 2,5502 | 2,494 | 85,5% |
| Escanteios | 2,6328 | 2,698 | 88,2% |
| Cartões | 2,2249 | 1,824 | 83,9% |

Todos com cobertura de intervalo 80% próxima do nominal (83,9%-88,2%) — calibração honesta,
sem sinal de descalibração sistemática, mesmo com 8,6× mais jogos com box-score que seleções.

**2.5 Tuning de hiperparâmetros do DC-NB** (18 configs × 5 folds = 90 fits): **a configuração
de PRODUÇÃO (n_estimators=100, max_depth=3, learning_rate=0.05) é a MELHOR do grid**
(log-loss 0,993758) — a 2ª colocada (200,3,0.03 → 0,993778) é estatisticamente indistinguível
(Δ=0,00002). Configs mais profundas/com mais árvores **pioram** (300,5,0.05 → 1,008707, pior
do grid). **Resposta definitiva à pergunta 1 da diretriz**: os hiperparâmetros da arquitetura
já estavam no ponto ótimo — 5-9× mais dados de clubes não desloca o ponto ótimo de
complexidade do modelo. Isso também torna o teste de "finetune" da Fase 3 (que usou os
hiperparâmetros de produção por já serem o candidato natural) validamente equivalente ao
baseline — não precisa reexecução.

## 5. Conclusão consolidada — respondendo à diretriz original

**Pergunta 1 (a arquitetura atual continua a melhor com mais dados de clubes?):** **SIM,
inequivocamente.** DC-NB de produção venceu 7 candidatos da Linha B na Fase 1 (incl. o SOTA
da literatura, CatBoost+pi-ratings), venceu a bateria avançada da Fase 6 (sweep extensivo,
state-space, ensemble, deep learning tabular) e seus hiperparâmetros já eram os ótimos
(Fase 2.5). Nenhuma das 9 hipóteses reprovadas em seleções reverteu com mais dados, exceto
o blend BTTS (Fase 4), que passou a valer.

**Pergunta 2 (o conhecimento de clubes melhora as previsões de seleções?):** **NÃO, na forma
testada.** Zero-shot (só clubes) piora bastante (0/5 folds); pooled é um empate estatístico
(delta≈0); transferência de hiperparâmetros é redundante (já são os mesmos). **Não há
exceção de push a aplicar** — nada bateu a produção real de seleções sob o gate §6.

**Achado que abre uma porta:** o blend DC+HistGBM no mercado de BTTS passou a valer com a
base de clubes (4/5 folds) — não testado ainda em seleções; candidato a investigação futura
sob o próprio pipeline de seleções (fora do escopo desta pesquisa de clubes).

## 6. Rodada 2026-07-19 — 12 hipóteses no dataset de 60 ligas (191.580 jogos)

> Nota de auditoria: o commit `033ae30` (mesmo dia, sessão anterior) alegava atualizar esta
> seção mas só trouxe os scripts (`clubs_hyp{4,5,6,10}_*.py`, `clubs_new_hyp_ablation.py`) —
> o diário nunca foi escrito aqui. Retroativamente registrado agora (fonte: histórico dos
> scripts + `DOCUMENTACAO_CENTRAL.md` §16 do branch `main`, que tem o relato completo dessa
> sessão incluindo os 3 mercados novos entregues em produção). Números abaixo são os mesmos
> já publicados em `main`, só espelhados aqui pra manter o diário desta branch completo.

Coleta expandida pra 60 competições nesse dia; dataset de pesquisa saiu de 54.072 jogos/13
competições (Fase 1-8, 2026-07-15) para **191.580 jogos/60 ligas** (cobertura box-score 71%,
xG 14,1%). Protocolo idêntico (`research_clubs/protocol.py`, gate ≥4/5 folds melhoram E
delta<-0.001). Nenhuma das 12 hipóteses passou o gate:

| # | Hipótese | Veredito | Nota |
|---|---|---|---|
| 1 | Re-rodar Fase 4/5/6 completas no dataset 60 ligas | NÃO EXECUTADO (ficou pra esta rodada, §7) | — |
| 2 | Blend com odds reais de clube | BLOQUEADO | `club_odds_registry` ainda com volume insuficiente |
| 3 | Pooling hierárquico Elo-diff por liga (shrinkage empírico-Bayesiano) | misto | 5/5 folds melhoram, delta=-0,0004 (abaixo do limiar -0,001) |
| 4 | Lineup novelty (desfalque real vs XI habitual) | REPROVADO | 3/5 folds, delta~0,0000 |
| 5 | Correlação ida-volta em mata-mata | CONFIRMADO (diagnóstico, não é modelo) | corr(margem leg1,leg2)=-0,132 (n=1.702); vira candidato a mercado de qualificação agregada (não construído) |
| 6 | xG como mercado próprio (O/U) | VIÁVEL, aguardar mais dado | cobertura80=0,975, MAE=0,89 gol, amostra 14% ainda pequena |
| 7 | Proxy de lesões no resultado | BLOQUEADO | zero dado de `/injuries` cacheado pra clube |
| 8 | Efeito derby/rivalidade (mesma cidade-sede) | misto | 4/5 folds melhoram, delta~0,0000 |
| 9 | GAP-ratings revisitado (60 ligas) | NÃO EXECUTADO (ficou pra esta rodada, §7) | — |
| 10 | Calibração isotônica por bucket de \|elo_diff\| | REPROVADO | logloss piora em 5/5 folds (+0,003 a +0,014) |
| 11 | Home advantage por lotação de estádio | BLOQUEADO | api-football não expõe `attendance` |
| 12 | Momentum de goleiro pra BTTS/clean-sheet | NÃO EXECUTADO (ficou pra esta rodada, §7) | — |

Também entregues nessa sessão (produção, fora do escopo de pesquisa): 3 mercados novos
(1º/2º tempo pra clube, cartões vermelhos, time a marcar primeiro) + fix de throttle na
coleta (16 workers estourava rajada de 429). Ver `DOCUMENTACAO_CENTRAL.md` §16 (main) pros
detalhes completos desses itens — não repetidos aqui por serem fora do escopo desta branch.

## 7. Rodada 2026-07-19 (parte 2) — fecha as 3 hipóteses pendentes (#1/#9, #12)

Continuação direta da rodada acima: as 3 hipóteses que ficaram "NÃO EXECUTADO" (#1/#9 — rerun
da bateria Fase 4/5/6 original no dataset de 60 ligas; #12 — momentum de goleiro). Mesmo
protocolo, mesmo dataset (`data/built/club_features_enriched.parquet`, 191.580 jogos,
183.530 pós burn-in ≥5 jogos disputados). Trabalho 100% local (zero chamada à API-Football —
a cota é compartilhada com a coleta de produção rodando em paralelo). Rodado nesta worktree
de pesquisa (`../previsao-jogos-clubs-research`, branch `clubs`).

### 7.1 Escopo — o que foi re-rodado e o que foi deliberadamente pulado

A bateria original (Fase 4: 9 hipóteses revisitadas de seleções; Fase 5: 7 grupos de
features próprias de clubes; Fase 6: state-space/GAP-direto/ensemble) tinha 17 testes ao
todo, sobre um dataset 3,4× menor (54.072 vs 191.580 jogos pós-expansão de liga; ~50k vs
183,5k pós burn-in). Priorizei os candidatos com alguma chance real de mudar de veredito —
os que já tinham sinal (mesmo que fraco) ou dependiam de cobertura que mudou:

- **Re-rodados**: `blend_btts` (Fase 4.3, passou 4/5 antes — o único achado positivo da
  Fase 1-6 original), `xg_feature` (Fase 4.8, prejudicado por baixa cobertura histórica —
  cobertura de xG mudou), `gap_ratings` + os outros 6 grupos da Fase 5 (`clubs_features_v2_ablation.py`,
  gap_ratings foi o único que passou isolado: 5/5 folds, delta -0,0022), `ensemble` (Fase 6.6,
  quase empate antes) e `gap_counts` (Fase 6.4, empatou com a cascata GBM antes).
- **Deliberadamente NÃO re-rodados** (reprovações firmes, sem indício de amostra insuficiente,
  já confirmadas por replicação em outras bases — ver `DOCUMENTACAO_CENTRAL.md` §9 e memória
  do agente `modelo-lambda-regressor.md`/`perfil-elo-condicionado.md`/`bateria-momentum-jogador.md`):
  `time_decay` (reprovado em seleções E em clubes-13-ligas; DC-dinâmico também reprovou na
  Fase 1), `momentum` de equipe (reprovado repetidamente, inclusive numa bateria dedicada),
  `xgb_lgbm` pra λ/μ (testado exaustivamente antes, nunca bate o GBM sklearn), `calibration`
  pós-hoc por classe (mecanismo diferente do #10 da rodada anterior, mas mesma família — sem
  motivo pra esperar reversão), `referee` (amostra por árbitro já era 10-50× maior em clubes
  e não ajudou), `elo_conditioned` (achado consistente de regressão por competição, não é
  ruído de amostra pequena), `gp_vs_nb` em escanteios (GP≈NB, sem sinal de melhora nem piora),
  `state_space` GAS (0/5 folds — o oposto de "quase passou").

### 7.2 Resultados

Reexecutados em 2026-07-19 (parte 3, mesma sessão) após dois lançamentos falhos por engano de
interpretador (o worktree de pesquisa não tem `.venv` próprio; scripts precisam do
`.venv/Scripts/python.exe` **absoluto** do repo principal — corrigido, ver nota de commit).

| Hipótese | Folds melhoram | Delta médio (logloss) | Veredito |
|---|---|---|---|
| `blend_btts` (DC-NB + HistGBM, 50/50) | 5/5 | -0,0005 | **misto** — direção 100% consistente (5/5), mas magnitude abaixo do limiar -0,001; mais forte que o 4/5 achado na base de 13 ligas, ainda não promovível pelo gate estrito |
| `xg_feature` (xG acumulado como feature, não mercado) | 1/5 | -0,0000 | REPROVADO |
| `gap_ratings` (Fase 5.6, isolado — GAP ratings de chutes/escanteios) | 5/5 | **-0,0022** | **PASSA** (>2x o limiar) — confirma o achado da Fase 5 original (base de 13 ligas) com 3,4x mais dado |
| congestion/altitude/phase/squad_rotation/xg_overperf/match_importance (Fase 5, outros 6 grupos) | — | — | REPROVADO/misto em todos — só `gap_ratings` passou isolado; combinação final (170 features) = gap_ratings sozinho, mesmo resultado (5/5, -0,0022) |
| `ensemble` (Fase 6.6 — stacking baseline+CatBoost+state_space) | 1/5 | -0,0000 | REPROVADO |
| `gap_counts` (Fase 6.4, finalizações) | — | — | sem comparação direta — cascata GBM (fase 2) não disponível pro confronto; não conclusivo |

**`gap_ratings` PROMOVIDO para produção** no mesmo dia (2026-07-19) — ver
`DOCUMENTACAO_CENTRAL.md` §17 no branch `main` para o runbook completo (feature de estado
por-time servida via snapshot, análoga ao Elo; artefato de clube retreinado com 170
`base_feats`, 158→170).

### 7.3 H12 — momentum de goleiro (BTTS/clean-sheet)

**Dados**: extraídos de `players[].statistics.goals.{saves,conceded}` +
`games.position=="G"` do espelho bruto (`club_raw_cache.sqlite` do repo PRINCIPAL, lido em
modo read-only — o espelho desta worktree de pesquisa estava vazio; zero conflito com a
coleta de produção que escreve lá, zero chamada à API). Script novo
`scripts/clubs_hyp12_gk_extract.py` (paralelizado via `multiprocessing`, 12 workers, parse de
203.819 JSONs em 25s): identifica o goleiro que mais minutos jogou por time/partida →
**244.809 linhas goleiro-jogo em 122.442 fixtures, cobertura de `saves` não-nulo 94,8%**.

Features (`scripts/clubs_hyp12_gk_momentum.py`): média móvel (shift1, point-in-time, janela
5 jogos) de `saves` e gols sofridos **por goleiro individual** (segue o jogador entre times,
mesmo espírito do estudo de momentum de jogador que passou em props — ver seção "bateria
momentum/jogador" acima) + flag de titularidade recorrente (goleiro mais frequente do time
nas últimas 10 partidas com goleiro identificado). **Cobertura do sinal (ambos os lados,
pós burn-in): 57,1%** — bem abaixo dos 94,8% de cobertura por goleiro isolado, porque exige
histórico de pelo menos 2 jogos anteriores do MESMO goleiro identificado nos dois lados
simultaneamente. Dataset de teste: 104.107 jogos (56,7% do pós burn-in) — sem imputar o
sinal ausente como "zero momentum" (enviesaria pra baixo).

Modelo: `HistGradientBoostingClassifier` sobre as 158 `base_feats` (baseline) vs
`base_feats` + 8 features de goleiro (candidato), mesmo protocolo (5 folds temporais),
avaliado em 3 targets binários:

| Target | Folds melhoram | Delta médio (logloss) | Veredito |
|---|---|---|---|
| `btts` | 4/5 | -0,0001 | misto (abaixo do limiar -0,001) |
| `home_clean_sheet` | 3/5 | -0,0004 | misto |
| `away_clean_sheet` | 2/5 | +0,0005 | misto/fraco (não passa nem por direção) |

**Veredito: REPROVADO/misto nos 3 targets — nenhum bate o gate de promoção.** Direção do
sinal é majoritariamente correta (2 dos 3 targets melhoram logloss em média, ainda que
abaixo do limiar), mas a magnitude é desprezível — muito menor que o -0,0022 do gap_ratings
(que também não passou por delta em outra métrica correlata). Duas leituras possíveis: (a) o
sinal de "forma do goleiro" já está majoritariamente capturado pelas features de defesa do
TIME (rolling de gols sofridos, chutes sofridos, etc. já presentes nas 158 base_feats) —
consistente com o achado de seleções de que "goleiro" só rendeu quando isolado para PROPS de
jogador (AUC de saves/defesas do próprio goleiro), não quando usado como sinal agregado do
resultado do time; (b) a cobertura de 57% (exige 2 jogos prévios do MESMO goleiro
identificado nos dois lados) pode estar diluindo o sinal em jogos de transição de goleiro
(lesão/venda/rotação) — candidato a reteste futuro SÓ no subconjunto de goleiros com >=10
jogos de histórico (titulares muito estabelecidos), não feito aqui por escopo.

### 7.4 Conclusão da rodada

Das 3 hipóteses que ficaram pendentes na rodada anterior, uma (H12 — goleiro) reprovou
com números limpos e as outras duas (#1/#9, rerun completo) fecharam a bateria de 17 testes
originais da Fase 4/5/6: **1 promoção real** (`gap_ratings`, delta -0,0022, agora em
produção), **1 achado consistente mas abaixo do limiar de promoção** (`blend_btts`, 5/5
folds mas delta -0,0005), e o resto reprovado/inconclusivo. A pesquisa de clubes desta
branch está, neste ponto, exaustivamente coberta: todas as hipóteses do plano original
(H1-H12 + #1/#9 revisitados) têm veredito registrado, com apenas `#2` (odds reais,
bloqueado por volume) e `blend_btts` (achado real mas sub-limiar, candidato a reteste
futuro com mais dado) como itens genuinamente em aberto.
