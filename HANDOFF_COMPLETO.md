# HANDOFF COMPLETO — Previsão de Jogos de Seleções

> **Leia este documento primeiro.** É o mapa-mestre para uma nova conversa reiniciar
> sabendo de TUDO. Cobre o arco completo do trabalho, o estado atual de produção, os
> aprendizados estabelecidos, as frentes vivas e a operação. Atualizado 2026-06-22.
>
> Houve **duas trilhas** de trabalho recentes: (A) a trilha desta conversa (modelos de
> contagem, campanha de melhorias, value betting, coleta de forma-por-jogo) e (B) uma
> trilha paralela que evoluiu produção (DynamicCornersNB, CardsGP, ortogonalização de
> estilo, UX v2, detector de anomalias, logging). Ambas estão refletidas abaixo.

---

## 1. O que é o projeto
Sistema de ML que prevê, para jogos de **seleções masculinas adultas**, em PROBABILIDADE:
vencedor (H/D/A), gols, BTTS, over/under, escanteios, cartões e chutes — cada um como
**distribuição completa** (PMF → linhas O/U e "odd justa" = 1/prob). Objetivo final:
**odds honestas** e identificação de **valor vs mercado**. Fonte: API-Football (stats) +
âncora martj42 (resultados/Elo). Python 3.12, scikit-learn 1.5.2. Produção em `api/` (FastAPI),
front em `web/` (Next). NÃO tocar produção sem validação que sustente.

## 2. ESTADO ATUAL DE PRODUÇÃO (o que o `predictor.py` carrega hoje)
| Mercado | Modelo (artefato) | Observação |
|---|---|---|
| Vencedor / gols / BTTS / over2.5 | **Dixon-Coles NB** (`dixon_coles_goals.joblib`) | matriz conjunta; base_feats(135), sem box-score; **elo_diff domina** |
| Escanteios (mand/vis/total) | **CornersNB cascata r-fixo** (`corners_cascade_rfixo.joblib`) | r_H=10/r_A=8.5; cascata+estilo. ROLLBACK 2026-06-24: DynamicCornersNB REPROVADO no gate OOS (ver §4) |
| Cartões (mand/vis/total) | **CardsGP** (`cards_gp.joblib`) | Generalized Poisson (trilha paralela; #3; substituiu CardsNB) |
| Chutes (total) | **ShotsNB** (`shots_nb.joblib`) | NB + time decay H=2 (único alvo onde decay ajuda) |
| Apoio | `style_ortho_weights.joblib` | features de estilo ortogonalizadas (anti-leakage) |
| Legado no disco | `corners_nb.joblib`, `cards_nb.joblib`, `quantile_models.joblib` | não mais servidos |
- `predictor.py` também carrega `clf_result/btts/over25.joblib` (classificadores legados) —
  **verificar** se ainda são usados no `predict()` ou se são resíduo (o DC serve esses mercados).
- Subir: API `cd api && ../api/.venv/Scripts/python -m uvicorn app.main:app --port 8010 --reload`;
  front `cd web && npm run dev` (porta 3000; Node em `C:\Program Files\nodejs`, fora do PATH).

## 3. ARCO DESTA CONVERSA (trilha A), em ordem
1. **Migração de máquina + ambiente.** venv não é portável (aponta p/ máquina antiga); recriar
   in-place (`py -3.12 -m venv`). Chave só em `.env` (`APIFOOTBALL_KEY`), nunca no git.
2. **Pull saga (recuperação de órfãos).** Disciplina: backup completo antes de qualquer git
   destrutivo; verificação por hash de que arquivos não-rastreados eram idênticos ao remoto.
3. **Ciclo de modelos de contagem (meu):** escanteios (Passo 2c, NB independente), cartões
   (Passo 2b, NB→na prática Poisson), chutes (NB + decay H=2). Cada um: comparação justa,
   backup, não-regressão byte-idêntica, teste HTTP. Ver `RESUMO_SESSAO_2026-06-21.md`.
4. **Análises estratégicas (medições, não achismo):**
   - **martj42 vs só-2016+:** medido ~**80% da perda irredutível** sem a história profunda
     (Elo de seleção não "lava"; poucos jogos/ano). **Decisão: MANTER a martj42.**
   - **Auditoria do guia vs api-football:** basta p/ box-score; **NÃO** tem tracking/xG
     histórico, terço final, cruzamentos, PPDA, stats robustas de árbitro. xG só 2,7%/2023+.
   - **Time decay:** ajuda **só chutes**; gols (viés estrutural invariante), escanteios/cartões neutro.
   - **Mando triplo:** 3a (escanteios em neutro) tinha resíduo real → corrigido com interações
     de mando; 3b (peso de competição) negativo.
5. **Backend final:** item 2 (interações de mando p/ escanteios em neutro), item 3 (value
   betting `api/value_betting.py` + coletor `scripts/collect_odds_forward.py`), item 4 (limpeza).
   Ver `RESUMO_SESSAO_2026-06-21_parte2.md` e `RESUMO_MODELOS.md`.
6. **Passo 4 (value vs mercado), coletando ao vivo:** tarefa Windows `PrevisaoJogos\CollectOdds`
   (3/3h) coleta odds de consenso + snapshota a previsão; `resolve_results.py` resolve;
   `value_report.py`/`value_backtest.py` dão o veredito. **34 jogos da Copa 2026 semeados.**
   `value_report` atual: **EV médio −10,2%** (modelo ≈ mercado − margem; sem edge sistemático),
   "+EV" grandes são **espúrios** (inflação de Elo em zebras a nível de time).
7. **Campanha de melhorias rodada 2 (5 proposições) — TODAS negativas in-sample.** Ver
   `CAMPANHA_MELHORIAS_RODADA2.md`. Resumo: #5 (era-feature) viés invariante; #4 (chutes→gols)
   redundante; #1 (confederation shrinkage) — o DC **já absorve** a inflação de confederação
   (γ confirma inflação no Elo cru: CONCACAF −123, AFC −102, OFC −360; CAF/UEFA ok), o resíduo
   da base já é ~0; #2 (xG sintético) refutado por argumento (re-codificação); #3 (cards GP)
   feito na trilha B.
8. **Forma recente por jogo (ortogonal ao Elo) — INICIADA, NÃO concluída.** Ver
   `player_ranking/FORMA_PERGAME.md`. Pipeline construído (`build_targets_recent.py`,
   `collect_player_form_pergame.py`); a coleta (~165k req, ~3-4 dias) foi lançada mas **parou**
   (sem `pergame_form.parquet`; processo morreu). **Pendente: re-rodar a coleta até concluir,
   depois rodar o gate** — e aplicar a dica do resíduo `Forma~Elo` (usar só o resíduo como
   feature) para garantir ortogonalidade.

## 4. TRILHA PARALELA (B) — evoluiu produção (commits `09ecb93`→`3bfbca2`)
Feita fora desta conversa; reflito pelo que os commits/arquivos indicam (ver `LOG_EXPERIMENTO_PROPS.md`,
`task.md` e os commits para detalhe):
- **CardsGP** (Generalized Poisson para cartões) — implementa a proposição #3 (subdispersão).
- **DynamicCornersNB** (GAMLSS log-linear, mu e r) — fora de produção. **Rollback 2026-06-24:** auditoria
  com gate honesto (o "APROVADO" anterior era texto hardcoded no template do `compare_corners.py`) deu
  **REPROVADO 4/4**: log-loss 2.6375>2.6277, MAE 2.791>2.713, Tail ECE Over 8.5 = 22,4% (limite 4%), Over 11.5
  = 4,54% (limite 2,5%). Produção voltou ao intermediário r-fixo (`corners_cascade_rfixo.joblib`, r_H=10/r_A=8.5),
  como o `POST_MORTEM_DYNAMIC_DISPERSION.md` já prescrevia. Artefato rejeitado guardado em `*.REJEITADO_bak`.
- **Cascade** (shots → cartões) + **features de estilo tático com ortogonalização leakage-free**.
- **Fine-tune de escanteios** (K-fold CV grid search, OOF shots predictions anti-leakage).
- **UX v2** (refactor do front + estado global), **detector de anomalias (Z-score)**, **slider
  de CDF interativo**, **logging de previsões**, **timestamp da última coleta**, endpoint de jogos recentes.
> ⚠️ Próxima conversa: validar que esses modelos novos (DynamicCornersNB, CardsGP) passaram
> por não-regressão/gate como os anteriores, e que `predictor.py` está coerente.

## 5. APRENDIZADOS ESTABELECIDOS (não reabrir sem motivo)
- **Elo domina.** Quase toda alavanca in-sample é **redundante** com o Elo + o que o GBR já
  aprende → **teto in-sample atingido** (campanhas 1 e 2, ambas majoritariamente negativas).
- **martj42 fica** (história profunda vale ~80% irredutível para o Elo de seleções).
- **Métrica que importa: calibração (log-loss/ECE)**, não acerto pontual. Gate: melhorar
  log-loss E ECE OOS sem regressão; ajustes de cauda/nicho avaliados por **Tail-ECE estratificado**.
- **Distribuições:** gols≈Poisson (DC), escanteios NB real (r~20), cartões≈Poisson (r colapsou),
  chutes NB real (r~18). Normal foi rejeitada para contagem.
- **O único salto real exige dados de OUTRA natureza** (tracking/xG real) — fora da api-football.
- **Disciplina que protegeu o projeto:** uma mudança por vez, validada; backup antes de tocar
  artefatos; sinalizar resultados "bons demais"; não promover sem ganho que sustente; documentar
  o negativo (economiza meses de overfitting por tortura de dados).

## 6. FRENTES VIVAS / PRÓXIMOS PASSOS
1. **Backtest de odds ao vivo (árbitro empírico).** Deixar acumular (Copa 2026 + janelas futuras);
   rodar `value_backtest.py` quando houver volume. Hoje 34 semeados, ~2 resolvidos.
2. **Concluir a coleta de forma-por-jogo** (re-rodar `collect_player_form_pergame.py` até o fim)
   + rodar o gate com o **resíduo `Forma~Elo`** (única hipótese ortogonal-por-construção viva).
3. **Validar/consolidar a trilha B** (DynamicCornersNB, CardsGP) com os mesmos gates.
4. **Decisão de dados:** avaliar um provedor de tracking (StatsBomb/Wyscout) — único caminho de
   salto. Caro/externo; decisão de investimento.
5. **Ampliar mercados de odds** (há 184 tipos; mapeamos ~9 + descobrimos que **chutes TÊM mercado**
   — Total Shots/ShotOnGoal): expandir `BET_MAP` para enriquecer o backtest.

## 7. OPERAÇÃO (estado de máquina, não viaja pelo git)
- **Recriar** (MIGRACAO.md): `py -3.12 -m venv api/.venv` + `pip install -r api/requirements.txt`.
- **`.env`** na raiz (`APIFOOTBALL_KEY`); `web/.env.local` (`NEXT_PUBLIC_API_URL=http://localhost:8010`).
- **Tarefa agendada** `PrevisaoJogos\CollectOdds` (3/3h) — re-registrar via `schtasks` (ver MIGRACAO §5).
- **Cota da API é por conta/chave**, compartilhada entre máquinas (75k/dia). Coletores têm teto + cache.
- **Backups** fora do repo: `previsao-jogos-prepull-backup/`, `_backup_model_artifacts_pre_*` —
  manter até uso real confirmado.
- **Dados gitignored a copiar** (ver MIGRACAO §2): `data/odds/` (insubstituível), CSV de produção,
  `data/raw/`, `data/built/`, `player_ranking/data/`.

## 8. ÍNDICE DE DOCUMENTOS
- **Estado/mapa:** `ESTADO_E_PROXIMOS_PASSOS.md` (estado + próximos passos), este `HANDOFF_COMPLETO.md`.
- **Sessões (narrativa):** `RESUMO_SESSAO_2026-06-21.md` (backend), `_parte2.md` (UX/Passo4/campanha1),
  `RESUMO_MODELOS.md` (referência por modelo), `walkthrough.md` (histórico perene detalhado).
- **Migração/operação:** `MIGRACAO.md`.
- **Campanhas de melhoria:** `CAMPANHA_MELHORIAS_RODADA2.md` (#1-#5), `LOG_EXPERIMENTO_PROPS.md` (trilha B).
- **Forma por jogo:** `player_ranking/FORMA_PERGAME.md`, `player_ranking/RELATORIO.md` (gate temporada FALHOU),
  `docs/ESPEC_player_power_ranking.md`.
- **Comparações/relatórios:** `comparacao_escanteios.md`, `comparacao_cartoes.md`, `comparacao_chutes.md`,
  `diagnostico_gols_escanteios.md`, `feature_importance_analysis.md`, `reports/audit_report.md`.
- **Contexto por frente:** `CONTEXTO*.md`, `MELHORIAS_UX_UI.md`, `ESTATISTICAS_E_DESTAQUES_EQUIPES.md`.
