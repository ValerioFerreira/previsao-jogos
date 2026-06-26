# SISTEMA_COMPLETO — Previsão de Jogos (ApostAI)

> Documento-mestre para retomar o trabalho de qualquer máquina/sessão. Cobre arquitetura, deploy, dados, coletas, modelos, mercados, estudos já feitos (e o que **não** repetir) e as janelas de melhoria com o que fazer em cada uma. Última atualização: 2026-06-26.

---

## 1. Visão geral

Plataforma de **previsão probabilística de partidas de seleções** (futebol internacional). Monorepo:
- **`/frontend`** — Next.js (TypeScript), deploy na **Vercel** (`www.valerioferreira.com.br`).
- **`/backend`** — FastAPI (Python), deploy no **Render** (`https://api-previsoes-jogos.onrender.com`).
- **Banco** — **Neon** (PostgreSQL serverless). Disco do Render/Vercel é efêmero → tudo de produção vive no Neon.

`npm run dev` na raiz sobe front+back juntos (concurrently). Doc de infra: `ARCHITECTURE.md` (raiz).

## 2. Deploy e variáveis de ambiente

- **Vercel (frontend):** `NEXT_PUBLIC_API_URL` = URL do Render. Domínio: `www.valerioferreira.com.br`.
- **Render (backend), env vars já setadas:** `DATABASE_URL` (Neon), `CORS_ORIGINS` (inclui o domínio Vercel), `FRONTEND_URL`, `APIFOOTBALL_KEY`, `PYTHON_VERSION`. Opcional: `CRON_TOKEN` (protege o endpoint de cron).
- **Render lê** `model_artifacts/` (joblibs + meta, versionados no git) + o Neon. Redeploy = pull do `main`.
- **Uptime:** cron-job.org pinga `/` (rota raiz existe; sem ela dava 404) para manter o serviço acordado.

**Gotcha CORS↔500:** uma exceção 500 no FastAPI NÃO leva header CORS → o browser mascara como "erro de CORS". Se aparecer CORS só num endpoint, é 500 nele. (Foi assim que descobrimos que `fixture_fetch` usava `requests`, ausente no Render → trocado por `httpx`.)

## 3. Dados

### 3.1 Tabelas no Neon (produção)
| Tabela | Conteúdo | Lida pela API? |
|---|---|---|
| `matches` | 1 linha por (time, jogo): gols, sb_* (box-score) — base de forma/histórico | sim (forma recente, página time) |
| `features_enriched` | dataset de treino (9.976 × ~319 col, inclui pace) | não (treino/ETL) |
| `fixture_index` | `key="date|home|away"` → caminho do raw .gz | sim (lookup detalhe + ligas rastreadas) |
| `past_fixtures` | lista mínima de jogos passados (home, away, date, league) p/ o seletor | sim (seletor de partida passada) |
| `referees`, `team_ids` | árbitros; nome→id (símbolos/bandeiras) | sim |
| `odds_registry` | jogos futuros (do coletor de odds) | sim (partidas futuras) |
| `match_detail_cache` | detalhe completo de partida (JSON), cache sob demanda | sim (página Estatísticas) |
| `apifootball_match_team_stats` | stats intermediárias | não |

### 3.2 Dataset de treino
`international_features_enriched_apifootball.csv` (raiz do backend; **gitignored**; também em `features_enriched` no Neon). 9.976 jogos, 2016→2026. ~319 colunas; **158 features-base** usadas pelo Dixon-Coles (ver §6). `has_advanced_stats==1` em **4.102** (~41%) — cobertura de box-score (sb_*) só recente.
- **NÃO há colunas de xG** (nenhuma `xg`/`expected`). xG existe no raw da API (`expected_goals` em /fixtures statistics) mas **nunca foi extraído** para o dataset. (Ver janela §9-A.)

### 3.3 Local vs Neon
`data/` é gitignored e **não existe no Render**. Raw fixtures (`data/raw/fixtures/*.json.gz`), snapshots de odds e o CSV são **locais** (máquina de coleta). Produção só enxerga o Neon + `model_artifacts/`.

## 4. Coletas (o quê, por quê, onde)

Rodam na **máquina local de coleta** (Windows Task Scheduler, pasta `\PrevisaoJogos\`), escrevendo no Neon. Chave em `backend/.env` (`APIFOOTBALL_KEY`); `app/db/connection.py` carrega o `.env` local (em produção as env vars vêm do ambiente).

| Tarefa | Frequência | Script | Por quê |
|---|---|---|---|
| `CollectOdds` | a cada 3h | `scripts/collect_odds_task.cmd` → `collect_odds_forward.py` | acumula odds pré-jogo + snapshot da previsão (destrava value/ROI futuro); atualiza `odds_registry` (jogos futuros) |
| `CollectPlayerForm` | diária 00:01 | `collect_player_form.cmd` → `player_ranking/src/collect_player_form_pergame.py` | forma de clube/lesões dos convocados (EXPERIMENTAL, não em produção — ver [[trilha-b-validacao]]) |
| `CollectResolved` | diária 05:00 | `collect_resolved.cmd` → `collect_resolved.py` | jogos resolvidos da Copa que faltam em `matches` (mantém forma atual) |

**Endpoints de coleta no Render (cloud, independem da máquina local):**
- `GET /api/cron/refresh-fixtures?token=…` — atualiza `past_fixtures` (últimas ~72h, idempotente) para todo jogo de seleção ficar selecionável. **Recomendado: cron-job.org diário.** `app/services/fixtures_refresh.py`.
- Match-detail sob demanda: `get_match_detail` faz base → `match_detail_cache` (Neon) → `.gz` local → API ao vivo (`/fixtures?id`) e cacheia. `app/services/fixture_fetch.py`. Precache das últimas 5 de cada seleção da Copa via `scripts/precache_wc_details.py`.

**Cota API:** ~75.000 req/dia (reseta 21h BRT). Uso saudável (~14k/dia). Coletas de odds gastam ~40/run; backfills pesados (forma) gastam milhares.

## 5. Mercados (o que o site mostra) e de onde saem

`predictor.py::predict(home, away, neutral, tournament)` orquestra tudo. Markets:
- **Resultado 1X2, BTTS, Over 2.5, Total de gols, Gols por equipe, Placar exato** → todos da **matriz conjunta do Dixon-Coles** (§6).
- **Finalizações, Chutes a gol, Escanteios, Cartões** (+ por equipe, + 1º/2º tempo) → modelos **NB em cascata** (§6.2).
- **Placar Exato:** top-3 da conjunta + **alerta de desvio** (potencial de placar fora do padrão) baseado na supremacia de gols esperados + cauda P(4+). `predictor.py` → `placar_exato`.
- **Confiabilidade** do jogo (cobertura de box-score), **confronto direto** (H2H).

## 6. Modelos

### 6.1 Gols / BTTS / Over / Resultado / Placar exato — Dixon-Coles NB
`dixon_coles_model.py` (`DixonColesNBRegressor`):
- **λ_home, μ_away** estimados por **sklearn GradientBoostingRegressor** (depth 3, 100 árvores, lr 0.05) sobre as 158 features (um regressor para casa, um para fora; cada um vê TODAS as features).
- **Marginais Binomial-Negativa** (dispersão `r_H`, `r_A`) + **correção Dixon-Coles `rho`** nas células de placar baixo (0-0/0-1/1-0/1-1). `r_H, r_A, rho` ajustados por **MLE** no treino.
- **Matriz conjunta** P(home=x, away=y) normalizada → dela saem BTTS (Σ x≥1,y≥1), Over, Resultado, Total, Placar exato.
- É **mais flexível que Poisson independente** (NB + tau). Alternativa não testada: Bivariate Poisson / cópulas (§9-C).

### 6.2 Demais mercados (NB em cascata)
`model_artifacts/`: `shots_nb`, `shots_on_target_nb`, `corners_cascade_rfixo` (chutes→escanteios), `cards_gp` (Gamma-Poisson), `gols_1t/2t_nb`, `cartoes_1t/2t_nb`, `dynamic_corners_nb`. Ortogonalização de estilo (`style_ortho_weights`) injeta resíduos de estilo.

### 6.3 Predictor / artefatos
`predictor.py` carrega `model_artifacts/` (joblibs + `meta.json`). **`meta.json`** guarda: `base_feats` (158), `full_feats` (294), `bases` (87 por-seleção), **`snapshot`** (valores das features de cada seleção, "congelados" no treino), `teams`, `tournament_weights`. Em produção o `build_row` monta o X a partir do `snapshot` (não recalcula rolling); features cruzadas (ex. pace) são computadas pós-preenchimento.
- **Re-treino cirúrgico:** `scripts/retrain_dc_pace.py` (modelo) — os scripts legados (`train_and_save_apifootball.py`, `scripts/train_dc_apifootball.py`) têm caminhos pré-monorepo quebrados; **use o retrain cirúrgico**.

## 7. Features (158 base)
Já incluídas e usadas pelo DC: Elo (`home_elo_pre`, `elo_diff`, `elo_home_winprob`), descanso (`*_days_rest`), mando (`neutral`, `real_home_advantage`), H2H, streaks, e rates **gf/ga/gd/ppg/winrate/csrate/ftsrate/bttsrate** em janelas l3/l5/l10 (home/away/diff), tournament weights. **Pace** (somas l10: `pace_gf/pace_ga/pace_total/btts_sum`) — adicionado e validado (ver §8). Excluídas do DC: `sb_*` (box-score, cobertura esparsa) e `home_cur_/away_cur_`.

## 8. Estudos já feitos (resultados — NÃO repetir o que falhou)
Harness reproduzível: `scripts/experiment_btts*.py`, `experiment_lambda_regressor.py`. Gate = **walk-forward (estabilidade)** + bootstrap + multi-mercado. Relatórios em `reports/` (gitignored).
- **BTTS (derivado):** DC já ótimo. `rho`, calibração (Platt/Isotônica/Temperatura) e modelo dedicado **pioram**. Blend DC+HistGBM marginal e **instável** (3/6). → manter. (`reports/btts_relatorio.md`)
- **Features novas (6 grupos):** só **PACE** passou o gate (BTTS 8/9 janelas, gols 7/9) → **EM PRODUÇÃO**. Reprovados: forma por mando (V), SoS-Elo (S), SoS ajustado por gols (S2, instável 4/8–7/9), interações explícitas (I), momentum (M), EWMA (E, instável). (`docs/features_proximas_rodadas.md`)
- **Regressor de λ/μ (XGBoost/LightGBM/HistGBM):** testado exaustivamente (9 configs × 8 janelas × 4 mercados) — **nenhum bate o sklearn GBM**; boosters potentes overfitam. Janela fechada. (`reports/lambda_regressor.json`, [[modelo-lambda-regressor]])
- **Pesos de gols:** time-decay não ajuda; downweight de amistosos = único ganho pequeno; xG só 5,8% em elite. (`sweep-pesos-gols`)

## 9. Janelas de oportunidade (análise das sugestões + o que fazer)

Mapeando as sugestões fornecidas ao estado atual:

| Sugestão | Estado | Veredito |
|---|---|---|
| Força ataque/defesa via Dixon-Coles/Bivariate Poisson | **Já feito** (DC-NB) | — |
| ML (muitas vars) p/ λ_home/λ_away | **Já feito** (GBM, 158 feats) | — |
| XGBoost/LightGBM no λ/μ | **Testado** (§8) | **Não melhora** |
| Calibração (Platt/Isotonic) do BTTS | **Testado** | **Piora** (DC já calibrado) |
| Distribuição conjunta flexível | **Já** NB+tau (DC) | BP/cópula = janela aberta (C) |

**Janelas REALMENTE abertas (com o que fazer):**

**A. xG/xGA como feature (dados parciais existem).**
Por quê: hoje o DC não usa xG (ausente do dataset). O raw da API tem `expected_goals` nas /fixtures statistics para ~41% dos jogos (recentes).
O que fazer: (1) no `build_history.py::parse_match`/`STAT_MAP`, extrair `expected_goals` (e o do adversário) → colunas `sb_xg`/`sb_xga`; (2) computar rolling l5/l10 point-in-time (como as outras rates) + cross (xG ataque × xGA defesa); (3) testar como grupo no harness (`experiment_btts_features.py`), **condicionando à cobertura** (interação com `has_advanced_stats`, pois pré-2022 não tem). Risco: cobertura esparsa pode adicionar ruído (memória: xG só 5,8% em elite).

**B. Backtest financeiro (ROI/yield) + RPS.**
Por quê: hoje só validamos por log-loss/Brier/ECE. **ROI/yield ainda inviável** — só **38 snapshots de odds / 3 resultados** (coletor de odds é recente). RPS não é computado.
O que fazer: (1) deixar `CollectOdds` rodando ~2-3 meses para acumular odds de fechamento × resultados; (2) usar `scripts/value_backtest.py` + `value_betting.py` para ROI/yield por mercado e por faixa de edge; (3) adicionar RPS (Ranked Probability Score) ao harness (trivial: sobre a distribuição ordinal de resultado/gols). **Acompanhar `odds_registry`/snapshots crescer.**

**C. Bivariate Poisson / cópula para a conjunta (placar exato).**
Por quê: usamos DC-NB (NB + tau). Bivariate Poisson (termo de covariância λ3 compartilhado) e cópulas modelam a correlação de outra forma — pode mudar a cauda de placares.
O que fazer: implementar um joint Bivariate Poisson (MLE de λ1,λ2,λ3) e/ou cópula gaussiana sobre marginais NB; comparar **NLL de placar exato** e log-loss BTTS/Over no walk-forward vs o DC-NB atual (reusar `evaluate()` de `experiment_lambda_regressor.py`). Expectativa: ganho incerto (DC-NB já trata correlação de baixos placares).

**D. Ratings dinâmicos (bayesiano / Elo aprimorado contínuo).**
Por quê: as features de força (Elo, rates) entram "congeladas" no snapshot do treino; não há um estado de força ataque/defesa que evolui continuamente.
O que fazer: implementar um **Dixon-Coles dinâmico** (forças de ataque/defesa por seleção evoluindo no tempo, estilo filtro de Kalman / atualização bayesiana online) OU um Elo com K adaptativo e ataque/defesa separados; gerar features point-in-time e testar no harness. Maior esforço; potencial real para placar exato.

**E. Lesões/disponibilidade.**
Por quê: existe coletor (`collect_player_form_pergame.py`, usa `/sidelined`) mas é EXPERIMENTAL e não passou o gate ([[trilha-b-validacao]]).
O que fazer: derivar feature de "% do elenco-base indisponível" point-in-time e testar como grupo; só promover se passar o gate (≥7/9 janelas, sem regressão).

**Prioridade sugerida:** B (acumular dados/ROI — é o que falta de validação "de verdade") em paralelo com A (xG, dado parcial já existe) e C (BP, estrutural e barato de testar). D e E são maiores/incertos.

## 10. Como rodar / reproduzir
```bash
cd backend
# experimentos (gate = walk-forward + multi-mercado):
./.venv/Scripts/python.exe scripts/experiment_btts_features.py        # screen de grupos de features
./.venv/Scripts/python.exe scripts/experiment_btts_features_round2.py # gate 9 janelas multi-mercado
./.venv/Scripts/python.exe scripts/experiment_lambda_regressor.py     # classe do regressor (XGB/LGBM)
# re-treino do DC após validar uma feature (cirúrgico):
./.venv/Scripts/python.exe scripts/retrain_dc_pace.py   # adapte a lista de features
```
Regra de ouro das features: **sempre `shift(1)`** (point-in-time, sem vazamento). Gate de adoção: melhora em **≥7/9 janelas** de walk-forward, em ≥2 esquemas de janela, sem regredir os outros mercados. Detalhe em `docs/features_proximas_rodadas.md`.

## 11. Gotchas (aprendidos)
- `truncate_and_append` preserva schema → **coluna nova no Neon exige DROP da tabela** uma vez.
- `pandas==3.0.3` exige **SQLAlchemy ≥ 2.0.36** (senão `to_sql` quebra).
- `connection.py` lê `DATABASE_URL` de `os.getenv` mas carrega `backend/.env` local via `setdefault`.
- Leitores da API (`get_referees`, `get_team_ids`, `past_fixtures`, `fixture_index`) usam `_cache_nonempty` (só cacheiam não-vazio) p/ não "envenenar" com `[]` de cold-start do Neon.
- Scripts de treino legados (`train_*_apifootball.py`) têm caminhos pré-monorepo quebrados — use `retrain_dc_pace.py`.
- Ordem de `base_feats` deve ser idêntica treino↔`meta.json` (append no fim).

## 12. Onde retomar
1. **B — acumular odds e montar o backtest financeiro (ROI/yield) + RPS** (a validação que mais falta).
2. **A — xG features** (extrair `expected_goals` do raw, testar no gate).
3. **C — Bivariate Poisson** para placar exato (barato de testar).
4. Rodada #2 de features (pendente): **volatilidade** (desvio-padrão de gols) + **EWMA×pace** — ver `docs/features_proximas_rodadas.md` e [[btts-estudo-melhoria]].
