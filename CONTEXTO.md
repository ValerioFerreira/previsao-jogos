# CONTEXTO DO PROJETO — Previsão de Jogos de Seleções

> Este documento existe para que um agente de IA (Claude Code) retome o trabalho a
> partir deste ponto, **sem depender de nenhuma conversa anterior**. Leia tudo antes
> de codar. Toda decisão importante já tomada está registrada aqui.

---

## 1. O que é o projeto

Sistema de **previsão de partidas de seleções masculinas** usando Machine Learning.
Dado um confronto (mandante × visitante, local, competição), o sistema prevê:

- **Vencedor** (vitória mandante / empate / vitória visitante) com probabilidades.
- **Total de gols** da partida (com intervalo de confiança de 80%).
- **Total de finalizações** da partida (com intervalo).
- **Escanteios por equipe** (mandante e visitante, com intervalo).
- **Ambas as equipes marcam** (Sim/Não) com confiança.
- **Mais/menos de 2,5 gols** (over/under) com confiança.
- **Odds justas** (1/probabilidade) derivadas de cada previsão.

Princípio inegociável do modelo: **nada de data leakage**. Toda feature é calculada
apenas com dados ANTERIORES à partida prevista (médias móveis com `shift`, Elo
pré-jogo, confronto direto histórico, etc.). As estatísticas da própria partida
nunca entram como preditor.

---

## 2. Arquitetura atual (já implementada e funcionando)

Monorepo no GitHub: `https://github.com/ValerioFerreira/previsao-jogos`

```
previsao-jogos/
├── api/                       # API FastAPI (deploy no Railway)
│   ├── predictor.py           # MOTOR DE INFERÊNCIA — núcleo do sistema
│   ├── model_artifacts/       # modelos treinados (.joblib), meta.json, results_slim.csv
│   └── ...                    # main FastAPI, requirements, Dockerfile
├── web/                       # front-end Next.js + React + TS + Tailwind (deploy na Vercel)
└── scripts/                   # utilitários (ex.: validate_fidelity.py)
```

Pipeline de dados (scripts que geram os modelos, rodam localmente):

1. **`fetch_statsbomb.py`** — (FONTE ANTIGA, será substituída) baixa e agrega dados
   do StatsBomb Open Data e gera `statsbomb_match_team_stats.csv`.
2. **`build_features.py`** — base de seleções (martj42/international_results, 1872+):
   Elo, forma móvel (3/5/10 jogos), confronto direto, descanso, contexto. Gera as
   features pré-jogo sem leakage.
3. **`build_final_dataset.py`** — junta a base com as estatísticas avançadas e cria
   versões pré-jogo (médias móveis l3/l5, "a favor" e "sofridas"), filtra últimos 10
   anos. Gera `international_features_enriched.csv`.
4. **`train_and_save.py`** — treina e salva: classificadores (vencedor, btts, over2.5)
   com RandomForest; regressão **quantílica** (q10/q50/q90 com GradientBoosting) para
   gols/escanteios/chutes. Salva snapshot por seleção e `meta.json`.
5. **`predictor.py`** — carrega os artefatos e expõe `Predictor.predict(...)`. A API
   FastAPI apenas embrulha isso em endpoints REST.

Formato que o pipeline espera das estatísticas avançadas (uma linha por equipe×partida),
gerado hoje pelo `fetch_statsbomb.py` e consumido por `build_final_dataset.py`:

```
colunas: date, team, opponent, is_home, competition, season,
         sb_shots, sb_shots_on_target, sb_corners, sb_offsides,
         sb_yellow, sb_red, sb_cards, sb_fouls, sb_possession
```

> IMPORTANTE: manter EXATAMENTE esses nomes de coluna (`sb_*`) na nova fonte, para que
> `build_final_dataset.py` e o resto do pipeline continuem funcionando sem alteração.

---

## 3. A MUDANÇA desta etapa: migrar a fonte de dados para o API-Football

### Por quê
A fonte gratuita (StatsBomb Open Data) só tem estatísticas avançadas (escanteios,
chutes, cartões, impedimentos) para ~242 jogos de grandes torneios. Isso limitou
demais os regressores de escanteios/chutes. O **API-Football** (api-football.com /
api-sports.io) tem essas mesmas estatísticas preenchidas para jogos de seleções,
permitindo expandir muito a base.

### Validação já feita (NÃO precisa refazer)
Testamos o endpoint de estatísticas com um jogo de Copa (England × Iran, 2022) e
confirmamos que vêm preenchidos: Shots on Goal, Total Shots, Corner Kicks, Offsides,
Yellow/Red Cards, Ball Possession, Fouls, etc. **A migração resolve o gargalo.**

Detalhes do formato da resposta que o código PRECISA tratar:
- Autenticação: header `x-apisports-key: <CHAVE>` (base URL `https://v3.football.api-sports.io`).
- `/fixtures/statistics?fixture=<id>` retorna `response[]` com 2 itens (um por time),
  cada um com `team.name` e uma lista `statistics[]` de `{type, value}`.
- **`Red Cards` (e às vezes outros) vem como `null` quando é zero** → normalizar para 0.
- **`Ball Possession` e `Passes %` vêm como texto com `%`** (ex.: "78%") → converter p/ número.
- Mapeamento de `type` → coluna do pipeline:
  - "Total Shots" → `sb_shots`
  - "Shots on Goal" → `sb_shots_on_target`
  - "Corner Kicks" → `sb_corners`
  - "Offsides" → `sb_offsides`
  - "Yellow Cards" → `sb_yellow`; "Red Cards" → `sb_red`; soma → `sb_cards`
  - "Fouls" → `sb_fouls`
  - "Ball Possession" → `sb_possession` (número, sem o "%")

### Restrições de cota (plano gratuito — CRÍTICO)
- **100 requisições/dia** no total. Cada partida custa 1 requisição de estatística;
  cada listagem de competição/temporada custa 1 requisição.
- Esta primeira coleta deve se **limitar a 90 requisições por execução** e respeitar
  **no máximo 10 requisições por minuto** (pausar entre chamadas).
- O script PRECISA ter: **cache em disco** (cada jogo baixado é salvo e nunca
  rebaixado), **retomada** (se parar ou bater o limite, continua de onde parou na
  próxima execução) e **contador de requisições** que para com folga antes de 90.

### Realidade temporal (CRÍTICO — hoje é junho/2026)
- A **Copa de 2026 está EM ANDAMENTO** (começou em 11/06/2026). A maioria dos 104
  jogos ainda NÃO aconteceu.
- Jogos não finalizados ficam com status `NS` e **não têm estatísticas** (só são
  preenchidas até ~48h após o fim do jogo).
- Portanto: **só pedir estatística de partidas já finalizadas (status `FT`)**. Pedir
  de jogo futuro desperdiça cota e volta vazio. Filtrar pelo status na listagem ANTES
  de gastar requisição de estatística.

### Escopo desta primeira coleta (validação)
- Copa do Mundo **2022** (`league=1&season=2022`) — 64 jogos, todos finalizados.
- Copa do Mundo **2026** (`league=1&season=2026`) — apenas os jogos já com status `FT`.
- Total estimado nesta fase: ~64 + poucos de 2026, dentro das 90 requisições.

---

## 4. Tarefa do agente (o que implementar agora)

1. Criar **`fetch_apifootball.py`** que:
   - Lê a chave de `os.environ["APIFOOTBALL_KEY"]` (NUNCA hardcode a chave).
   - Lista os fixtures de `league=1` para `season=2022` e `season=2026`.
   - Filtra só os finalizados (status `FT`) e, para cada um ainda não cacheado, busca
     `/fixtures/statistics`, respeitando 10/min e o teto de 90 req/execução.
   - Salva cache por fixture em disco (ex.: `cache_apifootball/<fixture_id>.json`) e um
     registro de progresso para permitir retomada.
   - Agrega e gera a tabela no MESMO formato `sb_*` da seção 2 (uma linha por
     equipe×partida), salvando em `apifootball_match_team_stats.csv`.
   - Normaliza os nomes das seleções para baterem com o dataset base (martj42). Há um
     mapa de normalização parecido no `fetch_statsbomb.py` — reaproveitar/estender
     (ex.: "Côte d'Ivoire" → "Ivory Coast", etc.). Verificar nomes divergentes.
   - Imprime, ao fim: quantas requisições usou, quantos jogos novos baixou, quantos
     já estavam em cache, e quantas req. restam estimadas para o dia.

2. Ajustar **`build_final_dataset.py`** para aceitar a nova fonte
   (`apifootball_match_team_stats.csv`) no lugar de (ou além de) `statsbomb_match_team_stats.csv`,
   mantendo as mesmas colunas de saída. **Não misturar as duas fontes na mesma base**
   (réguas de contagem diferentes); usar API-Football como fonte única daqui em diante.

3. Rodar o pipeline e **validar**: confirmar que as estatísticas dos jogos de 2022
   batem com a realidade (ex.: a final 2022 Argentina×France), que não há leakage, e
   que `train_and_save.py` treina sem erro com a nova base.

4. Não quebrar a API nem o front. O `predictor.py` e o contrato dos endpoints devem
   continuar funcionando. Rodar `scripts/validate_fidelity.py` se aplicável.

---

## 5. Regras de segurança e ambiente

- **Chave da API**: somente via variável de ambiente `APIFOOTBALL_KEY`. Nunca commitar.
  Adicionar `cache_apifootball/` e quaisquer `.env` ao `.gitignore`.
- **Versões**: o ambiente local de treino usa Python 3.12 (não 3.14 — há incompatibilidade
  conhecida de scikit-learn no 3.14). Os modelos `.joblib` devem ser treinados e
  carregados com a MESMA versão de scikit-learn (fixar no requirements).
- Antes de gastar cota, sempre checar o cache. A cota é o recurso mais escasso.

---

## 6. Próximos passos (depois desta validação — fora do escopo de agora)

- Se a coleta validar bem, expandir para Euro, Copa América, Copa Africana,
  eliminatórias e amistosos (provavelmente exigirá plano pago pela cota).
- Reconstruir a base completa só com API-Football e re-treinar.
- Adicionar xG e odds históricas como novas features, se o plano contratado oferecer.
