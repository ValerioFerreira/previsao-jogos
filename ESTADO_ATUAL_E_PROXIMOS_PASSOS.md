# Estado atual e próximos passos (handoff)

> **Leia isto primeiro.** Resume onde o projeto está e o que fazer a seguir, para retomar
> exatamente de onde paramos. Última atualização: **2026-07-03**.
> Docs de apoio: `DOCUMENTACAO_CENTRAL.md` (doc-mestre), `ARCHITECTURE.md` (infra),
> `docs/ARQUITETURA_MONETIZACAO.md` (desenho da camada de monetização).

---

## 1. O que foi feito nesta jornada

1. **Análise/modelos (validação sob gate temporal):** executados os 6 próximos passos do handoff
   anterior — **nada de features novo promovido** (elo satura). A **única melhora promovida** foi a
   **calibração isotônica das linhas O/U** de escanteios/a-gol/cartões (chutes excluído). Docs
   antigos consolidados no `DOCUMENTACAO_CENTRAL.md`.
2. **Camada completa de usuários / monetização** (backend + frontend), do zero:
   auth (cadastro→OTP→senha→login), carteira + ledger de créditos, compra de créditos (gateway
   abstrato), documentos legais versionados, análise com **snapshot imutável**, **"Monte sua
   Aposta"** (odd ≤2,00, auto-seleção ~2,00, imutável), **liquidação automática** pós-jogo
   ("Só Paga se Acertar"), e **Painel Admin** (backend + UI) com auditoria.
3. **Frontend:** página única **Análise** (`/`) com créditos + Construção da Aposta; `/carteira`,
   `/perfil`, `/admin`, `/documentos/[type]`, **`/como-funciona`** (doc interativo). Persistência
   da análise entre navegações. Ajustes na página **Estatísticas** (detalhe de partida).
4. **UX/correções finais:** modo "Partida Futura" default; **odd justa nunca < 1,00**; página
   "Como Funciona?" com links dos tooltips; correção de **nomes de seleções** (Bósnia e
   Herzegovina, North Macedonia, Rep. of Ireland, Macau) → bandeira + partidas antigas voltam.

Tudo mergeado na **`main`** e no Neon (as 23 tabelas `app_*` foram aplicadas com
`alembic upgrade head`).

## 2. Estado atual (produção)
- **Motor de previsão:** inalterado (Dixon-Coles NB / NB cascata / GP) + calibração O/U promovida.
- **Camada de monetização:** funcional ponta a ponta, **validada ao vivo no Neon**.
- **Adapters em MOCK** (importante):
  - **E-mail OTP** → o código aparece no **log do backend** (não vai por e-mail real).
  - **Gateway de pagamento** → confirmação via `POST /payments/mock/confirm/{order_id}`.
- **Conta demo** (para revisar): `demo.apostai@gmail.com` / `Demo1234` (admin, com créditos).

## 3. Como rodar / retomar
```bash
# Backend (Neon via backend/.env):
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Frontend (aponta para :8000 via frontend/.env.local = NEXT_PUBLIC_API_URL):
cd frontend && npm run dev          # http://localhost:3000
# Migrations da camada de app (idempotente):
cd backend && .venv/Scripts/python -m alembic upgrade head
# Promover um usuário a admin:
cd backend && .venv/Scripts/python scripts/make_admin.py email@dominio.com
# Liquidar apostas (agendável):
cd backend && .venv/Scripts/python scripts/settle_bets.py
```
Mapa do código: `backend/app/domains/{users,legal,wallet,payments,analysis,bets,promotions,admin}`
(`models/schemas/service/router` cada); `frontend/src/app/*` (páginas) + `frontend/src/lib/*`
(`authApi`, `monetizationApi`, `adminApi`, `AuthContext`, `PredictionContext`).

## 4. Próximos passos (priorizados)

### Para ir a produção de verdade (monetização)
1. **JWT_SECRET real** em produção (hoje é default de dev — `app/core/config.py`). Definir a env var.
2. **Provedor de e-mail (OTP) real:** implementar o adapter Resend/SES/SMTP em `app/core/email.py`
   (interface pronta) e setar `EMAIL_PROVIDER` + credenciais. Sem isso, OTP só no log.
3. **Gateway de pagamento real:** escolher (Asaas/MercadoPago/Pagar.me/Stripe), implementar o
   adapter em `app/domains/payments/gateways/` + webhook assinado, setar `PAYMENT_PROVIDER`.
4. **Agendar a liquidação:** Task Scheduler/cron chamando `scripts/settle_bets.py` ou
   `POST /api/cron/settle-bets?token=$CRON_TOKEN` (a cada ~30 min). Definir `CRON_TOKEN`.
5. **Revisar textos legais** (Termos/Privacidade/LGPD/Créditos/Regulamento) — hoje são **templates**
   (`app/domains/legal/service.py`); publicar as versões reais pelo admin (`POST /admin/legal/publish`).

### Refinos
6. **Nomes de seleções restantes:** ~77 entidades ainda sem `team_id` são não-FIFA/históricas
   (Abkhazia, Catalonia, Padania…) ausentes da API-Football — sem solução via API. Reavaliar só se
   surgir uma nação FIFA real ainda faltando.
7. **Testes automatizados** da camada (hoje validada por scripts E2E manuais em `scratchpad`).
8. **Frontend:** polish visual, estados de erro, e testar os fluxos com providers reais.

### Analytics (motor de previsão) — janelas abertas (ver `DOCUMENTACAO_CENTRAL.md` §9)
9. **Backtest financeiro (ROI/yield) + RPS** — a validação que mais falta (acumular odds de fechamento).
10. **xG denso / tracking** — única fonte plausível de sinal novo ortogonal ao Elo.
> Já fechado/não repetir: forma de jogador no resultado, GP vs NB, calibração do resultado,
> posse/passes, XGBoost/LightGBM, cadeia de regressão, cópula, ataque×defesa, dispersão dinâmica.

## 5. Notas / gotchas
- A camada `app_*` é **isolada** do pipeline de dados; migrations não tocam as tabelas de previsão.
- O harness do Claude **bloqueia migração em produção** por auto-mode — se precisar aplicar no Neon,
  o comando `alembic upgrade head` deve ser rodado pelo dono do ambiente (ou via regra de permissão).
- Servidor de dev auxiliar em `:8001` (SQLite local) foi **aposentado** — hoje o `:8000` (Neon)
  serve tudo (previsão + monetização).
- Odd justa é referência analítica (sem margem de casa) e **nunca < 1,00**; a plataforma remunera o
  uso da IA, a promoção é campanha de estorno — não é aposta.
