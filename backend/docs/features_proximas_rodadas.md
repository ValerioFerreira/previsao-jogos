# Features para λ/μ do Dixon-Coles — estado atual e próximas rodadas

> Documento operacional para continuar a exploração de features (melhora BTTS **e** os demais mercados, pois alimenta os λ/μ do DC). Feito para ser executado por outro Claude Code em casa.

## 1. Onde estamos (já feito)
- O **BTTS** sai da matriz conjunta do Dixon-Coles (`predictor.py` → `dc_probs["btts"]`), não de um modelo próprio.
- Estudo exaustivo: `scripts/experiment_btts.py` (≈44 variantes do derivado) e `scripts/experiment_btts_features.py` + `..._round2.py` (features). Relatório: `reports/btts_relatorio.md`.
- **ADOTADO em produção:** grupo **PACE** — 4 features = somas leakage-safe das rates l10:
  - `pace_gf = home_gf_l10 + away_gf_l10`
  - `pace_ga = home_ga_l10 + away_ga_l10`
  - `pace_total = pace_gf + pace_ga`
  - `btts_sum = home_bttsrate_l10 + away_bttsrate_l10`
  - Walk-forward (9 janelas): **BTTS melhora 8/9 (−0,00145)**, **gols totais 7/9 (−0,00257)**, resultado neutro. Confirmado em 2 esquemas de janela (5/6 e 8/9).
  - Wiring: `build_final_dataset.py` (+ colunas), `predictor.build_row` (computa pós-fill), DC retreinado (`scripts/retrain_dc_pace.py`) → `model_artifacts/{dixon_coles_goals.joblib, meta.json}` (158 base_feats). Neon `features_enriched` recriado com as 4 colunas.

## 2. O que NÃO funcionou (não repetir)
Testados como grupos e reprovados pelo gate de **estabilidade** (o dataset já tem rates btts/cs/fts/gf/ga em l3/l5/l10, Elo, descanso, H2H, streaks — sinal óbvio saturado):
- **V — forma por mando** (home só em casa / away só fora): piora (3/6). A forma overall já captura.
- **S — SoS via Elo do adversário recente:** bom no corte único (88% bootstrap) mas instável (2/6).
- **I — interações explícitas** (ataque×defesa, BTTS estimado): piora. O GBM já captura.
- **M — momentum (l3−l10):** irrelevante.
- **E — EWMA (span 5):** bom no corte (90% bootstrap) mas instável (6/9). Candidato a re-tentar combinado.
- **+ALL:** piora (ruído/overfit).

## 3. Metodologia / o gate (NÃO afrouxar)
- Dataset: `international_features_enriched_apifootball.csv` (9.976 jogos). Split temporal idêntico ao projeto (corte ~80% dos jogos com `has_advanced_stats==1`).
- Métrica primária: **log-loss do BTTS out-of-sample**. Secundárias: Brier, ECE, AUC, e **NLL de gols totais + log-loss de resultado** (para não regredir os outros mercados).
- **Gate de adoção:** melhora em **≥ 7/9 janelas de walk-forward** E não regride gols/resultado. Estabilidade > magnitude. (Neste mercado quase-moeda, edge pequeno e estável vale; ganho de corte único isolado **não** vale — ver o blend de §5 do relatório: 3/6, reprovado.)
- Cuidado com multiple-testing: ao varrer muitos grupos, exigir estabilidade em 2 esquemas de janela antes de adotar.

## 3b. Resultados das rodadas já executadas
- **Rodada #1 — SoS ajustado por gols (grupo `S2_sosadj`)** — `scripts/experiment_btts_features_round3.py`. Ajusta ataque/defesa pelo nível dos adversários enfrentados (schdef/schatt = média de `opp_ga_l10`/`opp_gf_l10` nas últimas 10, point-in-time) + resíduos `*_att_adj`/`*_def_adj`. Resultado por cima de base+pace:
  - BTTS: positivo na média em 3 esquemas de janela (−0,0021 / −0,0011 / −0,0002) mas consistência só ~70% (5/6, 7/9, **4/8**); melhora **resultado 7/9**; gols neutro; resíduos sozinhos pioram.
  - **Decisão: NÃO subir** — edge pequeno e ruidoso (abaixo da barra do pace ~92%), e exigiria features novas por seleção no `snapshot` (wiring mais pesado). Candidato a refinar (ex.: só recente, mínimo de histórico) numa próxima passada.

## 4. Próximas rodadas — ideias priorizadas (do mais promissor ao menos)
1. **Ratings ofensivo/defensivo ajustados por adversário (SoS iterativo de verdade)** — não o proxy de Elo que falhou. Estilo Poisson/Massey: resolver ataque/defesa por seleção ajustando pela força de quem enfrentou, point-in-time (janela móvel). É o sinal que rates cruas **não** têm.
2. **Pace assimétrico / λ̂ empírico** — produto Poisson por lado: `lam_home ≈ home_gf_l10 * away_ga_l10 / media_liga`, `lam_away ≈ away_gf_l10 * home_ga_l10 / media_liga`, e `btts_poisson = (1-e^-lam_home)(1-e^-lam_away)`. Variante direta do vencedor; testar como features.
3. **Forma por contexto/competição** — desempenho em jogos competitivos vs amistosos (intensidade e qualidade mudam BTTS). Interagir com `is_competitive`/`tournament_weight`.
4. **Volatilidade/consistência** — desvio-padrão (não só média) de gols marcados/sofridos nas últimas N. Times voláteis mudam as caudas (P(0)).
5. **Interações com ambiente** — `pace × elo_diff`, `pace × is_competitive`, `btts_sum × pace_total`.
6. **EWMA combinado com pace** — re-tentar E junto de P com spans diferentes (3, 7, 10); E sozinho foi instável, mas pode estabilizar com P.
7. **Box-score/xG condicional à cobertura** — usar `sb_*` só onde `has_advanced_stats==1`, via interação com a flag (hoje `sb_` é excluído das base_feats do DC).

## 5. Como rodar (passo a passo, em casa)
```bash
cd backend
# 1) editar scripts/experiment_btts_features.py -> build_features():
#    adicionar o novo grupo e registrar groups["X_nome"] = [colunas]
# 2) screen rápido (corte único + walk-forward 6 janelas):
./.venv/Scripts/python.exe scripts/experiment_btts_features.py
# 3) se promissor, refinar/combinar e rodar o gate (9 janelas + multi-mercado):
./.venv/Scripts/python.exe scripts/experiment_btts_features_round2.py
# resultados: reports/btts_features.json e reports/btts_features_round2.json
```
Regras ao engenheirar features: **sempre `shift(1)`** (point-in-time, sem vazamento); reconstruir histórico por seleção a partir das próprias linhas (home/away → long form), como em `build_features()`.

## 6. Se um grupo PASSAR o gate — wiring em produção (igual ao pace)
1. **`build_final_dataset.py`**: computar as colunas logo após `df_out` (antes do save/Neon).
2. **`predictor.py` `build_row`**: se as features forem **cruzadas** (home×away, como pace), computá-las **pós-fill** (no fim do build_row); se forem **por seleção**, elas entram automaticamente via `meta["bases"]`/`snapshot` (precisa adicioná-las ao snapshot no treino).
3. **Retreinar o DC**: copiar `scripts/retrain_dc_pace.py`, trocar a lista `PACE` pelas novas colunas e a função `add_pace`. Ele confirma o holdout, retreina na base completa e atualiza `model_artifacts/dixon_coles_goals.joblib` + `meta.json` (append no fim de `base_feats`/`full_feats` — **a ordem importa**).
4. **Neon**: recriar `features_enriched` com DROP + `truncate_and_append` (ver gotcha abaixo).
5. **Validar**: `Predictor("model_artifacts")` carrega, `build_row` preenche as novas colunas (sem NaN), `predict` roda; e o walk-forward confirma o ganho.
6. **Commit** `model_artifacts/*` + scripts + `predictor.py`/`build_final_dataset.py` → push → merge `main` → Render/Vercel redeploy.

## 7. Gotchas (aprendidos)
- **`truncate_and_append` preserva o schema** (TRUNCATE, não DROP) → **colunas novas exigem DROP da tabela uma vez** (`DROP TABLE features_enriched` e re-append). A API ao vivo não lê `features_enriched`, então é seguro.
- **Ordem de `base_feats`** deve ser idêntica entre treino e `meta.json` (sempre append no fim).
- O **DC imputa NaN (mediana)** no pipeline — ok ter NaN nas primeiras partidas de cada seleção.
- Features **por seleção** precisam estar no `snapshot`/`bases` do `meta` (o `predictor` preenche `home_/away_/diff_` a partir de `bases`). Features **cruzadas** computam-se no `build_row`.
- Scripts de treino legados (`train_and_save_apifootball.py`, `scripts/train_dc_apifootball.py`) usam caminhos **pré-monorepo** (`api/...`) e estão quebrados — use o fluxo cirúrgico do `retrain_dc_pace.py`.
