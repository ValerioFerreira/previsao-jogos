# Campanha de Melhorias — Rodada 2 (5 proposições) — 2026-06-22

> Teste rigoroso (gate: melhorar log-loss E ECE OOS, sem regressão) de 5 proposições de
> melhoria de modelo. Resultado honesto: **nenhuma alavanca in-sample passou** — confirma e
> reforça o teto já documentado (Elo domina; o que é redundante com ele não ajuda). Scripts
> em `scripts/experiment_*` e `scripts/confed_*`.

## Contexto
Após a campanha-1 (calibração/rating/xG/player-temporada, todas negativas), surgiram 5
proposições novas. Item 5 (odds de outros mercados) rodou antes: o `value_report` mostrou
**EV médio −10,2%** (modelo ≈ mercado − margem; sem edge sistemático) e que os "+EV" grandes
são **espúrios** (inflação de Elo em zebras: Curaçao +327%, Tunísia×Holanda +221%).

## Resultados dos testes (todos com split temporal 80/20)

### #5 — Feature de era (year≥2022) no Dixon-Coles  ❌ NEGATIVO
Hipótese: o viés de gols −0,11 (invariante ao decay) seria efeito macro (VAR/acréscimos pós-2022).
Confirmei que `year/era` não está em base_feats. Adicionei `era_pos2022`.
**Resultado:** viés −0,116 → −0,116 (idêntico); log-loss/ECE iguais. O viés é **regressão-à-média
perto do teto de previsibilidade**, não era capturável por feature. `experiment_era_goals.py`.

### #4 — Expectativa de chutes (ShotsNB) como feature do DC de gols  ❌ NEGATIVO
Confirmei que o DC usa base_feats SEM box-score → a expectativa de chutes seria sinal novo.
**Resultado:** result log-loss inalterado (0,8632); gols log-loss 1,9470→1,9450 (−0,1%, ruído).
A expectativa de chutes é **colinear com Elo/forma** (ela própria deriva deles). `experiment_shots_feature_goals.py`.
*(Obs.: a trilha paralela aplicou a ideia de cascade a CARTÕES — ver CardsGP/cascade nos commits.)*

### #1 — Confederation Shrinkage  ❌ NEGATIVO (mas diagnóstico valioso)
Engenharia de dados: `confed_map.py` mapeou **231 seleções** por confederação (via torneios
continentais; 74 não-FIFA fora). `confed_elo_bias.py` mediu o **déficit real** (não o isolamento Φ):
- **Inflados de fato:** CONCACAF −0,125, AFC −0,123, OFC −0,345 (resíduo real−Elo vs UEFA/CONMEBOL).
- **NÃO inflados:** CAF +0,02 (entrega), UEFA/CONMEBOL ~0. → Φ (isolamento) era o sinal errado
  (UEFA é a mais isolada, Φ=0,80, mas forte).

`experiment_confed_shrinkage.py` estimou γ_C (CONCACAF −123, AFC −102, OFC −360, CAF −20 pts de Elo)
e injetou no DC. **Resultado:** o residual dos inflados **já era +0,007 na base** (calibrado!) →
o **DC já absorve a inflação de confederação** (o GBR aprende o desconto do treino). O shrinkage
explícito super-corrige (resíduo → +0,018), piora o ECE (1,90%→2,17%). A inflação que sobra
(Curaçao) é **a nível de TIME**, não de confederação — granularidade errada, e o nível-time já
foi dado como não-flagável/não-robusto na campanha-1.

### #2 — xG sintético (BoxScore→xG)  ⚠️ NÃO EXECUTADO (prior baixo, refutado por argumento)
xG sintético de contagens é **função determinística do box-score que o modelo já usa** → não
adiciona a informação que o xG real traz (qualidade de chance, que exige dado a nível de chute).
Mesma armadilha de redundância. Não priorizado.

### #3 — Cards subdispersão → Generalized/COM-Poisson  ✅ FEITO NA TRILHA PARALELA
Implementado como **CardsGP** (`api/cards_gp_model.py`, Generalized Poisson) + cascade + style
features ortogonalizadas (commits `09ecb93`+). Ver os commits/relatórios dessa trilha para o veredito.

## Meta-conclusão
As 5 proposições convergem no **mesmo teto**: redundância com o Elo e com o que o GBR já aprende.
Diagnóstico maduro e robusto — **sem ganho preditivo in-sample com os dados atuais**. Caminhos vivos:
(1) **backtest de odds ao vivo** (árbitro empírico — já indica que as "vantagens" são zebras
miscalibradas a nível de time); (2) **forma-por-jogo** (ortogonal-por-construção, com a dica do
resíduo `Forma~Elo`); (3) salto só com **dados de outra natureza** (tracking/xG real).
