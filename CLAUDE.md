# CLAUDE.md — Índice do projeto (ApostaInfo)

> **Mapa de caminhos, não enciclopédia.** Leia este arquivo primeiro para saber ONDE está cada
> coisa; o conteúdo detalhado (o quê/por quê) vive nos docs abaixo. Mantenha este índice curto.

Plataforma de **previsão probabilística de partidas** (hoje seleções; clubes em coleta).
Monorepo: **`/backend`** (FastAPI + modelos sklearn, deploy Render), **`/frontend`** (Next.js,
deploy Vercel — **apostainfo.com.br**), banco **Neon** (Postgres serverless).

## 📚 Documentação (raiz)
- **`ESTADO_ATUAL_E_PROXIMOS_PASSOS.md`** — **LEIA PRIMEIRO.** Handoff: estado atual + próximos passos.
- **`DOCUMENTACAO_CENTRAL.md`** — doc-mestre. Modelos, mercados, métricas, **§6 gate de validação**,
  **§8/§9 histórico e TESTES já feitos (não repetir)**, §12 monetização.
- **`ARCHITECTURE.md`** — infra/banco. **§3.1 otimização de Network Transfer do Neon**, **§5 camada de
  usuários**, **§6 e-mail transacional (ZeptoMail)**.
- **`docs/ARQUITETURA_MONETIZACAO.md`** — desenho da monetização (créditos/apostas/admin).
- Memória do agente: `~/.claude/projects/<proj>/memory/MEMORY.md` (índice) + arquivos.

## 🐍 Backend (`/backend`)
- `predictor.py` — classe `Predictor` (Dixon-Coles NB + contagens NB/GP em cascata). Lê **artefatos
  CSV/joblib locais**, não o banco. `app/services/predictor_service.py::get_predictor()` (lru_cache).
- `app/main.py` — **todas as rotas** (`/predict`, `/h2h`, `/api/*`, domínios montados).
- `app/services/predictor_service.py` — leitores/endpoints de dados (recent/history/goal-timing/
  referee/benchmark/injuries/pmf/scorers). **Agregados lidos de tabelas pequenas** (ver abaixo).
- `app/services/aggregates.py` + `raw_cache.py` — **otimização do Neon**: precompute de agregados
  (tabelas `*_agg`) + espelho local SQLite do bruto (`data/raw_cache.sqlite`). Ver `ARCHITECTURE.md §3.1`.
- `app/services/scorer_service.py` + `shots_prop_service.py` — props de jogador (Marcar/Finalizar).
- `app/services/fixture_fetch.py` — API-Football (cache `match_detail_cache`, `/injuries`).
- `app/domains/{auth,wallet,payments,analysis,bets,promotions,admin}` — monetização (ORM 2.0 + Alembic).
- `app/core/{config,email,startup,security,rate_limit}.py` — config/JWT/OTP/e-mail/guarda de boot.
- `app/db/connection.py` — engine SQLAlchemy (Neon) + `truncate_and_append`.
- `model_artifacts/*.joblib` — modelos em produção (DC, NB/GP, `scorer_model`, `shots_prop_model`, calibradores).
- **Dataset de treino:** `international_features_enriched_apifootball.csv` (gitignored; espelho `features_enriched`).

### Scripts (`/backend/scripts`)
- **Coleta:** `prefetch_wc_data.py` (seleções, `--all-nations`), `prefetch_clubs.py` (clubes Brasil→Europa,
  tabela `club_match_detail_cache`). **Cron:** `prefetch_wc.cmd` (Task Scheduler `\PrevisaoJogos\`).
- **Modelos:** `build_scorer_model.py`, `build_shots_prop_model.py` (leem o espelho local).
- **Agregados:** `precompute_aggregates.py` (roda após os rebuilds no cron).
- **Experimentos/testes (gate §6):** `exp6..15_*.py`, `test_player_cards.py`, `test_player_fouls.py`,
  `promotion_validation.py`, etc. **Resultados registrados em `DOCUMENTACAO_CENTRAL.md` §8/§9.**

## ⚛️ Frontend (`/frontend/src`)
- `app/page.tsx` — **Análise** (config → gerar análise → mercados → Monte sua Aposta / Funções Avançadas).
- `app/estatisticas/page.tsx` — Estatísticas (Futura/Passada/Independente; H2H, radar, minutagem, quadrantes).
- `app/como-funciona/page.tsx` — doc interativo (destaque da oferta **ParcerIA** no topo).
- `app/{entrar,cadastro,carteira,perfil,admin,documentos}` — monetização.
- `lib/api.ts` — cliente da API de previsão (**cache TTL + dedup**); `lib/{authApi,monetizationApi,adminApi}.ts`.
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
Conta demo: `demo.apostai@gmail.com` / `Demo1234` (admin, com créditos).

## ✅ Regras de ouro
- **Antes de testar hipótese de modelo:** conferir `DOCUMENTACAO_CENTRAL.md` §9 — muita coisa já foi
  reprovada (não repetir). **Após testar qualquer hipótese, registrar o resultado lá.**
- **Promoção de modelo** exige o **gate §6** (CV temporal, reduzir log-loss sem piorar ECE, consistente).
- **Coleta:** exaurir a cota diária (75k) com propósito; seleções saturaram → coletando clubes.
- **Neon:** não reintroduzir varredura de blobs (`SELECT raw FROM match_detail_cache`) em runtime — use
  os agregados. Ver `ARCHITECTURE.md §3.1`.
- Commit/push na `main` ao concluir; documentar sempre.
