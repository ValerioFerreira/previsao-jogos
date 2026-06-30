# HANDOFF COMPLETO — sessão de experimentação (até 30/06/2026)

> **Leia este documento primeiro.** É o mapa para o próximo agente continuar sem dúvidas.
> Cobre TODO o arco desta sessão: validações, rollbacks, novos mercados, coleta de forma de
> jogadores, a reestruturação para monorepo, e as **três baterias de experimentos** (relatórios
> 1, 2 e 3). Branch de trabalho: **`claude-testing`** (pushada para `origin`). `main` = produção.
> **Nada desta sessão foi promovido a `main`** — tudo é medição/experimento na `claude-testing`.

---

## 0. TL;DR para o próximo agente
- O **pipeline de produção já está robusto e bem calibrado**. Nesta sessão **nada passou no gate** de promoção — e isso é o resultado correto, não falha.
- **Armadilha nº1:** a produção **NÃO usa Poisson** nos mercados de contagem. Usa **NB** (finalizações, escanteios, finalizações a gol), **Generalized Poisson** (cartões) e **Dixon-Coles-NB** (gols/resultado). Qualquer experimento que "mostre ganho de NB sobre Poisson" está comparando contra um **baseline strawman**, não contra produção. **Sempre compare contra o modelo real de produção.**
- **Armadilha nº2:** `RepeatedStratifiedKFold` (CV aleatória) **superestima** ganhos (ex.: forma de jogador). **O veredito vale só sob CV temporal expanding** (point-in-time). Foi assim que o "ganho" da forma no resultado **evaporou**.
- **Armadilha nº3:** o repo virou **monorepo** (`backend/` + `frontend/`). Os docs antigos `HANDOFF_COMPLETO.md`, `api/`, `web/` estão **desatualizados**. `api/.venv` não existe mais → use **`backend/.venv`**.
- **Armadilha nº4:** jobs em background **morrem no teardown de sessão**. Faça scripts de experimento **resumíveis** (checkpoint por config) e relance.

---

## 1. Estrutura e como rodar
- **Monorepo:** `frontend/` (Next.js, Vercel, porta 3000) + `backend/` (FastAPI, Railway, **porta 8000**, venv `backend/.venv`).
- **Rodar tudo:** `npm run dev` na raiz (concurrently). Só backend: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000`.
- **Python de trabalho:** `backend/.venv/Scripts/python` (pandas 3.0.3, sklearn 1.5.2). Existe também `.venv` na raiz (equivalente). **Não** existe `api/.venv`.
- **Branches:** `main` (produção), `claude-testing` (esta sessão, no `origin`). Histórico recente do `main` já integrou o trabalho anterior (Neon, httpx, deploy, mercados/UX).

## 2. Estado de PRODUÇÃO (o que `backend/predictor.py` serve hoje)
| Mercado | Modelo (artefato em `backend/model_artifacts/`) | Distribuição |
|---|---|---|
| Resultado / Gols / BTTS / Over2.5 | `dixon_coles_goals.joblib` (DixonColesNBRegressor) | **Dixon-Coles NB** (conjunta) |
| Escanteios (mand/vis/total) | `corners_cascade_rfixo.joblib` (CornersNB, r_H=10/r_A=8.5) | **NB** |
| Finalizações | `shots_nb.joblib` (ShotsNB) | **NB** |
| Finalizações a gol | `shots_on_target_nb.joblib` (ShotsNB) | **NB** |
| Cartões (mand/vis/total) | `cards_gp.joblib` (CardsGP) | **Generalized Poisson** |
| Gols 1º/2º tempo | `gols_1t_nb.joblib`, `gols_2t_nb.joblib` (CornersNB) | **NB** |
| Cartões 1º/2º tempo | `cartoes_1t_nb.joblib`, `cartoes_2t_nb.joblib` (CornersNB) | **NB** |
| Apoio | `style_ortho_weights.joblib` (ortogonalização de estilo), `meta.json` | — |
| **Legado em disco, NÃO servido** | `dynamic_corners_nb.joblib` (REPROVADO), `corners_nb.joblib`, `cards_nb.joblib`, `clf_result/btts/over25.joblib`, `quantile_models.joblib` | — |
- **Tier de confiabilidade** (Alta/Média/Baixa) por cobertura de box-score; **MatchHeader** fixo; **detalhe de partida** (cache); **modal de seleção** (futuras/passadas); **nomes PT-BR**; **H2H profundo** (martj42 1872+ ∪ api).

## 3. O que foi feito nesta sessão (cronológico/temático)
1. **Validação trilha B + rollback.** O `DynamicCornersNB` estava em produção sem gate honesto (o doc "APROVADO" era template hardcoded em `compare_corners.py`). Gate real (CV temporal): **REPROVADO 4/4** — log-loss 2.6375>2.6277, MAE 2.79>2.71, Tail-ECE Over8.5 **22.4%** (limite 4%), Over11.5 4.54% (limite 2.5%). **Rollback** para `corners_cascade_rfixo` (CornersNB r-fixo). **CardsGP mantido** (regressão marginal de log-loss compensada por melhor cauda/cobertura).
2. **Limpeza** do `predictor.py`: removidos loads mortos `clf_result/btts/over25` e método órfão `_binary` (o DC serve esses mercados).
3. **Sweep de pesos/features no modelo de gols** (`sweep_experiments.py`): **time-decay não ajuda** (meia-vida curta piora; só ≥4 anos ~neutro); **peso por competição** dá ganho minúsculo dentro do ruído; **chutes→gols redundante** (confirma prop #4); **condicional de majors** não ajuda. Adicionado `sample_weight` ao `DixonColesNBRegressor.fit` (aditivo, retrocompatível).
4. **Diagnóstico de xG:** esparso **por competição** (só elite UEFA/Euro/Copa do Mundo/Copa América) **+ recência** (concentrado em 2024); ~5.8% dos jogos com stats, amistosos ~0.4%, confederações não-europeias 0. → **inviável** como feature de xG por jogo da seleção; caminho é **xG de clube** (coletado na forma).
5. **Novos mercados + UX:** finalizações por equipe, **modelo de finalizações a gol** (`train_shots_on_target.py`), **mercados por tempo** (gols/cartões 1º/2º via `halftime_targets.parquet` + `train_halftime_markets.py`), **tier de confiabilidade**, **MatchHeader sticky**, **detalhe de partida** (do cache `data/raw/fixtures`), **modal de seleção** futura/passada, **nomes de seleção e competição em PT-BR**, **H2H profundo** (`build_h2h_results.py` = martj42 pré-2016 ∪ api), **normalização de aliases** (Czechia→Czech Republic, etc.), **árbitro** (autocomplete + `build_referee_features.py`).
6. **Coleta de forma-por-jogo CONCLUÍDA** (`player_ranking/src/collect_player_form_pergame.py`): **2.123/2.123 jogos**, point-in-time leakage-safe. Colunas por equipe: `form_rating`, `form_minutes`, `form_games30` (fadiga), `form_trend` (momentum), `coverage`, `unavail_count/rate` (lesões/suspensões via `/sidelined`), `xg_coverage`, `form_xg_for/against` (xG de clube). + `diff_*`. Cobertura: rating ~89%, xG ~73%.
7. **Reestruturação para monorepo** (api→backend, web→frontend) ocorreu no meio da sessão (por usuário/outro processo). Trabalho integrado ao `main`; passei a operar na `claude-testing`.

## 4. As três baterias de experimentos (relatórios na raiz)

### `relatorio1_29062026.md` — forma de jogador no RESULTADO (H/D/A)
- **2.016 configs** (21 feature sets × 24 modelos × 4 subconjuntos), CV `RepeatedStratifiedKFold` 5×3 **(aleatória)**.
- Achado: **Elo domina**; forma dá ganho **minúsculo** (rating-residual, trend), maior em equilibrados/alta cobertura. Caveat: Δ grandes do RandomForest são artefato (baseline RF-elo ruim).
- Script: `backend/scripts/forma_exhaustive_experiments.py` (resumível). Dados: `pergame_form.parquet`.

### `relatorio2_29062026.md` — mercados de contagem (do zero)
- Poisson × NB × Generalized-Poisson × {GBR, HistGBM-poisson, HistGBM}, por equipe e por tempo. Rodada 1 (split temporal) + rodada 2 (CV temporal + árbitro).
- Achado (vs **baseline Poisson do experimento**): NB/GP **>> Poisson** em finalizações/escanteios; gols e cartões já ótimos; **árbitro não ajuda** (amostra rasa por árbitro em seleções).
- ⚠️ **Esse "ganho" é vs Poisson, que NÃO é produção** — ver relatório 3.
- Scripts: `market_models_experiments.py`, `market_round2.py`, `build_referee_features.py`.

### `relatorio3_promocao_validacao_29062026.md` — promoção sob gate (o veredito que vale)
- **Premissa corrigida:** produção já é NB/GP/DC-NB. Pergunta real: **GP bate a NB de produção?**
- **CV temporal expanding** (4 folds; cuts 0.50/0.62/0.73/0.85), point-in-time, segmentado.
- **Resultados (gate):**
  - **GP vs NB** (finalizações/escanteios/a-gol): **empate/ruído, inconsistente por segmento** → manter NB.
  - **Forma no resultado: REPROVADO** (piora LogLoss/ECE em todos os segmentos sob CV temporal). O ganho do relatório 1 era **artefato de CV aleatória**.
  - **Calibração** (isotonic/Platt/beta): produção **já calibrada** (ECE ~4%); pós-hoc **piora na média** → não promover.
  - **Posse/passes/faltas** (não estão no base_feats): ganho **inconsistente** → não promover.
- **Promovido: NADA.** Scripts: `promotion_validation.py`, `result_forma_validation.py`, `calibration_experiment.py`, `possession_features_experiment.py`.

## 5. Dados e artefatos (tudo em `backend/`)
- `international_features_enriched_apifootball.csv` — 319 colunas, ~9.976 jogos; box-score em ~4.102 (`has_advanced_stats==1`). Alvos por equipe: `home/away_cur_sb_{shots,shots_on_target,corners,cards,yellow,red,fouls,possession,passes}`; rolling l3/l5 (pré-jogo). `elo_diff`, `tournament`, `neutral`.
- `model_artifacts/meta.json` — `base_feats` (158), `snapshot` (294 seleções), `teams`, `tournament_weights`. **base_feats NÃO inclui** posse/passes (fouls só via ratio de estilo).
- `data/built/`: `halftime_targets.parquet`, `fixture_index.json`, `past_fixtures.json`, `referees.json` (1724), `team_ids.json`, `referee_features.csv` (severidade leakage-safe), `oof_shots.csv`, `matches.parquet`.
- `player_ranking/data/processed/pergame_form.parquet` — **forma completa (2123)**.
- `model_artifacts/h2h_results.csv` (martj42∪api), `h2h_stats.csv` (box-score p/ médias do H2H).
- `data/odds/` — `registry.json`, `snapshots/`, `results/` (backtest de valor, volume baixo ainda).
- `cache_apifootball/results_martj42.csv` (49.477 jogos, 1872+).
- `data/reports/` — CSVs de TODOS os experimentos: `forma_experiments_results.csv`, `market_models_results.csv`, `market_round2_results.csv`, `market_promotion_pooled.csv` (por linha, com segmentos), `result_forma_validation.csv`, `calibration_results.csv`, `calibration_reliability.csv`, `possession_features_results.csv`.

## 6. Operação / coletas (tarefas agendadas Windows, `\PrevisaoJogos\`)
- **`CollectOdds`** (3/3h) — snapshot de odds + previsão dos jogos futuros (backtest de valor). **Ativa.**
- **`CollectResolved`** — resolve resultados dos jogos disputados. **Ativa.**
- **`CollectPlayerForm`** (diária 00:01) — ⚠️ foi criada apontando para o caminho **antigo** (`api/.venv`/`scripts/collect_player_form.cmd`) **antes** da reestruturação; pode estar **quebrada** no monorepo. A coleta já está **completa (2123)**, então é **inócua**; **repointar para `backend/...` ou remover** se quiser. Cota API: 75k/dia, compartilhada.

## 7. Protocolo de validação (o PADRÃO — siga isto)
- **CV temporal expanding** (treina no passado, testa no bloco seguinte; cuts ~0.50→0.85), **seed=42**.
- **Point-in-time:** só features pré-jogo. Ortogonalização/residualização **ajustada por fold** (sem leakage).
- **Métricas:** contagem → log-loss da PMF no valor observado + ECE da linha O/U + MAE; resultado → log-loss multiclasse + ECE multiclasse + acc; + Brier (binário).
- **Gate (todos obrigatórios):** reduzir LogLoss **vs produção real** + não piorar ECE + passar CV temporal + sem leakage + sem degradar inferência — **consistente em folds E segmentos**. Senão, **não promover**.
- **Segmentar sempre:** equilíbrio (|elo|≤80 / 80–150 / >150), competição (Copa do Mundo/Eliminatórias/Nations League/Amistoso/Continental), continente (UEFA/CONMEBOL/AFC/CAF/CONCACAF), cobertura.

## 8. PRÓXIMOS PASSOS / OPORTUNIDADES (onde começar)
1. **Exp 3 — modelagem conjunta** (não rodado): multi-output GB / cadeias de regressão (posse→finalizações→escanteios→gols) vs independentes.
2. **Exp 4 — bivariadas/cópulas** (não rodado): dependência mandante×visitante em escanteios/finalizações. *Nota: trabalho anterior mediu correlação fraca (β≈−0.04) em escanteios; o DC já captura correlação em gols.*
3. **Exp 5 — ataque×defesa→λ** (não rodado): pipeline estilo Dixon-Coles para mercados de contagem (força ofensiva A × defensiva B). *Nota: o DC de produção já faz isso para gols.*
4. **Feature importance (SHAP/permutação)** dos modelos de produção — interpretabilidade (pendente da Parte 5).
5. **xG de clube** (já coletado: `form_xg_for/against` no pergame_form) — testar se agrega aos mercados de contagem/resultado **além do base_feats**, sob CV temporal.
6. **Forma como blend de alta-cobertura** no resultado (não substituição), com gate temporal — única forma de talvez extrair o sinalzinho positivo.
7. **Backtest de valor das odds** — deixar `CollectOdds` acumular volume; rodar quando houver dezenas/centenas de jogos resolvidos.
8. **Promoção segmentada** (ex.: usar GP só onde vence) — investigado e **inconsistente**; provavelmente não vale.

## 9. Lacunas de dados conhecidas
- **Árbitro:** coletado, mas raso por árbitro em seleções (pouco sinal). Útil só em ligas de clube.
- **xG de seleção por jogo:** esparso (~6%); usar via forma de clube.
- **Odds históricas:** API só dá 7 dias → backtest depende de coleta forward (`CollectOdds`).
- **Posse/passes/faltas rolling:** existem na CSV mas **fora do base_feats**; testados (Exp 2) sem ganho consistente.

## 10. Reprodutibilidade
Todos os scripts em `backend/scripts/` (e `player_ranking/src/`) são reprodutíveis, **seed=42**, CV temporal. Resultados em `backend/data/reports/*.csv`. Relatórios na raiz (`relatorio1/2/3_*.md`, `novo_contexto.md`, este handoff). sklearn 1.5.2 / pandas 3.0.3.
