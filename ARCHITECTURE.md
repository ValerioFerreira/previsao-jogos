# System Architecture

Este documento descreve a arquitetura técnica, a estratégia de infraestrutura e os fluxos de dados do projeto de Previsão de Jogos.

## 1. Visão Geral da Arquitetura (Monorepo)

O projeto está organizado em um **Monorepo**, dividindo claramente as responsabilidades de interface e processamento de dados. 

- **`/frontend`**: Desenvolvido em **Next.js (TypeScript)**. Responsável pela interface do usuário, consome a API do backend para exibir previsões, estatísticas e históricos.
- **`/backend`**: Desenvolvido em **Python (FastAPI)**. Lida com a coleta de dados de terceiros, execução de scripts de ETL, treinamento/inferência de modelos de Machine Learning e disponibiliza endpoints de API rápidos.

**Desenvolvimento Local**:
O repositório possui um `package.json` na raiz configurado com o `concurrently`. Para rodar todo o sistema (Frontend e Backend) simultaneamente em ambiente de desenvolvimento, basta executar:
```bash
npm run dev
```

## 2. Estratégia de Deploy

A infraestrutura foi desenhada para otimização de custos e performance, hospedando cada serviço em provedores especializados:

- **Frontend (Vercel)**:
  - Hospedado nativamente na Vercel para tirar proveito da CDN global do Next.js.
  - A comunicação com o backend é gerenciada pela variável de ambiente `NEXT_PUBLIC_API_URL` (ex: `https://api-previsao-jogos.onrender.com`).

- **Backend (Render / Railway)**:
  - Hospedado como um Web Service.
  - O diretório raiz no Render deve ser configurado como `/backend`.
  - **Porta Dinâmica**: O servidor `uvicorn` roda com `--host 0.0.0.0` e escuta a porta definida pelo ambiente (`process.env.PORT` ou configuração interna do Render/Railway).
  - **CORS**: O acesso ao backend é estritamente controlado via CORS, aceitando tráfego apenas da origem oficial do frontend através da variável `FRONTEND_URL`. (No ambiente local, `http://localhost:3000` é permitido por fallback).

## 3. Arquitetura de Banco de Dados (Neon Serverless PostgreSQL)

Anteriormente, o sistema utilizava armazenamento efêmero local (arquivos JSON, CSV e Parquet). Como provedores de hospedagem serverless/PaaS possuem discos temporários, a persistência de dados foi migrada para o **Neon PostgreSQL Serverless**.

### Gerenciamento de Conexão e Escalabilidade
O banco de dados é gerenciado via `SQLAlchemy`. Devido ao comportamento "Serverless" do Neon (que suspende a instância após inatividade para economizar custos), a Engine do SQLAlchemy é configurada com estratégias de mitigação:
- **`pool_pre_ping=True`**: Verifica passivamente a saúde da conexão TCP antes de enviar a consulta. Se a conexão for fechada por inatividade da Neon, o pool reestabelece uma nova automaticamente.
- **Dimensionamento de Pool**: Conexões limitadas (`pool_size=5`, `max_overflow=10`) para prevenir gargalos simultâneos pesados.

### Estratégias de Escrita (ETL)

O módulo de conexão ( `app.db.connection` ) exporta funções avançadas para garantir atualizações íntegras em produção:

1. **`upsert_df`**:
   - Utilizado para atualizações incrementais contínuas (ex: logs, telemetria).
   - Baseia-se em `on_conflict_do_update` (Upsert nativo do PostgreSQL), garantindo que dados duplicados não existam sem onerar a memória com deleções em lote.

2. **`truncate_and_append`** (Atomicidade Crítica):
   - Utilizado pelos pesados pipelines de ML que regeneram históricos inteiros (`build_history.py`, `build_final_dataset.py`).
   - Diferente do destrutivo `df.to_sql(if_exists='replace')`, esta função mantém a estrutura e os índices essenciais.
   - **Garantia Transacional**: O comando cru de `TRUNCATE TABLE` e o respectivo `append` ocorrem estritamente na *mesma transação SQL*. Se a inserção de dados falhar por formatação incorreta, o `TRUNCATE` sofre rollback, impedindo que a API do frontend quebre por consultar uma tabela acidentalmente vazia.

### Cache dos dados crus: arquivos em disco, não JSONB
> Corrigido em 2026-07-08 após medição. A versão anterior desta seção descrevia um
> "Raw Data Lake" em coluna `JSONB`, que **nunca existiu no código**.

O que de fato acontece:
- Os retornos crus da API-Football são gravados como **arquivos JSON em disco**
  (`cache_apifootball/`, `data/raw/`). Não há nenhuma coluna `JSONB` de fixtures. As únicas
  colunas `JSONB` do projeto são `app_admin_audit_log` (before/after) e `app_platform_settings`.
- A tabela `fixture_index` mapeia `key -> path`, onde `path` é o **caminho de um arquivo local**
  (`predictor_service.py::_fixture_index`). O Postgres guarda o índice; o conteúdo fica no disco.
- `build_history.py` grava `data/built/historico_completo.json` (~205 MB) **somente em disco**;
  para o Postgres vai apenas um DataFrame achatado (tabela `matches`, ~101 KB em Parquet).

Tabelas de dados realmente escritas no Postgres: `matches`, `features_enriched` (a maior — vem de
um CSV de ~17 MB), `apifootball_match_team_stats`, `fixture_index`, `odds_registry` (cresce a cada
coleta de odds), `past_fixtures`, `referees`, `team_ids`, `match_detail_cache` (detalhe das
seleções — alimenta as páginas Estatísticas e os modelos de jogador), `injuries_cache` (desfalques,
TTL 12h) e **`club_match_detail_cache`** (detalhe dos CLUBES — coleta iniciada em 2026-07-09/10 para
a próxima adição ao sistema, na ordem de prioridade Brasil→Europa: Série A/B, Copa do Brasil, depois
Premier/La Liga/Serie A/Bundesliga/Ligue 1; `scripts/prefetch_clubs.py`, com `league_id`). É uma
**tabela separada** para não contaminar os modelos de seleção, que varrem apenas `match_detail_cache`.
(A `serie_a_detail_cache` do primeiro dia foi superada por esta, mais geral.)

### 3.1 Network Transfer do Neon — otimização (2026-07-10)
Um pico de **5,58 GB de egress** (com storage de só ~55 MB) veio de **leituras repetidas de
blobs**: o `match_detail_cache` (raw JSON, 44 MB) era escaneado **inteiro** pelo Fator Árbitro
(a cada cold start do Render), por-time pela Minutagem, e **2×/dia** pelos rebuilds de modelo.
Correções (commit da sessão 2026-07-10):
- **Agregados precomputados** (`app/services/aggregates.py`, `scripts/precompute_aggregates.py`):
  o job diário faz **1 passada** sobre o bruto e grava tabelas PEQUENAS no Neon —
  `referee_stats_agg` (264 kB), `goal_timing_agg` (280 kB), `competition_bench_agg` (16 kB),
  `agg_kv`. Os endpoints `get_referee_stats`/`get_goal_timing`/`get_competition_benchmark` leem
  **1 linha** (bytes) em vez de escanear 44 MB. Fallback on-the-fly se ainda não precomputado.
- **Espelho local do bruto** (`app/services/raw_cache.py`, SQLite em `backend/data/raw_cache.sqlite`):
  os rebuilds de modelo e o precompute leem o bruto do **disco local** (máquina 24h) → **zero
  egress do Neon** nos jobs. O prefetch grava no espelho junto do Neon.
- **Column pruning + LIMIT + parametrização** em `anomaly_detector`, `get_team_history`,
  `get_recent_matches` (também fecha SQLi por f-string).
- **Frontend:** cache TTL (5 min) + dedup em `frontend/src/lib/api.ts`.

Resultado estimado: **~5,58 GB/mês → < 0,5 GB/mês** (o transfer passa a escalar com ações
transacionais pequenas, não com blobs). O runtime só lê o bruto do Neon em `/api/match-detail`
(1 jogo por vez, sob demanda na Estatística → Partida Passada).

**Ainda em aberto (opcional):** tirar o `match_detail_cache` do Neon de vez, deixando o bruto só
no espelho local + servindo `/api/match-detail` via API interna/túnel — reduziria o storage/egress
residual a ~zero. Antes de mover qualquer coisa "para economizar Neon", medir de verdade:
```sql
SELECT relname AS tabela, pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 15;
```

## 4. Referência de Variáveis de Ambiente

Ao clonar o projeto, devem ser criados os arquivos `.env` nas respectivas pastas.

### `/frontend/.env`
```env
# URL da API do backend de produção (sem / no final)
NEXT_PUBLIC_API_URL=https://sua-api.onrender.com
```

### `/backend/.env`
```env
# URL oficial de conexão do banco de dados (Neon PostgreSQL)
DATABASE_URL=postgresql://user:password@ep-cool-sun-1234.us-east-2.aws.neon.tech/dbname?sslmode=require

# Origem oficial permitida do Frontend (para bloqueio de segurança CORS)
FRONTEND_URL=https://seu-frontend-producao.vercel.app

# Porta de escuta do Uvicorn (Opcional, Render gerencia isso dinamicamente)
PORT=8000

# Chave da API-Football usada pelos coletores ETL.
# Atenção ao nome: os coletores (fetch_apifootball.py, fetch_internationals.py,
# scripts/fetch_odds.py, scripts/collect_odds_forward.py) leem APENAS `APIFOOTBALL_KEY`.
# Só `app/services/fixture_fetch.py` também aceita o alias `API_FOOTBALL_KEY`.
APIFOOTBALL_KEY=your_api_football_key

# Camada de usuários: ambiente, JWT e e-mail transacional. Lista completa em §6.5.
# APP_ENV=production faz o backend recusar o boot com config de e-mail/JWT inválida.
APP_ENV=development
JWT_SECRET=dev-insecure-change-me
EMAIL_PROVIDER=mock
EMAIL_FROM=no-reply@seudominio.com
ZEPTOMAIL_TOKEN=

# Gateway de pagamento (§5) — PAYMENT_PROVIDER=mock (dev) | mercadopago (produção).
# Sem MP_ACCESS_TOKEN/MP_WEBHOOK_SECRET reais, o backend continua em mock mesmo se
# PAYMENT_PROVIDER=mercadopago (create_checkout falha com RuntimeError explícito).
PAYMENT_PROVIDER=mock
FRONTEND_BASE_URL=http://localhost:3000
MP_ACCESS_TOKEN=
MP_PUBLIC_KEY=
MP_WEBHOOK_SECRET=
MP_WEBHOOK_URL=
```
> O `backend/.env` é lido diretamente pelo `app/core/config.py` (via `env_file`). Variáveis de
> ambiente reais (Render) têm precedência sobre o arquivo. Ver §6.4.

## 5. Camada de Usuários / Monetização (tabelas `app_*`)

Introduzida em 2026-07. Estende o mesmo FastAPI/Neon com estado transacional, **isolada** do
pipeline de dados/previsão (que segue intacto).

- **ORM declarativo + Alembic.** Diferente do pipeline (SQLAlchemy Core + pandas), a camada
  transacional usa **ORM 2.0** (`backend/app/db/base.py`) e **migrations** (`backend/alembic/`).
  As migrations gerenciam **apenas** as tabelas com prefixo `app_` (filtro em `alembic/env.py`);
  as tabelas de dados (`matches`, `fixture_index`, `odds_registry`…) não são tocadas.
  Aplicar/atualizar: `cd backend && .venv/Scripts/python -m alembic upgrade head`.
- **Estrutura modular por domínio:** `backend/app/domains/{users,legal,wallet,payments,analysis,
  bets,promotions,admin,affiliates,campaigns,analytics,notifications,support}` — cada um com
  `models.py`/`schemas.py`/`service.py`/`router.py`. Os 5 últimos (afiliados, campanhas,
  analytics, notificações, suporte) entraram em 2026-07-11 (monetização de conversão — ver
  `DOCUMENTACAO_CENTRAL.md` §12.7) e já estão na `main` desde 2026-07-13 (§12.8). Config central em
  `backend/app/core/config.py` (pydantic-settings). Segurança em `app/core/security.py`
  (argon2 + JWT + OTP), validação CPF/telefone em `app/core/validators.py`.
- **36 tabelas `app_*`** no Neon (já criadas em produção): usuários/OTP/sessões/auditoria,
  carteira + **ledger** de créditos (saldo só via lançamento, idempotência), pagamentos (com
  cupom/afiliação/nota fiscal por pedido), análises com snapshot imutável, apostas + liquidação,
  promoções/cupons, afiliados/atribuição/comissão, campanhas/experimentos A-B, eventos de
  analytics, notificações, tickets de suporte, e suporte ao admin.
- **Adapters trocáveis:**
  - **E-mail (OTP):** `app/core/email.py` — adapters `mock` | `zeptomail` | `smtp`, escolhidos por
    `EMAIL_PROVIDER`. **ZeptoMail** (o produto transacional da Zoho) é o provedor de produção;
    SMTP (`smtp.zoho.com:587`) é o fallback. Detalhes na **§6**.
  - **Gateway de pagamento:** `app/domains/payments/gateways/` — adapter `mock` (confirmação via
    `POST /payments/mock/confirm/{id}`, só ativo quando `PAYMENT_PROVIDER=mock`) e **`mercadopago`
    implementado** (Checkout Pro, webhook com assinatura HMAC) — falta só credencial real
    (`MP_ACCESS_TOKEN`/`MP_WEBHOOK_SECRET`) para ativar em produção. Asaas/Pagar.me/Stripe plugam
    pela mesma interface (`PaymentGateway` Protocol em `gateways/base.py`).
  - **Nota fiscal:** `app/domains/payments/invoicing.py` — adapter `NoopInvoiceProvider` (marca
    `invoice_status="pending"`, não emite nada); trocar por NFE.io/Focus NFe é troca de classe, sem
    mexer no fluxo de pagamento. Emissão roda automática (best-effort) para toda venda paga; desde
    2026-07-13 a **exibição ao cliente é sob demanda** — coluna `invoice_requested_at` + rota
    `POST /payments/orders/{id}/request-invoice` + botão na Carteira (ver
    `DOCUMENTACAO_CENTRAL.md` §12.8).
- **Env vars novas (defaults de dev):** `APP_ENV`, `JWT_SECRET` (obrigatório em produção),
  `EMAIL_PROVIDER` + credenciais (§6), `PAYMENT_PROVIDER` + `MP_ACCESS_TOKEN`/`MP_PUBLIC_KEY`/
  `MP_WEBHOOK_SECRET`/`MP_WEBHOOK_URL`/`FRONTEND_BASE_URL`, TTLs de token/OTP,
  `CRON_TOKEN` (protege liquidação).
- **Validação de configuração no boot:** `app/core/startup.py::validate_startup_config()`, chamado
  no import de `app.main`. Com `APP_ENV=production` o processo **se recusa a subir** se a
  configuração quebraria o cadastro (§6.3). Em `development`, apenas avisos.
- **Liquidação de apostas:** worker `backend/scripts/settle_bets.py` (ou `POST /api/cron/settle-bets`)
  agendável — pós-jogo, consulta a API-Football, consome/estorna o crédito reservado.
- **Frontend:** rotas novas `/entrar`, `/cadastro`, `/carteira` (redesenhada — banner, selos de
  pacote, cupom, PIX pendente, minhas compras), `/perfil`, `/admin` (10 abas), `/afiliado`
  (portal), `/documentos/[type]`, `/como-funciona`; auth via `lib/AuthContext.tsx` +
  `lib/authApi.ts` (JWT no localStorage + refresh automático). Atribuição de afiliado capturada em
  qualquer página via `?ref=código` (`components/platform/ReferralCapture.tsx`).
  `NEXT_PUBLIC_API_URL` deve apontar para o backend.

Detalhes completos (domínios, fluxos, promoção, admin) em `docs/ARQUITETURA_MONETIZACAO.md` e
`DOCUMENTACAO_CENTRAL.md` §12 (§12.7 = monetização de conversão, 2026-07-11).

## 6. E-mail transacional (Zoho / ZeptoMail)

Introduzido em 2026-07-08. O cadastro depende de entregar um código OTP por e-mail: sem envio
real, não existe usuário ativo. Toda a integração vive atrás de um único `Protocol`.

### 6.1 Adapters (`app/core/email.py`)
`EmailSender` expõe só `send(to, subject, body)`. Três implementações:

| `EMAIL_PROVIDER` | Classe | Uso |
|---|---|---|
| `mock` | `MockEmailSender` | dev — imprime o OTP no console, **não entrega nada** |
| `zeptomail` | `ZeptoMailSender` | **produção** — `POST {base}/v1.1/email`, header `Authorization: Zoho-enczapikey <token>` |
| `smtp` | `SmtpEmailSender` | fallback — `smtp.zoho.com:587` STARTTLS (ou `:465` com `SMTP_STARTTLS=false`) |

**Por que ZeptoMail e não a caixa do Zoho Mail:** a caixa é para correio humano e tem limite
diário de envio; disparar OTP por ela leva a throttling e a reputação de spam. ZeptoMail é o
produto transacional, com token dedicado e log de entrega por mensagem.

Regras que valem a pena preservar numa refatoração:
- Um `EMAIL_PROVIDER` desconhecido, ou credencial faltando, levanta `EmailSendError` — **não**
  cai silenciosamente em `mock`. O comportamento antigo (fallback para mock) fazia o
  `POST /auth/register` responder `201 "Enviamos um código"` com o OTP indo parar no log do
  servidor, sem nada acusar erro.
- O token é aceito com ou sem o prefixo `Zoho-enczapikey ` (o painel da Zoho o exibe das duas formas).
- O log de erro nunca inclui o corpo da mensagem, porque o corpo contém o código OTP.

### 6.2 Falha de envio aborta o cadastro (proposital)
`send_otp_email` é chamado em `auth/service.py::_create_and_send_otp`, **entre** o
`db.add(OtpCode(...))` e o `db.commit()` do chamador. Como `get_session()` não commita sozinho,
levantar ali descarta o OTP *e* o usuário. `EmailSendError` é convertido em `HTTPException 502`
(não exceção crua: um 500 não carrega header CORS e o browser mascara o erro real como falha
de CORS).

Consequência desejada: sem estado órfão e sem travar o cooldown de reenvio de 60 s com um código
que nunca chegou — o usuário tenta de novo imediatamente.
**Trade-off aceito:** se o ZeptoMail cair, ninguém se cadastra até voltar. Desacoplar exigiria
enfileirar o envio num worker.

### 6.3 Validação no boot (`app/core/startup.py`)
Chamada no import de `app.main`. Com `APP_ENV=production`, levanta `ConfigError` (derrubando o
processo) se qualquer uma destas for verdadeira — listando **todas** de uma vez:
- `EMAIL_PROVIDER=mock` (nenhum e-mail entregue);
- credencial do provedor escolhido ausente (`ZEPTOMAIL_TOKEN`, ou `SMTP_HOST/USER/PASSWORD`);
- `EMAIL_FROM` ainda no placeholder `no-reply@apostai.local`;
- `JWT_SECRET` ainda no default de desenvolvimento.

Em `development` isso vira apenas `logger.warning`. Quando a config está OK, o boot imprime
`[config] OK — app_env=… email_provider=… remetente=…` **em stdout** (`print`, não `logger.info`:
sem handler configurado o root logger descarta INFO, e essa é justamente a linha que se procura
no log do Render após um deploy).

### 6.4 Configuração é lida do `.env` pelo próprio `config.py`
`app/core/config.py` declara `env_file=backend/.env` no `SettingsConfigDict`. Antes ele dependia
de `app.db.connection._load_local_dotenv()`, mas **`app.core.config` é importado antes de
`app.db.connection`** na cadeia de imports do `app.main` — o `.env` era lido tarde demais e
silenciosamente ignorado para *todas* as settings (inclusive `JWT_SECRET` e `EMAIL_PROVIDER`).
Variáveis de ambiente reais continuam com precedência sobre o `.env`.

### 6.5 Env vars
```env
APP_ENV=production                       # "development" local; production torna a validação fatal
JWT_SECRET=<openssl rand -hex 32>
EMAIL_PROVIDER=zeptomail                 # mock | zeptomail | smtp
EMAIL_FROM=no-reply@seudominio.com       # precisa ser de domínio verificado na Zoho
EMAIL_FROM_NAME=ApostAI
ZEPTOMAIL_TOKEN=<Send Mail Token>        # painel > Mail Agents > seu agente
ZEPTOMAIL_BASE_URL=https://api.zeptomail.com   # conta na UE: https://api.zeptomail.eu
# fallback SMTP (Zoho Mail — exige SENHA DE APLICATIVO, não a senha da conta)
SMTP_HOST=smtp.zoho.com
SMTP_PORT=587
SMTP_USER=contato@seudominio.com
SMTP_PASSWORD=
SMTP_STARTTLS=true
```
Pré-requisito no lado da Zoho: **domínio verificado + SPF e DKIM publicados no DNS**. Sem isso a
entrega é recusada ou cai em spam.

### 6.6 Scripts de verificação
```bash
cd backend
python -m scripts.send_test_email voce@dominio.com   # usa o MESMO adapter do cadastro; exit≠0 em falha
python -m scripts.verify_signup_flow                 # cadastro ponta a ponta, SQLite + ZeptoMail falso
```
`verify_signup_flow` não precisa de rede, banco nem token: sobe um servidor HTTP local que finge
ser o ZeptoMail, lê o OTP do corpo capturado, e percorre
`register → verify-email → set-password → login → /auth/me`. Cobre também o 502-com-rollback e o
retry imediato após o provedor voltar.

### 6.7 Recebimento de e-mail — ainda não implementado
Uma caixa `contato@seudominio.com` no Zoho Mail é **configuração, não código**. Fazer o *sistema*
ler a caixa (abrir ticket a partir de uma resposta, por exemplo) exigiria IMAP ou a Zoho Mail API
com OAuth2 + refresh token — trabalho separado, ainda sem decisão.

---

## 7. Ambiente de pesquisa/desenvolvimento reproduzível (qualquer máquina)

Checklist para um agente (ou pessoa) partindo do zero numa máquina nova conseguir rodar o
predictor de produção **e** os experimentos de pesquisa (`backend/research_clubs/`,
`backend/scripts/clubs_*.py`, `backend/scripts/*.py` de validação). Ordem: clonar → venv →
segredos → dados.

### 7.1 Python / venv
- **Python 3.12** (testado com 3.12.0). Venv **não é portável entre máquinas** — o
  `pyvenv.cfg` guarda o path absoluto de origem; se copiar a pasta `.venv` de outra máquina,
  repare com `py -3.12 -m venv .venv` no destino (preserva `site-packages`, só corrige o
  `pyvenv.cfg`) em vez de recriar do zero.
- Instalar: `cd backend && pip install -r requirements.txt`. O arquivo tem duas seções:
  1. **Produção** (`app/`, `predictor.py`) — sempre necessária.
  2. **Pesquisa de modelos** (`research_clubs/`, `scripts/clubs_*.py`) — CatBoost, LightGBM,
     XGBoost, `tabulate`. **Não** inclui `torch`: o índice CPU-only do PyTorch é específico de
     plataforma (`--index-url https://download.pytorch.org/whl/cpu`), então instale à parte
     só se for rodar `scripts/clubs_deep_tabular.py`:
     `pip install torch --index-url https://download.pytorch.org/whl/cpu` (Linux/Mac: omitir o
     índice para pegar a build certa da plataforma, ou usar o mesmo se não houver GPU).
- Verificar instalação: `python -c "import catboost, lightgbm, xgboost, torch"` (torch é opcional).

### 7.2 Segredos (`backend/.env`, nunca commitado)
Copiar de `backend/.env.example` e preencher:
- `DATABASE_URL` — string de conexão do Neon (Postgres serverless). Sem ela, **nenhum** dado de
  produção nem os datasets de treino ficam acessíveis (tudo lê do Neon ou dos espelhos locais
  derivados dele).
- `APIFOOTBALL_KEY` (e/ou `API_FOOTBALL_KEY`, ambos aceitos) — chave da API-Football. Só é
  necessária para **coleta** (`scripts/prefetch_*.py`, `scripts/mirror_club_cache.py`,
  `scripts/collect_*.py`) e para checar cota (`GET /status`). Treino/validação/promoção com dados
  já coletados **não precisam dela**.
  - **Checar cota em tempo real** (1 chamada, barata): `python -c "from app.services.fixture_fetch
    import _get; print(_get('/status'))"` — retorna `requests.current`/`limit_day` e a data de
    expiração da assinatura (`subscription.end`). **Sempre conferir isso antes de planejar uma
    coleta grande** — a cota reseta diariamente e a assinatura tem prazo (verificado expirando em
    2026-07-19 nesta sessão; pode ter mudado, checar de novo).

### 7.3 Dados — o que é versionado vs. o que precisa ser (re)gerado
`backend/data/` inteiro é **gitignored**. Numa máquina nova, nada em `data/` existe. Ordem de
regeneração (cada passo é resumível/idempotente — pode interromper e retomar):

| Artefato | Como gerar | Custo |
|---|---|---|
| `data/raw_cache.sqlite` (seleções) | espelho, ver `app/services/raw_cache.py::mirror_from_neon()` | leitura única do Neon (~44 MB) |
| `data/club_raw_cache.sqlite` (clubes, **1,5 GB**) | `scripts/mirror_club_cache.py --max 60000 --margin 1000 --workers 6 --rps 6` | ~2,5h a 360 req/min, consome cota da API (não do Neon — desenhado assim de propósito, ver §3.1) |
| `data/built/club_*.parquet` (fixtures/matches/lineups/features) | `scripts/build_clubs_lineups.py` depois `scripts/build_clubs_dataset.py` | minutos, CPU-only, lê só do espelho local acima |
| `international_features_enriched_apifootball.csv` (seleções) | `build_final_dataset.py` | minutos, lê cache local + martj42 (auto-baixado) |
| `model_artifacts/*.joblib` (produção) | já estão no repo (não gitignored) — não precisa retreinar p/ rodar o predictor | — |

**Se só quer rodar o predictor de produção:** só precisa de `model_artifacts/` (já no repo) +
`DATABASE_URL`. **Se quer rodar/estender a pesquisa de clubes:** precisa do espelho local de
clubes — ou copiar `data/club_raw_cache.sqlite` de uma máquina que já o tem (mais rápido), ou
rodar `mirror_club_cache.py` do zero (mais lento, gasta cota).

### 7.4 Rodando experimentos longos em background (Windows)
Os scripts de pesquisa (`scripts/clubs_*.py`) são desenhados para rodar por horas — **sempre
resumíveis por CSV incremental** (verificam o que já está salvo em `data/reports/` e pulam).
Padrão usado nesta sessão: `Start-Process` do PowerShell com `-WindowStyle Hidden` e saída
redirecionada, para o processo sobreviver ao fim da sessão do agente:
```powershell
Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "scripts\NOME.py" `
  -WorkingDirectory "<repo>\backend" -RedirectStandardOutput "data\state\NOME.log" `
  -RedirectStandardError "data\state\NOME.err.log" -WindowStyle Hidden -PassThru
```
**Cuidado com reboot:** um reinício da máquina (Windows Update, política automática) mata todos
os processos em background sem aviso. Depois de um reboot, **o Windows recicla PIDs** — um PID
"vivo" pode ser um processo completamente diferente. Antes de assumir que um job continua rodando,
confirme a identidade: `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>"` (campo
`CommandLine`) e compare `CreationDate` com `(Get-CimInstance Win32_OperatingSystem)
.LastBootUpTime`. Se o reboot aconteceu depois do lançamento do job, relance-o — os scripts
resumíveis retomam do checkpoint sem perder trabalho.

### 7.5 Coleta diária automática (Windows Task Scheduler, `\PrevisaoJogos\`)
Ver `ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` para o estado corrente de cada tarefa. Resumo: 4 tarefas
(`PrefetchWorldCup` 06:30, `CollectResolved` 05:00, `CollectPlayerForm` 00:01, `CollectOdds` a
cada ~3h) rodando os `.cmd` em `backend/scripts/*.cmd`, cada um chamando o `.venv\Scripts\python.exe`
local. Numa máquina nova, recriar as tarefas aponta os `.cmd` para o novo path do repo (os `.cmd`
resolvem o próprio diretório via `%~dp0`, então só o Task Scheduler precisa ser reconfigurado, não
os scripts).
