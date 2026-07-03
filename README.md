# Previsão de Jogos (ApostAI)

Plataforma de **previsão probabilística de partidas de seleções** (futebol internacional).
Monorepo:
- **`/frontend`** — Next.js (TypeScript), deploy na **Vercel**.
- **`/backend`** — FastAPI (Python), deploy no **Render**; modelos em `backend/model_artifacts/`.
- **Banco** — **Neon** (PostgreSQL serverless).

## Documentação

- **[`DOCUMENTACAO_CENTRAL.md`](DOCUMENTACAO_CENTRAL.md)** — documento-mestre único: o que o
  projeto prevê, dados, modelos (e por quê), métricas explicadas, todo o histórico de
  desenvolvimento com os achados de cada tentativa, e as janelas de oportunidade abertas.
- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — infraestrutura, deploy e banco de dados (Neon/SQLAlchemy).

## Rodar localmente

```bash
npm install          # dependências da raiz (concurrently)
npm run install:all  # dependências de frontend e backend
npm run dev          # sobe frontend (porta 3000) e backend (porta 8000) juntos
```

Só o backend:
```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

## Variáveis de ambiente

- **`/frontend/.env`** — `NEXT_PUBLIC_API_URL` (URL do backend no Render).
- **`/backend/.env`** — `DATABASE_URL` (Neon), `FRONTEND_URL` (CORS), `APIFOOTBALL_KEY`.

Detalhes em [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Odds justas

As odds exibidas são **odd justa = 1 / probabilidade** (sem margem da casa), referência
analítica para comparar com o mercado — não recomendação de aposta. Nenhuma previsão garante
resultado.
