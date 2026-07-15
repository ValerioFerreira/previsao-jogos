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
| 2026-07-15 | Setup: espelho local + dataset builder + doc | — | em andamento |

(Registrar TUDO aqui, inclusive negativos, com números.)
