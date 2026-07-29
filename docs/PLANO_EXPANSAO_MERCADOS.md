# PLANO — Expansão de mercados: catálogo, gate de contagem e pipeline

> **Escrito em**: 2026-07-29, numa máquina **sem** a base completa de clubes (4 de 85 ligas).
> **Para**: o agente/dev que executar isto em outra máquina.
> **Leia antes**: `docs/HANDOFF_PROXIMA_MAQUINA.md` (bloqueios de credencial/dado),
> `DOCUMENTACAO_CENTRAL.md` §6 (gate), §9 e §16/§17 (o que já foi reprovado), §20/§24/§25
> (por que mercado novo não é alfa novo).
> **Status**: plano aprovado, **nada executado**.

---

## 0. TL;DR

A API-Football já nos entregou muito mais dado do que consumimos, e **ele está no disco**.
Dá para abrir ~15 mercados novos **sem gastar um único request de cota**. O trabalho é de
modelagem e validação, não de coleta.

Mas há um problema anterior: **os mercados de contagem que já estão em produção nunca passaram
por gate nenhum.** Então a primeira entrega não é mercado novo — é o gate.

| Fase | O que é | Bloqueado? |
|---|---|---|
| 0 | Definir o gate §6-C (mercado de contagem) | não |
| 1 | Auditoria retroativa dos 7 mercados já no ar | não |
| 2 | Estender `STAT_MAP` (+7 estatísticas) e rebuild | não |
| 3 | Targets derivados de `events` | não |
| 4 | Treinar candidatos + rodar o gate | **parcial** — clube depende do backfill |
| 5 | Integrar só o que passou (predictor + frontend) | depende da 4 |
| 6 | Fechar assimetrias + documentar | não |

---

## 1. O que a auditoria encontrou

Três varreduras de código + inspeção read-only do espelho `backend/data/club_raw_cache.sqlite`
(610 MB, 21.130 jogos).

### 1.1 Metade das estatísticas da API é descartada

`STAT_MAP` em `backend/scripts/build_clubs_dataset.py:64-75` tem **10 entradas**. O blob salvo
tem **19 `type` distintos**. Os 9 restantes nunca viraram coluna.

Cobertura medida sobre os 21.130 jogos (`statistics` presente em 14.090 = **66,7%**):

| `type` da API | Cobertura | Vira coluna hoje? |
|---|---|---|
| Shots on Goal | 66,2% | sim → `sb_shots_on_target` |
| Total Shots | 65,7% | sim → `sb_shots` |
| Corner Kicks | 66,6% | sim → `sb_corners` |
| Offsides | 62,4% | sim → `sb_offsides` |
| Ball Possession | 65,8% | sim → `sb_possession` |
| Yellow Cards | 64,7% | sim → `sb_yellow` |
| Red Cards | **23,4%** | sim → `sb_red` (ver §1.4) |
| Fouls | 66,1% | sim → `sb_fouls` |
| Total passes | 63,5% | sim → `sb_passes` |
| expected_goals | 17,4% | sim → `sb_xg` |
| **Shots off Goal** | 66,2% | **não** |
| **Goalkeeper Saves** | 65,9% | **não** |
| **Blocked Shots** | 64,0% | **não** |
| **Shots insidebox** | 63,5% | **não** |
| **Shots outsidebox** | 63,5% | **não** |
| **Passes accurate** | 63,5% | **não** |
| **Passes %** | 63,5% | **não** |
| goals_prevented | 10,7% | não (§21 já marcou NOT VIABLE) |
| Free Kicks | 0,1% | não (irrelevante) |

Amostra de controle em 400 jogos com `statistics`: `Goalkeeper Saves`, `Shots insidebox`,
`Shots outsidebox` e `Blocked Shots` presentes em **400/400**. Ou seja, vêm de graça junto com
as que já usamos — não há custo marginal de coleta.

### 1.2 `events` tem 99,9% de cobertura e é 100% desperdiçado

`grep -n "events" backend/scripts/build_clubs_dataset.py` → **zero ocorrências**. Nenhum builder
de dataset lê o bloco de eventos.

- `events` presente em **21.114 / 21.130 (99,9%)**, todos com `time.elapsed` (minuto exato)
- 9.313 jogos têm também `time.extra` (acréscimos)
- 64.391 cartões amarelos · 48.157 gols normais · 4.652 pênaltis · 3.253 vermelhos · 1.534 gols contra
- `score.halftime` presente em **21.124 / 21.130 (100,0%)**

Os únicos consumidores de `events` hoje são dois scripts de target isolados
(`build_first_scorer_targets.py`, `build_clubs_halftime_targets.py`). O dataset principal ignora.

### 1.3 O gate que se pretende usar não existe

```
grep -l "TimeSeriesSplit\|expanding\|fold\|log_loss\|cross_val" backend/scripts/train_*_market.py
→ (vazio)
```

Os scripts de treino de mercado de contagem (`train_yellowcards_market.py`,
`train_redcards_market.py`, `train_clubs_halftime_markets.py`) têm apenas um **print de sanidade
in-sample** comparando `E[PMF]` com a média real. Sem CV temporal, sem baseline, sem ECE.

O próprio código admite, em `backend/predictor.py:762-763`:

> *"Cartões vermelhos isolados (mercado novo, exibido cru — **sem gate de calibração ainda**)."*

O **gate §6** do doc-mestre foi desenhado para **substituir um incumbente** — é literalmente o
que `scripts/promotion_validation.py` faz ("GP bate a NB de produção?"). Num mercado novo não há
incumbente, então boa parte do gate não se aplica e é preciso definir o análogo.

### 1.4 Armadilha de dado: `null` que significa zero

`Red Cards` tem só **23,4%** de não-nulo nos dois times — não porque falte dado, mas porque
**a API manda `null` quando o valor é 0**. O `build_clubs_dataset.py:165-170` já trata esse caso
específico:

```python
y, r = trow.get("sb_yellow"), trow.get("sb_red")
if y is None and r is None:
    trow["sb_cards"] = None
else:
    trow["sb_yellow"], trow["sb_red"] = float(y or 0.0), float(r or 0.0)
```

**Para cada estatística nova é obrigatório decidir explicitamente se `null` é zero ou ausente.**
Tratar ausente como zero envenena o alvo e o modelo aprende a prever zero.

Heurística de decisão: `Goalkeeper Saves` praticamente nunca é 0 num jogo real → `null` = ausente.
`Blocked Shots` pode legitimamente ser 0 → `null` = zero. Validar comparando a taxa de nulos
contra a distribuição esperada antes de treinar.

---

## 2. Catálogo de mercados candidatos

Custo: **A** = só script de treino · **B** = +`STAT_MAP` + rebuild · **C** = +script de target.

### Grupo 1 — o dado já é coluna (custo A)

| Mercado | Coluna | Cobertura | Seleção | Clube |
|---|---|---|---|---|
| Faltas (mandante/visitante/total) | `*_cur_sb_fouls` | 66,1% | **pronto** | pronto |
| Posse de bola | `*_cur_sb_possession` | 65,8% | **pronto** | pronto |
| Passes totais | `*_cur_sb_passes` | 63,5% | falta coluna | pronto |
| Impedimentos | `*_cur_sb_offsides` | 62,4% | já em produção | **falta artefato** |

Verificado: `international_features_enriched_apifootball.csv` (282 colunas) tem
`home/away_cur_sb_fouls` e `home/away_cur_sb_possession`. **Faltas e posse são treináveis para
seleção imediatamente**, sem depender de nenhum backfill.

⚠️ **Posse não é contagem** — é proporção soma-zero (`home + away = 100`). Não usar `CornersNB`.
Modelar `home_possession` com regressão Beta e derivar o visitante por complemento; mercado
"Over/Under 50,5% de posse do mandante". O mesmo vale para `Passes %`.

### Grupo 2 — no cache, falta estender `STAT_MAP` (custo B)

Defesas do goleiro · Chutes para fora · Chutes bloqueados · Chutes dentro da área ·
Chutes fora da área · Passes certos · Precisão de passe (%)

Todos ~63-66% de cobertura. Ver §1.4 antes de treinar.

### Grupo 3 — derivável de `events` (custo C)

| Mercado | Fonte |
|---|---|
| **HT/FT (resultado duplo, 9 combinações)** | `score.halftime` + `goals` |
| Resultado do 1º tempo (1X2 HT) | `score.halftime` |
| Placar exato do 1º tempo | `score.halftime` |
| Time a marcar por último | `events` |
| Gol em intervalo (0-15, 16-30, 31-45, 46-60, 61-75, 76-90) | `events[].time.elapsed` |
| Marcar nos dois tempos / ambas marcam no 1º tempo | `events` + `score.halftime` |
| Cartão após o minuto 70 | `events[].time.elapsed` |
| Gol nos acréscimos | `events[].time.extra` |

**HT/FT é o de maior valor**: mercado clássico, odd alta, presente em toda casa, e já temos
`gols_1t_nb` e `gols_2t_nb` treinados.

⚠️ **Não derivar HT/FT pelo produto das duas marginais.** 1º e 2º tempo não são independentes —
quem está atrás ataca mais, quem está à frente recua. Modelar como classificador 9-vias direto
(`HistGradientBoostingClassifier`), e usar **o produto das marginais como baseline no gate**:
se o classificador não bater o produto, o mercado não vale o artefato extra.

**"Time a marcar por último"** é o espelho exato do `first_scorer` — `build_last_scorer_targets.py`
reaproveita `build_first_scorer_targets.py:49-70` trocando `gevents[0]` por `gevents[-1]`.

❌ **Escanteios por tempo NÃO são deriváveis.** A API-Football não emite evento de escanteio;
`Corner Kicks` só existe agregado no jogo inteiro. É por isso que os `adhoc_corners_halftime_*.py`
vão buscar esse dado em **football-data.org** (`fd_get`), fonte externa. Fora do escopo deste plano.

### Grupo 4 — prop de goleiro (decisão do dono)

Defesas por goleiro, de `players[].statistics.goals.saves` — 13.414 jogos (63,5%), 497.398 blocos
de estatística de jogador.

**Por que só este, e por que ele não viola a regra de ouro:** o doc-mestre §9 declara o espaço de
props de jogador **"exaurido"** — cartão de jogador (AUC 0,62 seleção / 0,634 clube) e faltas de
jogador (AUC 0,58) foram testados sob o gate e **reprovados nos dois escopos**; só os ofensivos
(goleador AUC ~0,74, finalizações) passaram e já estão em produção. Saves aparece no §17.1 como
**REPROVADO**, mas ali foi testado como **feature** do modelo de gols (Δlog-loss −0,00037, abaixo
do limiar) — nunca como **mercado-alvo**. São perguntas diferentes: "saves do goleiro adversário
ajuda a prever gols?" ≠ "conseguimos prever quantas defesas este goleiro fará?".

Uma hipótese isolada. **Não reabrir desarmes, dribles ou duelos** sem decisão explícita.

### Grupo 5 — assimetrias já existentes (custo quase zero)

1. **`offsides_nb.joblib` não existe em `model_artifacts_clubes/`** → impedimentos existe para
   seleção e não para clube. Um comando de treino resolve.
2. **`ou_calibrators.joblib` não existe em `model_artifacts_clubes/`** → 8 mercados de contagem
   de clube saem **crus**, enquanto os equivalentes de seleção saem calibrados. Chaves presentes
   no artefato de seleção: `cartoes`, `cartoes_1t_{home,away,total}`, `cartoes_2t_{...}`,
   `escanteios`, `escanteios_home`, `finalizacoes_gol`, `gols_1t_total`, `gols_2t_total`.
3. **`empate_anula` (DNB) é calculado e nunca exibido.** `predictor.py:708-709` produz o dado, mas
   o único consumidor (`DerivedMarketsBlock`, `DerivedMarkets.tsx:201`) vive em
   `PredictionDisplay.tsx` — componente morto que nenhuma página importa
   (`app/page.tsx` e `app/compartilhado/[token]/page.tsx` usam só `AnalysisResultsView`).
   Mercado pronto, invisível. ~3 linhas de JSX.
4. Bônus, achado na varredura: **`predictor_service.py:1019-1080`** são ~60 linhas inalcançáveis
   depois de um `return` incondicional em `get_goal_timing` (linhas 1008-1017).

---

## 3. Fase 0 — Definir o gate §6-C (mercado de contagem)

**Arquivo novo: `backend/scripts/gate_count_market.py`**

Reaproveita integralmente `backend/research_clubs/protocol.py` — **não escrever métrica nova**.
Já existe lá:

| Função | Uso |
|---|---|
| `temporal_folds(df, cuts, date_col)` | expanding, `CUTS = [0.50, 0.60, 0.70, 0.80, 0.85]` (mesmos cortes do §6) |
| `pmf_logloss(y, pmfs)` | métrica primária |
| `pmf_mae(y, pmfs)` | erro da média |
| `coverage80(y, pmfs)` | cobertura do intervalo |
| `ou_probs_from_pmf(pmfs, line)` | P(total > linha) |
| `tail_ece(y, pmfs, lines)` | ECE das linhas O/U (foi o que reprovou o `DynamicCornersNB`) |
| `summarize(results, label)` / `compare(base, cand, metric)` | tabela fold-a-fold |

**O que muda em relação ao §6**: o incumbente é o **baseline trivial**, porque não há modelo
anterior. Três baselines obrigatórios; o gate compara contra o **melhor** deles:

- **B0** — NB de intercepto (média global, sem feature nenhuma)
- **B1** — NB sobre a média rolante do time (`*_l5`/`*_l10`) e mais nada
- **B2** — média da competição

**Critério de aprovação** (espelha o operacional de clube do §17,
`DOCUMENTACAO_CENTRAL.md:968-970`):

1. `pmf_logloss` melhor que o melhor baseline em **≥4/5 folds**
2. Δ`pmf_logloss` médio **< −0,001**
3. `tail_ece` da linha central **≤ 0,05** e não pior que o baseline
4. `coverage80` dentro de **[0,75; 0,85]**
5. **≥5.000 jogos** com alvo não-nulo
6. Sem inversão de sinal por segmento (competição, faixa de `|elo_diff|`)

Para mercado multiclasse (HT/FT, marcar por último) trocar `pmf_logloss` por
`multiclass_logloss` + `ece_multiclass`, ambos já em `protocol.py`.

**Reprovar é resultado válido** e deve ser registrado no doc-mestre, não escondido.

**Saída**: `backend/data/reports/gate_mercados/<mercado>_<scope>.{md,csv}`

---

## 4. Fase 1 — Auditoria retroativa dos mercados já no ar

Rodar o gate da Fase 0 nos **7 mercados que foram para produção sem validação**:

`impedimentos` · `cartoes_amarelos` · `cartoes_vermelhos` · `gols_1t` · `gols_2t` ·
`cartoes_1t` · `cartoes_2t`

Não é burocracia — **é o que calibra o próprio gate**. Se nenhum mercado em produção passar, o
limiar está apertado demais; se todos passarem folgado, está frouxo. E qualquer reprovação vira
decisão de produto: esconder o card, ou exibi-lo com selo explícito de baixa confiança.

---

## 5. Fase 2 — Estender `STAT_MAP` e reconstruir o dataset

1. `backend/scripts/build_clubs_dataset.py:64-75` — 7 entradas novas no `STAT_MAP`
2. Resolver a política de `null` de cada uma (**§1.4** — obrigatório antes de treinar)
3. Adicionar as colunas ao rolling `SB_COLS` em `backend/build_final_dataset.py:404-406`
4. Rodar o rebuild

```bash
cd backend
.venv/Scripts/python -m scripts.build_clubs_dataset --stage all
```

Zero chamada de API — lê só o espelho sqlite local.

⚠️ **Este passo exige o espelho completo.** Rodar com 4 ligas gera um parquet de 21k jogos que
**não pode** ser usado para treinar artefato de produção — é exatamente a armadilha que degradou
o modelo congelado (250.682 → 19.574 jogos de treino, ver §24 do doc-mestre).

---

## 6. Fase 3 — Targets derivados de `events`

Um script por família, seguindo o padrão exato de `build_first_scorer_targets.py`:
`CONFIG` dual-escopo, `--scope {selecao,clube}`, `SELECT fixture_id, raw FROM raw`, saída parquet.

- `build_htft_targets.py` — HT/FT, 1X2 HT, placar exato HT
- `build_goal_window_targets.py` — gols e cartões por janela de 15 min
- `build_last_scorer_targets.py` — espelho do first scorer

Reusar a flag `has_card_events` (`build_clubs_halftime_targets.py:71`) para filtrar jogos sem
cobertura de eventos — sem ela, jogo sem evento vira "zero cartões" e envenena o alvo.

---

## 7. Fase 4 — Treinar candidatos e rodar o gate

Um `train_<mercado>_market.py` por mercado, copiando **`train_yellowcards_market.py`** (o template
mais limpo: lê `meta["base_feats"]` do artefato do escopo, `CornersNB(feats=base_feats,
max_corners=N)`, `--scope`, `m.save()`).

| Tipo de alvo | Modelo | Referência |
|---|---|---|
| contagem | `CornersNB` | `backend/corners_nb_model.py` |
| proporção (posse, precisão de passe) | regressão Beta | novo |
| multiclasse (HT/FT, marcar por último) | `Pipeline(SimpleImputer + HistGradientBoostingClassifier)` | `train_first_scorer_market.py:75-79` |

### Onde o gate é definitivo e onde não é

Isto **precisa** estar explícito no relatório final — é a lição do §24.

| Escopo / mercado | Base disponível | Status do gate |
|---|---|---|
| **Seleção** — faltas, posse | 9.976 jogos, dataset completo e atual | **definitivo** |
| Seleção — demais | sem `raw_cache.sqlite`, sem `ht_home` no CSV | **bloqueado** |
| **Clube** — todos | depende do backfill (hoje 4 de 85 ligas) | **preliminar até o mirror completar** |

Enquanto o espelho estiver incompleto, rodar o gate de clube mesmo assim — mas marcado como
**smoke test**: serve para pegar bug de pipeline, nunca para decidir promoção.

⚠️ **Seleção tem duas limitações próprias, descobertas na auditoria:**
- `backend/data/raw_cache.sqlite` **não existe** (o código o referencia em `raw_cache.py:22` e
  `prefetch_wc_data.py` chama `local_put()`, mas o arquivo nunca foi criado) → nenhum mercado de
  seleção derivado de `events` é viável hoje.
- O CSV ativo (282 colunas) é **mais pobre** que o backup
  `backend/international_features_enriched_apifootball.csv.bak_20260617` (319 colunas, com
  `sb_passes`, `style_*`, `pace_*`). Vale checar se houve regressão antes de assumir que a
  coluna não existe.

---

## 8. Fase 5 — Integrar só o que passou

Padrão opcional/retrocompatível, sem exceção: **artefato ausente = chave ausente no JSON = card
não renderiza**. Zero risco para produção.

1. Constante de linhas O/U — `backend/predictor.py:69-97`
2. Carga com `os.path.exists` no `__init__` — `predictor.py:128-154`
3. Bloco `if self.<x> is not None:` em **`_predict_from_X`** — `predictor.py:752-802`
4. Campo opcional (`?`) no `PredictionResponse` — `frontend/src/lib/api.ts:80-98`
5. Render condicional — `frontend/src/components/platform/AnalysisResultsView.tsx`

⚠️ **Adicionar em `_predict_from_X`, não em `predict()`.** `_predict_from_X` é o corpo
compartilhado por `predict()` (`predictor.py:506`) e por `predict_from_row()` (`:536`), que é o
motor do backtest. Colocar no lugar errado faz o mercado sumir de toda análise histórica.

`app/main.py`, `predictor_service.py` e `odds.py` **não mudam** — `/predict` retorna `dict` sem
`response_model`, então o campo novo flui sozinho. Só mexer em `odds.py` se o mercado precisar
entrar no Verificador de Bets (badge de odds por casa).

⚠️ **Nunca devolver `NaN` no dict — usar `None`.** `NaN` quebra o `INSERT` em
`app_analyses.snapshot::JSONB` do Postgres; foi um 500/CORS real, documentado em
`predictor.py:266-272`.

---

## 9. Fase 6 — Assimetrias e documentação

- Grupo 5 do catálogo (§2): `offsides_nb` de clube, `ou_calibrators` de clube, `empate_anula` no
  frontend, código morto do `predictor_service.py`
- **§27 nova no `DOCUMENTACAO_CENTRAL.md`**: catálogo, definição do gate §6-C, resultado da
  auditoria retroativa, e o veredito de cada candidato — **incluindo os reprovados**
- `CLAUDE.md`: registrar o gate §6-C na seção de regras de ouro
- `data/MANIFEST.yaml`: registrar os targets/datasets novos e dar `push` para o WorkDrive

---

## 10. O que este plano NÃO promete

Mercado novo é **superfície de produto, não alfa**.

As §20, §24 e §25 do doc-mestre concluíram **sem edge robusto** — com 8.117 e 722 partidas reais,
bootstrap de 20.000 reamostragens e correção de múltiplas comparações. Abrir 15 mercados não muda
isso.

E há um risco a gerenciar: mais mercados = mais superfície onde a seção "Oportunidades
Encontradas" (EV positivo, 100% client-side) pode apontar oportunidade que é só ruído de um
modelo mal calibrado. Por isso:

- a Fase 5 só integra o que **passou** no gate;
- mercado sem calibração isotônica **não entra** em Oportunidades nem no Verificador de Bets.

---

## 11. Verificação

1. **Gate calibrado** — a Fase 1 roda nos 7 mercados em produção. Se **0/7 ou 7/7** passarem,
   revisar o limiar antes de seguir para a Fase 2.
2. **`STAT_MAP` estendido** — após o rebuild, as 7 colunas novas devem ter não-nulos entre
   **63% e 67%** (a mesma faixa das existentes). Fora disso, a política de `null` está errada.
3. **Targets de eventos** — `build_htft_targets.py` deve produzir ~21.130 linhas (com o espelho
   atual) e a distribuição das 9 combinações HT/FT deve bater com a literatura
   (H/H ≈ 26%, D/H ≈ 12%). Distribuição fora disso = bug de parse.
4. **Produção intocada** — `git status` limpo em `backend/model_artifacts{,_clubes}/` até a
   Fase 5. Antes de qualquer commit de artefato:

   ```bash
   git show HEAD:backend/model_artifacts_clubes/meta.json > /tmp/meta_head.json
   # comparar n_train / n_teams / torneios contra a cópia local
   ```

   Foi exatamente este check que pegou a degradação do modelo congelado em 2026-07-28.
5. **Ponta a ponta** — smoke test do `Predictor` isolado → `fetch` real contra o `/predict` do
   dev server → `tsc --noEmit` limpo.
   ⚠️ Se o campo novo não aparecer no fetch, **reinicie o uvicorn manualmente** antes de suspeitar
   do código: o `--reload` no Windows perde evento de mudança em `predictor.py`.
6. **Frontend** — `preview_start` + `read_page` na Análise, confirmando que os cards novos
   renderizam **e que os antigos não sumiram**.

---

## 12. Arquivos

**Novos**
`backend/scripts/gate_count_market.py` · `build_htft_targets.py` ·
`build_goal_window_targets.py` · `build_last_scorer_targets.py` ·
`train_{fouls,possession,saves,htft,last_scorer,...}_market.py`

**Modificados**
`backend/scripts/build_clubs_dataset.py:64-75` (`STAT_MAP`) ·
`backend/build_final_dataset.py:404-406` (`SB_COLS`) ·
`backend/predictor.py` (linhas O/U + `__init__` + `_predict_from_X`) ·
`frontend/src/lib/api.ts` · `frontend/src/components/platform/AnalysisResultsView.tsx` ·
`DOCUMENTACAO_CENTRAL.md` · `CLAUDE.md` · `data/MANIFEST.yaml`

**Reusados sem alterar** (não reinventar)
`backend/research_clubs/protocol.py` — harness completo do gate ·
`backend/corners_nb_model.py` — `CornersNB` ·
`backend/scripts/train_yellowcards_market.py` — template de treino ·
`backend/scripts/build_first_scorer_targets.py` — template de target por eventos ·
`backend/scripts/build_ou_calibrators.py` — calibração isotônica pós-gate ·
`backend/scripts/promotion_validation.py` — precedente de validação temporal segmentada
