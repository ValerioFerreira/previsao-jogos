# Especificação Técnica — Player-Level Power Ranking (arquitetura paralela)

> **Status:** desenho / especificação. **NÃO É PRODUÇÃO.** Pipeline estritamente
> paralelo ao atual (Elo + forma de gols). Nada aqui toca `api/model_artifacts/`,
> `predictor.py`, o front, nem a tarefa agendada de odds. Documento-manual para um
> agente autônomo iniciar a execução numa máquina nova.
>
> **Premissa:** para seleções, o Elo é defasado (jogam esparso; o rating "lava"
> devagar). A força real vem da **qualidade técnica e do ritmo atual dos jogadores**
> que entram em campo — medível pelo desempenho rotineiro deles **nos clubes**.
> **Objetivo:** substituir/complementar o Elo por um **Player-Level Power Ranking**
> agregado a partir das estatísticas individuais de clube.

---

## 0. Princípios de design (ler antes de tudo)

1. **Isolamento total da produção.** Novo diretório-raiz `player_ranking/`, nova venv,
   novo cache. Zero imports de `api/` que possam reescrever artefatos de produção.
2. **Ponto-no-tempo (anti-leakage) é requisito, não detalhe.** Toda feature de um jogo
   da seleção na data `D` só pode usar dados de clube **estritamente anteriores a `D`**.
   O endpoint `/players?season=` devolve agregados da temporada **inteira** (inclui o
   futuro relativo a `D`) → **proibido** usá-lo para treino histórico; só serve para o
   "elenco atual" em inferência. O histórico tem de ser reconstruído de dados **por jogo**.
3. **Quota é o gargalo, não a CPU.** O plano atual rende ~75k requests/dia e tem teto
   por minuto. Todo passo abaixo tem um **orçamento de requests** e **cache idempotente
   por ID** (nunca rebaixar o mesmo recurso duas vezes).
4. **Pilôto antes de backfill.** Validar o sinal num recorte pequeno (1 janela, ~20-40
   jogos de seleção) **antes** de qualquer coleta histórica em massa.
5. **Escalabilidade desenhada, não implementada.** O esquema de dados prevê **clubes**
   (generalização trivial) e **market_value** (coluna reservada, fonte futura).

---

## 1. Fluxo lógico da arquitetura

```
                            ┌──────────────────────────────────────────────┐
                            │  ALVO: prever um jogo de seleção (home,away,D) │
                            └──────────────────────────────────────────────┘
                                              │
   PASSO 1  Elenco Base ────────────────────► /fixtures?team={sel}&last=5
   (por seleção)            para cada um dos 5 jogos: /fixtures/players?fixture={id}
                            → união deduplicada de player_id  =  ELENCO BASE
                                              │
   PASSO 2  Ponte de origem ───────────────► /players?id={player}&season={Y}
   (por jogador)            extrai o clube atual e o league.id onde atua
                            → dim_player[player_id] = {club_id, league_id, ...}
                                              │
   PASSO 3  Ingestão focada ───────────────► dedup de league_id dos clubes
   (por liga/clube)         /fixtures?league={lg}&season={Y}&from=&to=   (calendário)
                            /fixtures/players?fixture={id}  (desempenho por jogo)
                            → JSON bruto salvo por liga/data
                                              │
   PASSO 4  Agregação ──────────────────────► script Pandas lê os JSON e calcula,
   (por jogador, point-in-time)  POR DATA DE CORTE, o histórico de clube de cada
                            jogador (minutos 90d, rating médio l10, chutes/passes…)
                            → fact_player_form (Parquet)
                                              │
   PASSO 5  Feature eng. ───────────────────► agrega os jogadores do Elenco Base em
   (por seleção/jogo)       features da seleção, com PESO por força de liga
                            → dataset_player_ranking.parquet  (pronto p/ ML)
                                              │
   GATE     Validação ──────────────────────► treina modelo paralelo; compara contra o
                            Elo atual no MESMO holdout temporal (log-loss/ECE).
```

---

## 2. Sequência de chamadas HTTP — API-Football v3

Base: `https://v3.football.api-sports.io` · Header: `x-apisports-key: $APIFOOTBALL_KEY`
Sempre ler os headers de resposta `x-ratelimit-requests-remaining` e
`x-ratelimit-requests-limit` e o **limite por minuto** do plano; pausar ao se aproximar.

| # | Endpoint | Parâmetros | Para quê | Custo aprox. |
|---|---|---|---|---|
| 1 | `GET /fixtures` | `team={sel_id}&last=5` | últimos 5 jogos da seleção | 1 / seleção |
| 2 | `GET /fixtures/players` | `fixture={fx_id}` | jogadores que atuaram (titulares + subs) | 5 / seleção |
| 3 | `GET /players` | `id={player_id}&season={Y}` | clube atual + `league.id` do jogador | 1 / jogador (~25-40) |
| 4 | `GET /fixtures` | `league={lg_id}&season={Y}&from={D-180}&to={D-1}` | calendário recente do clube | 1+ / liga (paginado) |
| 5 | `GET /fixtures/players` | `fixture={fx_id}` | desempenho por jogo no clube | 1 / jogo de clube |

Notas de endpoint (confirmadas pela estrutura que já usamos no projeto):
- `/fixtures/players` devolve, por time, uma lista de jogadores com bloco `statistics`
  rico: `games.minutes`, `games.rating`, `shots{total,on}`, `passes{total,key,accuracy}`,
  `tackles`, `duels`, `dribbles`, `fouls`, `cards`, `goals`, `penalty`. **É a fonte
  primária da agregação** (Passo 4).
- `/players?id=&season=` devolve `statistics[]` com `team` e `league` por competição que
  o jogador disputou na temporada — use o item de maior `games.appearences` / minutos como
  "clube principal" para resolver o `league.id` (Passo 2). **Não** usar seus agregados de
  temporada como feature de treino (leakage — ver §0.2).
- Alternativas úteis: `/players/squads?team={club_id}` (elenco de um clube — caminho
  direto para **clubes** no futuro) e `/leagues?id={lg}` (metadados/força de liga).

**Paginação:** `/players` e `/fixtures` retornam `paging.{current,total}`; iterar `page=`.
**Rate-limit:** intercalar `sleep` curto (≈0.2–0.3s) e respeitar o teto/minuto; toda
chamada bem-sucedida grava em cache para nunca repetir.

---

## 3. Estrutura do data lake local (paralelo, isolado)

```
player_ranking/                      # raiz da nova arquitetura (fora de api/)
├─ .venv/                            # venv própria (não reutilizar a de produção)
├─ .env                             # APIFOOTBALL_KEY (NUNCA commitar)
├─ config/
│  ├─ leagues_weights.yaml          # força de cada liga (multiplicador) — §6
│  └─ settings.yaml                 # season atual, janelas (90d/l10), teto de quota
├─ data/
│  ├─ raw/                          # JSON bruto da API (imutável, append-only)
│  │  ├─ fixtures/{league_id}/{season}/{fixture_id}.json
│  │  ├─ fixture_players/{fixture_id}.json          # /fixtures/players
│  │  ├─ players_profile/{season}/{player_id}.json  # /players?id=&season=
│  │  └─ national_last5/{team_id}/{season}.json     # /fixtures?team=&last=5
│  ├─ interim/                      # cruzamentos intermediários (Parquet)
│  │  ├─ dim_player.parquet         # player_id → club_id, league_id, pos, market_value*
│  │  ├─ dim_league.parquet         # league_id → nome, país, weight
│  │  ├─ dim_team.parquet           # team_id (seleção OU clube) → nome, country
│  │  └─ base_squads.parquet        # (team_id, ref_date) → [player_id]  (Elenco Base)
│  └─ processed/
│     ├─ fact_player_form.parquet   # (player_id, cutoff_date) → métricas point-in-time
│     └─ dataset_player_ranking.parquet  # (fixture_sel, home/away) → features ML
├─ src/
│  ├─ collect_base_squad.py         # Passo 1
│  ├─ resolve_player_origin.py      # Passo 2
│  ├─ ingest_club_fixtures.py       # Passo 3
│  ├─ build_player_form.py          # Passo 4 (point-in-time)
│  ├─ build_features.py             # Passo 5
│  └─ apiclient.py                  # wrapper HTTP: cache, rate-limit, retomada
└─ docs/PIPELINE.md                 # este documento (cópia local)
```

**Formatos:** **JSON** no `raw/` (espelho fiel da API, auditável, idempotente por ID);
**Parquet** no `interim/`/`processed/` (tipado, colunar, rápido para o Pandas).

**Como cruzar IDs (esquema estrela):**
- Chaves primárias: `player_id`, `team_id`, `league_id`, `fixture_id`.
- `base_squads` liga **seleção+data → jogadores** (Passo 1).
- `dim_player` liga **jogador → clube/liga** (Passo 2); é a "ponte".
- `fact_player_form` é a tabela-fato (grão = jogador × data-de-corte).
- O dataset final (Passo 5) faz: `base_squads ⋈ dim_player ⋈ fact_player_form`, agrega
  por seleção e anexa ao alvo (jogo da seleção) por `team_id` + `date`.
- `*market_value`: coluna **reservada** em `dim_player` (NULL agora; fonte futura —
  `/players` transfer/value ou provedor externo). Nenhum cálculo depende dela hoje.

---

## 4. Passo 4 — Agregação point-in-time (o coração e o maior risco de leakage)

Para cada `(player_id, cutoff_date)` necessário (as datas dos jogos de seleção no
treino + a data de inferência), calcular **apenas com jogos de clube com `date < cutoff`**:

- `minutes_90d` — soma de `games.minutes` nos últimos 90 dias.
- `matches_90d` — nº de jogos com minutos > 0 em 90 dias (proxy de ritmo).
- `rating_l10` — média de `games.rating` nos últimos 10 jogos de clube.
- `shots_l10`, `key_passes_l10`, `pass_acc_l10`, `goals_l10`, `tackles_l10`… (médias).
- `days_since_last_match` — recência (proxy de lesão/banco).
- `league_id` vigente no período (para o peso, §6).

> **Regra de ouro anti-leakage:** o filtro `date < cutoff` é por **jogo de clube**, nunca
> por agregado de temporada. Testar com um caso conhecido (um jogo antigo) e conferir que
> nenhuma estatística posterior vazou.

---

## 5. Passo 5 — Features agregadas da seleção

A partir do Elenco Base (jogadores dos 5 últimos jogos) e do `fact_player_form`:

- `team_total_competitive_minutes_90d` = Σ `minutes_90d × league_weight`.
- `team_avg_club_rating` = média de `rating_l10` ponderada por minutos (e por liga).
- `team_attack_index` = Σ ponderada de `shots_l10 + key_passes_l10 + goals_l10`.
- `team_depth` = nº de jogadores do elenco com `minutes_90d ≥ limiar` (profundidade).
- `team_freshness` = média de `days_since_last_match` (fadiga/ritmo).
- `team_top_league_share` = fração de minutos do elenco em ligas de peso alto.
- (Análogas para o adversário; o modelo usa os **diffs**, como hoje com `elo_diff`.)

Cada feature tem variante **home/away/diff**, espelhando a convenção atual do projeto.

---

## 6. Pesos de liga (`leagues_weights.yaml`)

Multiplicador por `league_id` para refletir que 90 min na Premier League ≠ 90 min numa
liga fraca. Fontes possíveis (escolher uma e documentar): coeficientes UEFA/club, ranking
de ligas, ou um peso aprendido. **Risco de overfit/subjetividade** — começar com uma
tabela fixa e simples (top-5 europeias = 1.0; demais escalonadas) e só "aprender" o peso
depois que o sinal bruto provar valor. Versão e racional ficam no YAML.

---

## 7. Escalabilidade (desenhada, não construída)

- **Clubes:** um clube é o caso trivial — o "Elenco Base" é o próprio elenco do clube
  (`/players/squads?team=`), sem a indireção dos 5 jogos. Todo o resto (Passos 2–5) é
  idêntico. `dim_team.kind ∈ {selecao, clube}` distingue.
- **Market value:** coluna `market_value` (+ `market_value_date`) em `dim_player`,
  preenchida no futuro; uma feature `team_squad_value` entra no Passo 5 sem refatorar nada.

---

## 8. Montagem do ambiente paralelo (agente de amanhã, máquina nova)

1. **Pré-requisitos:** Python 3.12, git, ~2 GB livres. Chave válida da API-Football.
2. **Isolamento:** `mkdir player_ranking && cd player_ranking` (fora de qualquer pasta de
   produção). `py -3.12 -m venv .venv` e ativar.
3. **Dependências:** `pip install requests pandas pyarrow pyyaml python-dotenv tqdm`.
4. **Segredo:** criar `.env` com `APIFOOTBALL_KEY=...` (no `.gitignore`; **nunca** commitar).
5. **Config:** `config/settings.yaml` com `season`, janelas (90d, l10), `daily_quota_cap`
   (deixar folga, ex. 60k) e `per_minute_cap`. `config/leagues_weights.yaml` com a tabela
   inicial de pesos.
6. **`apiclient.py` primeiro:** cache por ID em `data/raw/`, retomada (pula o que já existe),
   leitura dos headers de rate-limit, backoff. **Toda** coleta passa por ele.
7. **Ordem de execução:** §1 (Passos 1→5), cada script idempotente e re-executável.
8. **Smoke-test obrigatório antes do backfill:** rodar o pipeline ponta-a-ponta para **1
   jogo** (ex.: Brazil x Argentina), inspecionar `dataset_player_ranking.parquet` e
   conferir manualmente o anti-leakage num jogador.

---

## 9. Plano por fases e orçamento de quota (cota diária = 75.000 requests)

**Sequência obrigatória — nunca apontar uma coleta grande para código não-validado:**

| Fase | Escopo | Requests | Critério de saída |
|---|---|---|---|
| **F0 — Smoke** | 1 jogo, 2 seleções, ponta-a-ponta | ~10² | pipeline roda; anti-leakage conferido à mão |
| **Passo 0 — Sonda de cobertura** | amostra do espectro: top (França), médias, **minnows (Curaçao, Cabo Verde)** | ~10² | mede se `/fixtures/players` existe p/ os clubes dos atletas de cada faixa |
| **F1 — Base enriquecida** | janela recente, dimensionada para ~uso pleno da cota | ~58-70k | features plausíveis; **gate vs Elo** (§10) |
| **F2 — Backfill histórico** | só se F1 passar o gate | ~10⁵+ (vários dias) | dataset histórico utilizável |

### Modelo de custo (amortizado por janela, com cache por ID)
`custo ≈ M×6 + P×1 + C×(1+K)` — onde **M** = jogos de seleção, **P** = jogadores-base
únicos (~30/seleção), **C** = clubes únicos (~0,85·P), **K** = jogos de clube por clube.
O termo dominante é `C×(1+K)` (o `/fixtures/players` por jogo de clube) → **cachear por
clube é o que multiplica o alcance**. Sem cache, o custo ingênuo é ~620 req/jogo.

### Dimensionamento para a cota de um dia (75.000)
| Cenário | K | Cobre (~) | Requests | Observação |
|---|---|---|---|---|
| Ingênuo (sem cache) | 10 | ~120 jogos | ~75k | referência do porquê cachear |
| **A — amplo/raso (recomendado)** | 10 | **~250 jogos · ~7.000 jogadores** | ~70k | quase todo o calendário internacional recente |
| **B — focado/profundo** | 20 | ~130 jogos | ~70k | forma de clube mais robusta por jogador |
| **C — com folga p/ odds** | 10 | ~200 jogos | ~58k | deixa ~15k para a tarefa `PrevisaoJogos\CollectOdds` |

> **75k NÃO é base pequena:** com cache, compra ~200-400 jogos recentes com features
> completas — poder estatístico de sobra. **Ritmo:** respeitar o teto por minuto do plano
> (75k a ~450/min ≈ 2,8 h de coleta contínua).

> ⚠️ **Conflito de cota com a produção:** um dia a 75k zera a cota da coleta de odds da
> Copa (perde linha de fechamento dos jogos que resolvem nesse dia). Preferir o **Cenário C**
> (cap ~58-60k) ou rodar num dia de calendário leve. `daily_quota_cap` no settings.yaml
> deve refletir isso.

### 9.1 Resultado do Passo 0 — sonda de cobertura (EXECUTADO, 2026-06-21)

`player_ranking/src/probe_coverage.py` rodado em 5 seleções do espectro (259 requests no
total, 2 rodadas). **Veredito: cobertura VIÁVEL — risco nº 1 (cobertura morre nos minnows)
amplamente REFUTADO.** Fração de clubes com `/fixtures/players` utilizável (amostra de 6
jogadores-base por seleção, já filtrada para o time correto):

| Seleção | Tier | Clubes c/ stats |
|---|---|---|
| France | top (UEFA) | 6/6 |
| Japan | média (AFC) | 5/6 |
| Egypt | média (CAF) | 5/6 |
| Curaçao | minnow (CONCACAF) | 6/6 |
| Cape Verde | minnow (CAF) | 4/6 |

**Por quê funciona até nos minnows:** suas seleções são compostas por **diáspora em ligas
europeias/americanas** (Eredivisie, Bélgica, Portugal, MLS, Escócia, Irlanda) — todas cobertas.

**Falhas observadas (gerenciáveis) e ajustes que viram requisito:**
1. **Ligas fora do eixo europeu sem stats por jogador** (ex.: UAE Pro League) → **fallback
   por jogador** (Elo/default) + métrica de cobertura por seleção (sinalizar/abater times
   com poucos jogadores cobertos).
2. **Resolução de clube cai em competição de torneio** (FIFA Club World Cup, CONCACAF Gold
   Cup) quando o jogador teve mais minutos lá → **excluir todas as competições de
   torneio/seleção** na resolução, não só Copa/Nations/Amistoso; tratar `club_id == None`.
3. **Bug pego no probe (disciplina "bom demais"):** `/fixtures/players` devolve os DOIS
   times; o `base_squad` precisa **filtrar por `block.team.id == team_id`** (senão coleta o
   adversário — a 1ª rodada deu "Cape Verde" com elenco do Uruguai).

---

## 10. Critério de sucesso (GATE) — herdado da disciplina do projeto

O modelo paralelo **só avança** se, no **mesmo holdout temporal** usado hoje, as features
de player-ranking **melhorarem log-loss e ECE do resultado** sobre o baseline Elo atual —
medido com o protocolo já existente (split temporal justo, mesmas partidas de teste).
Comparar três cenários: (a) Elo só; (b) player-ranking só; (c) Elo + player-ranking.
Métrica probabilística manda (não acerto pontual). Sem ganho que sustente → não promove.

---

## 11. Riscos e mitigações (honesto)

| Risco | Severidade | Mitigação |
|---|---|---|
| Explosão de quota (Passos 3/5) | **Alta** | pilôto antes de backfill; cache por ID; orçamento por fase |
| Leakage via `/players?season=` | **Alta** | proibir agregado de temporada no treino; reconstruir por jogo; teste de corte |
| Cobertura fraca p/ minnows (jogadores em ligas obscuras sem `/fixtures/players`) | **Alta** | medir cobertura no pilôto; fallback p/ Elo quando o elenco não tem dados |
| Mapeamento jogador→clube ruidoso (transferências, empréstimos, lesões) | Média | usar clube de maior minutagem; recência; revalidar a cada season |
| Peso de liga subjetivo/overfit | Média | tabela fixa simples primeiro; só aprender peso após sinal provado |
| Esforço alto vs ganho incerto (modelo atual já perto do teto) | Média | gate explícito vs Elo; abortar cedo se F1 não mostrar sinal |

---

## 12. Resumo executivo para o agente de amanhã

Construa **`player_ranking/` isolado**, com `apiclient.py` (cache + rate-limit) primeiro.
Implemente os 5 passos como scripts idempotentes que vão do **JSON bruto por ID** ao
**Parquet de features**, cruzando tudo por `player_id`/`league_id`/`fixture_id`/`team_id`.
**Trate point-in-time como requisito** (sem agregado de temporada no treino). **Não toque
na produção.** Pare no **smoke-test (F0)** e no **pilôto (F1)**, reporte cobertura e o
**gate vs Elo** antes de qualquer backfill histórico (F2).
