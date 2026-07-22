# CLAUDE.md — Índice do projeto (ApostaInfo)

> **Mapa de caminhos, não enciclopédia.** Leia este arquivo primeiro para saber ONDE está cada
> coisa; o conteúdo detalhado (o quê/por quê) vive nos docs abaixo. Mantenha este índice curto.

Plataforma de **previsão probabilística de partidas** — **produção: seleções E clubes**
(mercados de clube lançados em 2026-07-18, mesmo menu de mercados de seleção, ver §14 do
doc-mestre; coleta de clube em 68 competições — 60 completas, 8 novas ~92% coletadas, ver §17;
artefato de produção cobre 52 torneios, DC-NB de clube com GAP ratings desde 2026-07-19, ver §17).
Monorepo: **`/backend`** (FastAPI + modelos sklearn, deploy Render), **`/frontend`**
(Next.js, deploy Vercel — **apostainfo.com.br**), banco **Neon** (Postgres serverless).

## 📚 Documentação (raiz)
- **`ESTADO_ATUAL_E_PROXIMOS_PASSOS.md`** — **LEIA PRIMEIRO.** Handoff: estado atual + próximos passos.
  **§2.1 = checklist do que falta para a monetização vender de verdade** (credenciais MP, textos
  jurídicos, nota fiscal — nada é código pendente).
- **`DOCUMENTACAO_CENTRAL.md`** — doc-mestre. Modelos, mercados, métricas, **§6 gate de validação**,
  **§8/§9 histórico e TESTES já feitos (não repetir)**, **§12 monetização (§12.7 = conversão
  completa, gateway MP/cupons/afiliados/analytics/admin, 2026-07-11; §12.8 = merge na `main` +
  nota fiscal sob demanda, 2026-07-13; §12.9 = código p/ Mercado Pago real + nota fiscal automática
  via NFE.io, 2026-07-16 — falta só o runbook do dono)**, **§13 pesquisa de clubes (branch `clubs`,
  2026-07-15 — arquitetura atual venceu tudo, sem exceção de push)**, **§14 mercados de clubes em
  produção (2026-07-18 — `scope="selecao"|"clube"` ponta a ponta, gaps documentados)**, **§15
  partida agendada de clube + Elo histórico real + retreino 60 ligas (2026-07-18, mesmo dia —
  fecha os gaps da §14)**, **§16 bateria de 12 hipóteses (dataset 60 ligas) + 3 mercados novos:
  1º/2º tempo pra clube, cartões vermelhos, time a marcar primeiro (2026-07-19)**, **§17 fecha
  as hipóteses pendentes do §16 — GAP ratings PASSOU o gate e foi promovido pro DC-NB de clube
  (158→170 features); mercados novos: cartões amarelos, qualificação/agregado em mata-mata
  ida-volta; +8 competições em coleta (mesmo dia, 2026-07-19)**, **§18 reforma da monetização
  (2026-07-21): créditos promocionais (boas-vindas 0 + saldo `promo_balance` consumido antes do
  pago e nunca reservado), 2 tipos de cupom de parceiro (convite 1ª-compra+5 promo; promocional
  solicitado→aprovado pelo admin com prazo/faturamento), indicação de parceiros (`parent_affiliate_id`
  + override 5%, um nível) e badge de pendências no admin — backend testado, migrations Postgres**,
  **§19 bateria H1-H4 (empate/valor/de-vig/xG, 2026-07-21/22) — nenhuma promoção de modelo (H4 xG
  reprovado pela 3ª vez, H1 é achado de produto); coleta 68→83 competições de clube (cota resetou
  no meio da sessão, aproveitada); achado de infra: coleta forward de odds de clube não está no
  cron. Relatório completo em `backend/data/reports/RESUMO_BATERIA.md`**.
- **`ARCHITECTURE.md`** — infra/banco. **§3.1 otimização de Network Transfer do Neon**, **§5 camada de
  usuários/monetização**, **§6 e-mail transacional (ZeptoMail)**, **§7 ambiente de pesquisa
  reproduzível (venv, segredos, dados, jobs em background — leia antes de rodar experimentos numa
  máquina nova)**.
- **`docs/ARQUITETURA_MONETIZACAO.md`** — desenho original da monetização (créditos/apostas/admin).
- **`backend/docs/PESQUISA_CLUBES.md`** — diário completo da pesquisa de clubes (literatura,
  candidatos, protocolo, todos os experimentos); **`backend/docs/RELATORIO_FINAL_PESQUISA_CLUBES.md`**
  — números consolidados (gerado por `scripts/clubs_consolidate.py`).
- Memória do agente: `~/.claude/projects/<proj>/memory/MEMORY.md` (índice) + arquivos.

## 🐍 Backend (`/backend`)
- `predictor.py` — classe `Predictor` (Dixon-Coles NB + contagens NB/GP em cascata). Lê **artefatos
  CSV/joblib locais**, não o banco. `app/services/predictor_service.py::get_predictor()` (lru_cache)
  serve seleção; `get_club_predictor()` serve clube (mesma classe, `art_dir` diferente).
- `app/main.py` — **todas as rotas** (`/predict`, `/h2h`, `/api/*`, domínios montados). Rotas
  relevantes (predict/teams/team/h2h/team-ids/benchmark/pmf/scorers) aceitam
  `scope: "selecao"|"clube"` (default `"selecao"`, retrocompatível) — ver §14 do doc-mestre.
  `GET /api/aggregate` (novo 2026-07-19, §17) — qualificação/agregado em mata-mata ida-volta
  (`Predictor.predict_aggregate`), mesmo cálculo já anexado em `/predict` (`mata_mata_agregado`)
  pras competições continentais de clube com 2 pernas.
- `app/services/predictor_service.py` — leitores/endpoints de dados (recent/history/goal-timing/
  referee/benchmark/injuries/pmf/scorers). **Agregados lidos de tabelas pequenas** (ver abaixo).
  `_predictor_for(scope)` escolhe entre `get_predictor()`/`get_club_predictor()`; endpoints sem
  base de dado de clube ainda (recent/history/benchmark/goal-timing) degradam vazio p/ clube.
- `scripts/build_clubs_production_artifacts.py` + `model_artifacts_clubes/*.joblib` — artefato de
  produção de clube (2.326 times/191.580 jogos/52 torneios, retreino 2026-07-19 §17), mesma
  arquitetura/hiperparâmetros da §13 **+ GAP ratings de chutes/escanteios no DC-NB** (158→170
  `base_feats`, único achado que passou o gate na bateria do §16/§17 — `meta["gap_ratings_state"]`
  guarda o rating final por time, servido em `predictor.py::build_row()` no mesmo padrão do Elo).
  Nomes de time desambiguados por colisão real (`"Nome (Liga)"`); `team_ids` (p/ escudo)
  resolvido do próprio `meta.json`, não do Neon (que só tem seleção).
- `app/services/aggregates.py` + `raw_cache.py` — **otimização do Neon**: precompute de agregados
  (tabelas `*_agg`) + espelho local SQLite do bruto (`data/raw_cache.sqlite`). Ver `ARCHITECTURE.md §3.1`.
- `app/services/scorer_service.py` + `shots_prop_service.py` — props de jogador (Marcar/Finalizar).
- `app/services/fixture_fetch.py` — API-Football (cache `match_detail_cache`, `/injuries`).
- `app/domains/{auth,wallet,payments,analysis,bets,promotions,admin,affiliates,campaigns,analytics,
  notifications,support}` — monetização (ORM 2.0 + Alembic, já na `main`). Gateway real: `payments/
  gateways/mercadopago.py` (código pronto, falta credencial de produção — runbook em
  `DOCUMENTACAO_CENTRAL.md` §12.9). Nota fiscal: emissão automática via `payments/invoicing.py` +
  `payments/invoicing_nfeio.py` (adapter NFE.io, assíncrono — `check_status()`/`invoice_poll.py`
  fazem o polling; `NoopInvoiceProvider` continua o default seguro sem `INVOICE_PROVIDER=nfeio`),
  mas a **exibição ao cliente é sob demanda** (`invoice_requested_at` +
  `POST /payments/orders/{id}/request-invoice` + botão "Solicitar nota fiscal" na Carteira).
- `app/core/{config,email,startup,security,rate_limit}.py` — config/JWT/OTP/e-mail/guarda de boot.
- `app/db/connection.py` — engine SQLAlchemy (Neon) + `truncate_and_append`.
- `model_artifacts/*.joblib` — modelos em produção (DC, NB/GP, `scorer_model`, `shots_prop_model`, calibradores).
  Opcionais (ausência = mercado não exposto, `Predictor.__init__` checa `os.path.exists`):
  `offsides_nb`, `gols_{1,2}t_nb`/`cartoes_{1,2}t_nb` (por-tempo — clube ganhou em 2026-07-19),
  `cartoes_vermelhos_nb`, `first_scorer_clf` (2026-07-19, ambos escopos, §16), `cartoes_amarelos_nb`
  (2026-07-19, ambos escopos, §17) — ver DOCUMENTACAO_CENTRAL.md.
- **Dataset de treino:** `international_features_enriched_apifootball.csv` (gitignored; espelho `features_enriched`).

### Scripts (`/backend/scripts`)
- **Coleta:** `prefetch_wc_data.py` (seleções, `--all-nations`), `prefetch_clubs.py` (clubes, **68
  competições** — 60 completas (26 originais + 34 de expansão 2026-07-15/18) + 8 novas 2026-07-19
  (copas dos "big five" + Índia/Tailândia, ~92% coletadas, ver §17.6), `LEAGUES` no topo do arquivo
  — tabela `club_match_detail_cache` + espelho local `data/club_raw_cache.sqlite`).
  `prefetch_clubs_parallel.py` (versão paralela p/ backfill grande — ~380 req/min vs ~15-20/min do
  sequencial). `mirror_club_cache.py` (backfill único via API, zero egress do Neon).
  `collect_club_odds_forward.py` (odds futuras de clubes, novo). **Cron:** `prefetch_wc.cmd` (Task
  Scheduler `\PrevisaoJogos\`). **Checar cota/validade da assinatura antes de coleta grande:** ver
  `ARCHITECTURE.md §7.2`.
- **Modelos:** `build_scorer_model.py`, `build_shots_prop_model.py` (leem o espelho local).
  **Mercados por-tempo/vermelhos/marcador-primeiro (2026-07-19, §16):**
  `build_clubs_halftime_targets.py` + `train_clubs_halftime_markets.py` (1º/2º tempo pra clube),
  `train_redcards_market.py --scope {selecao,clube}` (cartões vermelhos isolados),
  `train_yellowcards_market.py --scope {selecao,clube}` (cartões amarelos isolados, §17.3),
  `build_first_scorer_targets.py` + `train_first_scorer_market.py --scope {selecao,clube}` (time
  a marcar primeiro) — todos 100% locais (leem `data/{club_,}raw_cache.sqlite`), opcionais em
  `predictor.py`.
- **Agregados:** `precompute_aggregates.py` (roda após os rebuilds no cron). `build_elo_history.py`
  (novo, §15 do doc-mestre — deriva `elo_history.csv` de cada `model_artifacts{,_clubes}/` a
  partir do `home_elo_pre`/`away_elo_pre` já presente no dataset de treino; sem custo de API).
- **Experimentos/testes (gate §6):** `exp6..15_*.py`, `test_player_cards.py`, `test_player_fouls.py`,
  `promotion_validation.py`, etc. **Resultados registrados em `DOCUMENTACAO_CENTRAL.md` §8/§9.**
- **Pesquisa de clubes (`clubs_*.py` + `/backend/research_clubs/`):** protocolo único, ratings da
  literatura, modelos estatísticos/GBM/state-space/ensemble/deep tabular. Ver `DOCUMENTACAO_CENTRAL.md
  §13` e `backend/docs/PESQUISA_CLUBES.md` antes de propor um novo candidato — muita coisa já foi
  testada e reprovada lá também.

## ⚛️ Frontend (`/frontend/src`)
- `app/page.tsx` — **Análise** (config → gerar análise → mercados → Monte sua Aposta / Funções Avançadas).
  Toggle Seleções/Clubes na Análise Independente (`scope` em `PredictionContext`); banner de
  lançamento de mercados de clube com CTA (`ClubMarketsBanner`).
- `app/estatisticas/page.tsx` — Estatísticas (Futura/Passada/Independente; H2H, radar, minutagem, quadrantes).
- `app/como-funciona/page.tsx` — doc interativo (destaque da oferta **ParcerIA** no topo).
- `app/{entrar,cadastro,carteira,perfil,admin,afiliado,documentos}` — monetização. `carteira`
  redesenhada p/ conversão (banner/selos/cupom/PIX pendente/minhas compras); `afiliado` = portal.
- `lib/api.ts` — cliente da API de previsão (**cache TTL + dedup**); `lib/{authApi,monetizationApi,
  adminApi,affiliatesApi}.ts`.
- `lib/PredictionContext.tsx` (análise persiste em localStorage), `lib/AuthContext.tsx` (JWT).
- `components/platform/*` — cards (MarketCard, H2HCard, ScorersCard, DerivedMarkets, BetBuilder, MatchHeader…).

## ▶️ Rodar
```bash
# tudo junto (raiz):        npm run dev
# backend:  cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
# frontend: cd frontend && npm run dev            # http://localhost:3000 (aponta p/ :8000 via .env.local)
# migrations app_*:  cd backend && python -m alembic upgrade head
# verificar cadastro (sem rede/banco): cd backend && python -m scripts.verify_signup_flow
```
Conta demo: `demo.apostai@gmail.com` / `Demo1234` (admin, com créditos) — **login retornou 401 em
2026-07-18** (Neon local), não investigado ainda; confirmar credencial antes de depender dela p/
teste de UI autenticado.

## ✅ Regras de ouro
- **Antes de testar hipótese de modelo:** conferir `DOCUMENTACAO_CENTRAL.md` §9 **e** §13 (pesquisa
  de clubes) — muita coisa já foi reprovada (não repetir). **Após testar qualquer hipótese,
  registrar o resultado lá** (ou em `backend/docs/PESQUISA_CLUBES.md` se for sobre clubes).
- **Promoção de modelo** exige o **gate §6** (CV temporal, reduzir log-loss sem piorar ECE, consistente).
  Pesquisa em branch (`clubs` ou nova) **não dá push para `main`** a menos que bata a produção real
  sob o gate — é a exceção documentada em §13.
- **Coleta:** exaurir a cota diária (75k) com propósito; seleções saturaram, clubes em 68
  competições (60 completas + 8 novas ~92%, ver §17.6), artefato treinado cobre 52 torneios.
  **Checar a validade da assinatura da API-Football** (`GET /status` → `subscription.end`) antes de
  planejar coleta de vários dias — ela tem prazo, não é indefinida.
- **Neon:** não reintroduzir varredura de blobs (`SELECT raw FROM match_detail_cache`) em runtime — use
  os agregados. Ver `ARCHITECTURE.md §3.1`. O mesmo vale para `club_match_detail_cache` — sempre usar
  o espelho local (`data/club_raw_cache.sqlite`), nunca puxar os blobs do Neon em runtime/jobs.
- **Ambiente novo (outra máquina):** ver `ARCHITECTURE.md §7` — venv não é portável, `requirements.txt`
  separa produção de pesquisa, `data/` é gitignored e precisa ser regenerado ou copiado.
- **Monetização:** cupom (benefício ao usuário) e afiliado (comissão) são **independentes** — nunca
  acoplar a lógica dos dois. Gateway/nota fiscal são adapters trocáveis (`PaymentGateway`/
  `InvoiceProvider` Protocol) — nunca hardcode o provedor num domínio; troque via `PAYMENT_PROVIDER`
  e a fábrica em `gateways/__init__.py`. Antes de vender de verdade, ver checklist em
  `ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` §2.1 (credenciais MP, textos jurídicos, nota fiscal).
- Commit/push na `main` ao concluir; documentar sempre.
