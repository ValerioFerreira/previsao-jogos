# Resumo dos Modelos — o que temos, o que preveem, features, resultados e tentativas

> Referência rápida de todos os modelos em produção: o que cada um prevê, as features que
> usa, os resultados nos testes e as tentativas de melhoria (e por que falharam). Atualizado
> 2026-06-22. Detalhe perene em `walkthrough.md`, `RESUMO_SESSAO_*`, `player_ranking/RELATORIO.md`.

## Visão geral
Arquitetura **híbrida por mercado** (melhor modelo para cada alvo). Todos os mercados de
contagem usam **distribuição própria** (PMF real → linhas O/U e odds da CDF). A métrica que
importa é **probabilística (log-loss/ECE)**, não acerto pontual. Tudo treinado na base
unificada da API-Football (resultados/Elo ancorados na martj42; stats avançadas da API).

---

## 1. Dixon-Coles NB — `dixon_coles_goals.joblib`
- **Prevê:** vencedor (H/D/A), total de gols, ambas marcam (BTTS), over/under 2.5 — todos da
  **mesma matriz conjunta** (sistema coerente).
- **Features:** `base_feats` (135, sem `sb_`), **9.976 jogos**. **`elo_diff` domina**; depois
  h2h, forma (gf/ga/gd l5/l10), `tournament_weight`, `days_rest`.
- **Resultados:** ganho robusto vs baseline pré-DC — resultado **log-loss 0,874→0,830, ECE
  7,57%→3,16%**; gols log-loss melhor; BTTS/over equivalentes. O ganho vem do **acoplamento
  Dixon-Coles**, não da Binomial Negativa (o `r` de gols colapsou em região quase-Poisson).
- **Tentativas de melhoria que falharam:**
  - *Calibração post-hoc* (temperature/isotônica) no resultado/over2.5 → modelos **já
    calibrados OOS** (resultado ECE 1,78%); melhora uma métrica e regride outra. Nada passa.
  - *Confiabilidade de rating* (excesso de confiança em zebras, ex. Curaçao) → é **inflação
    de Elo por força de tabela**, não flagável por nº de jogos/Elo. Sharpening não-robusto.
  - *xG como feature* → **muro de dados** (258/9.511 jogos, só 2023+).
  - *Time decay em gols* → o viés (−0,11) é **estrutural, invariante ao decay**.

## 2. CornersNB — `corners_nb.joblib`
- **Prevê:** escanteios mandante / visitante / total.
- **Features:** `full_feats` (243), **4.102 jogos** (com stats). **`elo_home_winprob` domina
  (~0,52)**; box-score (histórico de escanteios) é fraco. + **interações de mando**
  (`rha_x_elo_winprob`, `rha_x_corner_diff`) que corrigem o resíduo em campo neutro.
- **Resultados:** NB independente **bate a quantílica** em log-loss e ECE nos 3 mercados
  (total ECE 2,75% vs 5,11% da acoplada). **r≈17-21 → sobredispersão real** (NB usada de fato).
- **Tentativas:** *acoplada (bivariada)* → correlação entre lados negativa mas **fraca
  (β=−0,04)**, não compensou → aposentada. *Resíduo em campo neutro* (~0,2 escanteio, 2,4σ) →
  **corrigido** com as interações de mando (única melhoria localizada que passou o gate).

## 3. CardsNB — `cards_nb.joblib`
- **Prevê:** cartões mandante / visitante / total.
- **Features:** `full_feats` (243), **4.102 jogos**. **`is_friendly` + Elo** (contexto
  competitivo: jogo "pegado" cartoneia mais).
- **Resultados:** NB bate a quantílica (mandante log-loss 1,58 vs 1,67; ECE 1,6% vs 7,3%).
- **Achado honesto:** o `r` **colapsou (~1000) → na prática Poisson** (sem sobredispersão real;
  comporta-se como gols, não como escanteios). O ganho vem da **distribuição de contagem
  própria** vs a Normal, não da NB. Correlação entre lados **+0,07 (positiva, confirmada, mas
  fraca** → acoplada empatou). **Caveat:** intervalo de 80% grosseiro (contagem baixa, sobre-
  cobre ~92%); estimativa e linhas O/U são confiáveis.

## 4. ShotsNB — `shots_nb.joblib` (com time decay H=2)
- **Prevê:** total de chutes (finalizações).
- **Features:** `full_feats` (243), **4.102 jogos**. **Histórico de chutes (`sb_shots`)**, depois
  Elo/torneio.
- **Resultados:** NB bate a quantílica (total log-loss 3,24 vs 3,32; ECE 5,6%→2,5%). **r≈18 →
  sobredispersão real.** Foi o **único alvo onde o time decay ajudou**: H=2 corrigiu o viés
  temporal (−0,83→−0,31) e despencou o ECE.
- **Tentativas:** mercado legado migrado de quantílica+Normal para NB+decay. (Casas **não
  oferecem odds de chutes** → fora do value betting.)

## 5. Quantile models — `quantile_models.joblib` (LEGADO)
- Regressão quantílica (q10/q50/q90) que servia gols/escanteios/chutes antes da migração.
  **Não é mais carregado** pelo `predictor.py` (todos os mercados migraram). Permanece no
  disco por histórico; inofensivo.

---

## Tentativas de melhoria transversais (e por que falharam)
- **Player-ranking de temporada** (força via clube dos convocados, agregado): **redundante
  com o Elo** (corr +0,55..+0,72), gate falhou em todos os subconjuntos. → *Em aberto e EM
  COLETA agora:* a versão **forma recente por jogo** (ortogonal ao Elo), ver `FORMA_PERGAME.md`.
- **Remover a martj42** (usar só api-football): medido **~80% da perda irredutível** (Elo de
  seleção não "lava" o passado; poucos jogos/ano). **Decisão: manter a martj42.**
- **Peso de competição** (rebaixar amistosos): negativo/misto.
- **Mando triplo** (3a): só os escanteios tinham resíduo real (corrigido); gols/cartões não.

## Meta-conclusão
Os modelos estão **no teto in-sample** — o Elo domina e quase tudo que tentamos é redundante
com ele. As duas frentes vivas: **(1)** a coleta de forma-por-jogo (último sinal ortogonal não
testado) e **(2)** o **backtest de odds ao vivo** como árbitro empírico de edge real. Salto
de qualidade só com **dados de outra natureza** (tracking/xG), fora da api-football.

## Value betting / odds (Passo 4)
- `api/value_betting.py`: compara prob do modelo × odd da casa → **edge/EV** (de-vig). EV>0 = valor.
- `scripts/collect_odds_forward.py` + tarefa 3/3h: coleta odds de consenso + snapshota a
  previsão; `resolve_results.py` + `value_backtest.py` dão o veredito. Mercados mapeados:
  resultado, gols O/U, BTTS, escanteios (3), cartões (3). **Sem chutes** (casas não oferecem).
