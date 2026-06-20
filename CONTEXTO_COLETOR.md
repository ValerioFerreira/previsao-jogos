# CONTEXTO — Coletor de Dados de Seleções (API-Football)

> Documento autossuficiente para o Claude Code construir o coletor de dados.
> Leia tudo antes de codar. Todas as decisões já tomadas estão aqui.

---

## 1. Objetivo

Construir um sistema de coleta que baixa o histórico completo de partidas de
**seleções masculinas adultas** do API-Football (api-sports.io), salva cada jogo em
cache no disco e, depois da carga inicial, passa a baixar **apenas jogos novos**.
O resultado final inclui um **JSON histórico consolidado** que o usuário quer guardar.

Esta é a fase de coleta. Ela alimenta o pipeline já existente do projeto
(`build_final_dataset.py` → `train_and_save.py` → `predictor.py`), que prevê
resultado, gols, escanteios, finalizações e cartões de jogos de seleções.

---

## 2. Decisões já tomadas (NÃO reabrir)

- **Escopo:** somente competições de **seleções masculinas adultas**. EXCLUIR
  explicitamente: feminino (Women), base/juvenil (U17, U19, U20, U21, U23, Youth),
  olímpico (Olympics) e qualquer coisa de clubes. Na lista de ligas do API-Football,
  as competições de seleção aparecem sob o "país" **World** (mais algumas regionais).
- **Janela temporal:** últimos **10 anos** (temporadas de **2016 em diante**).
- **Ordem de download:** da temporada **mais recente para a mais antiga** (dado
  recente é mais valioso; se interromper, já se tem o que mais importa).
- **Bloco `players`:** PRESERVAR (estatística por jogador — abre features de rating
  de elenco no futuro). NÃO descartar.
- **Compressão:** salvar os arquivos crus em **gzip** (`.json.gz`). Economiza ~80%
  de espaço sem perda. O consolidador lê de volta normalmente.
- **Limites do plano:** 75.000 requisições/dia, 450 por minuto e 7 por segundo. Mas o
  script deve se auto-regular pelos HEADERS de cada resposta (ver seção 5), não por
  números fixos.

---

## 3. Arquitetura de armazenamento (APROVADA)

Duas camadas: cache cru (caro de obter, nunca perder) + consolidado (barato, derivado).

```
data/
├── raw/
│   ├── fixtures/<league_id>/<season>/<fixture_id>.json.gz   ← jogo completo (gzip), COM players
│   └── fixtures_list/<league_id>_<season>.json              ← listagem da temporada (cache leve)
├── state/
│   └── progress.json                                        ← controle de retomada
└── built/
    ├── historico_completo.json                              ← JSON histórico consolidado (entregável)
    └── matches.parquet                                       ← versão tabular p/ o pipeline
```

- **Um arquivo por jogo.** Se `raw/fixtures/.../<fixture_id>.json.gz` existe, o jogo
  já foi baixado e NUNCA é rebaixado.
- A pasta `data/` fica **FORA do git** — adicionar `data/` ao `.gitignore`. (Milhares
  de arquivos de dados não pertencem ao repositório.)
- A chave da API vem de `os.environ["APIFOOTBALL_KEY"]` — NUNCA hardcode.

---

## 4. Como o coletor deve funcionar

`fetch_internationals.py`:

1. Lê a lista de ligas de seleção (a partir de `/leagues?type=cup` filtrado por
   país "World" + regionais relevantes; ver passo de descoberta abaixo) e monta a
   lista-alvo de `(league_id, season)` para temporadas >= 2016, EXCLUINDO
   feminino/base/olímpico.
2. Para cada `(league_id, season)`, da mais recente para a mais antiga:
   a. Busca a listagem de jogos (`/fixtures?league=<id>&season=<season>`) — 1 req —
      e cacheia em `raw/fixtures_list/`.
   b. Filtra os jogos **finalizados** (status short == "FT", e variantes de
      finalização como AET/PEN se aplicável).
   c. Para cada jogo finalizado SEM cache: busca o jogo completo
      (`/fixtures?id=<fixture_id>` — traz events, lineups, statistics, players) — 1 req —
      e salva `.json.gz`.
   d. Jogo já cacheado é PULADO sem gastar requisição.
3. **Retomada:** `progress.json` marca temporadas encerradas como "fechadas" (nunca
   mais tocadas) e temporadas em andamento como "abertas" (relistadas a cada execução,
   baixando só jogos novos já finalizados). Permite rodar em vários dias.

### Descoberta de ligas de seleção
Já temos a lista de IDs (via `/leagues?type=cup`, país "World"). Competições de seleção
masculina adulta relevantes incluem (confirmar/atualizar via API):
World Cup (1) e eliminatórias (29-34, 37), Euro (4) e qualificação (960),
Copa America (9), Africa Cup of Nations (6) e qualificação (36), Asian Cup (7) e
qualificação (35), Gold Cup (22) e qualificação (858), UEFA Nations League (5),
CONCACAF Nations League (536), Confederations Cup (21), Finalissima (913),
Arab Cup (860), Gulf Cup (25), CAFA Nations Cup (1008), Friendlies (10), FIFA Series (1222).
EXCLUIR tudo com Women/U17/U19/U20/U21/U23/Youth/Olympics no nome.
Antes de baixar em massa, IMPRIMA a lista-alvo final de ligas+temporadas e o total
estimado de requisições, e peça confirmação do usuário.

---

## 5. Auto-regulação pelos limites (CRÍTICO)

A cada resposta, a API devolve headers:
- `x-ratelimit-requests-limit` / `x-ratelimit-requests-remaining`: cota DIÁRIA.
- `X-RateLimit-Limit` / `X-RateLimit-Remaining`: cota por MINUTO.

O script deve:
- Ler esses headers e se governar por eles (não por constantes fixas).
- Respeitar o teto por minuto: pausar quando `X-RateLimit-Remaining` estiver baixo.
- Aplicar um freio adicional de no máximo ~7 requisições/segundo (evitar rajadas).
- **Encerrar a execução do dia com folga**: parar quando
  `x-ratelimit-requests-remaining` chegar a ~500 (margem de segurança), NÃO raspar
  até zero.
- Tratar HTTP 429 (rate limit) com backoff e retomada, sem perder progresso.
- Imprimir, ao fim de cada execução: requisições usadas, jogos novos baixados, jogos
  já em cache, cota diária restante, e o que falta para completar.

---

## 6. Consolidador

`build_history.py`:
- Lê todos os `.json.gz` de `data/raw/fixtures/`.
- Monta `data/built/historico_completo.json` (o entregável que o usuário quer).
- Monta `data/built/matches.parquet` (tabular, pronto para o pipeline de features).
- É barato e 100% reconstruível a partir do cache cru. Pode rodar quantas vezes quiser.
- Normaliza nomes de seleções para baterem com a base martj42 (reaproveitar o mapa de
  normalização já usado em `fetch_apifootball.py`: ex. "IR Iran"→"Iran",
  "Korea Republic"→"South Korea", "Côte d'Ivoire"→"Ivory Coast", etc.).

---

## 7. Segurança e ambiente

- Chave SÓ via `APIFOOTBALL_KEY` (variável de ambiente). Nunca commitar.
- `data/` e `.env` no `.gitignore`.
- Python 3.12 (não 3.14 — incompatibilidade conhecida de libs de ML).
- Sempre checar cache antes de gastar requisição. Cota é o recurso escasso.
- NÃO tocar nos modelos/artefatos existentes (`api/model_artifacts*`, `predictor.py`,
  `train_and_save*.py`). Esta etapa é só coleta.

---

## 8. Fora de escopo agora (não fazer)

- Clubes (será um projeto separado, com Elo e pipeline próprios).
- Novas features no modelo (peso temporal, Poisson, calibração) — etapas futuras.
- Re-treino dos modelos — só depois de a base estar coletada e consolidada.
