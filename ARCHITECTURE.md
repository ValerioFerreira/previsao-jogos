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

**Consequência conhecida (em aberto):** os dados de jogo vivem hoje numa **máquina local**, e o
cache apontado por `fixture_index` é efêmero em hosts serverless (no Render o disco some a cada
redeploy, fazendo o sistema reconsumir cota da API-Football). Mover esse acervo para
armazenamento durável na nuvem é um trabalho planejado, **ainda não iniciado** — e o destino
natural é object storage, não uma tabela de banco. Antes de mover qualquer coisa "para economizar
Neon", medir de verdade:
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
  bets,promotions,admin}` — cada um com `models.py`/`schemas.py`/`service.py`/`router.py`.
  Config central em `backend/app/core/config.py` (pydantic-settings). Segurança em
  `app/core/security.py` (argon2 + JWT + OTP), validação CPF/telefone em `app/core/validators.py`.
- **23 tabelas `app_*`** no Neon (já criadas em produção): usuários/OTP/sessões/auditoria,
  carteira + **ledger** de créditos (saldo só via lançamento, idempotência), pagamentos, análises
  com snapshot imutável, apostas + liquidação, promoções e suporte ao admin.
- **Adapters trocáveis:**
  - **E-mail (OTP):** `app/core/email.py` — adapters `mock` | `zeptomail` | `smtp`, escolhidos por
    `EMAIL_PROVIDER`. **ZeptoMail** (o produto transacional da Zoho) é o provedor de produção;
    SMTP (`smtp.zoho.com:587`) é o fallback. Detalhes na **§6**.
  - **Gateway de pagamento:** `app/domains/payments/gateways/` — adapter `mock` (confirmação via
    `POST /payments/mock/confirm/{id}`). Asaas/MercadoPago/Pagar.me/Stripe plugam via `PAYMENT_PROVIDER`.
- **Env vars novas (defaults de dev):** `APP_ENV`, `JWT_SECRET` (obrigatório em produção),
  `EMAIL_PROVIDER` + credenciais (§6), `PAYMENT_PROVIDER`, TTLs de token/OTP,
  `CRON_TOKEN` (protege liquidação).
- **Validação de configuração no boot:** `app/core/startup.py::validate_startup_config()`, chamado
  no import de `app.main`. Com `APP_ENV=production` o processo **se recusa a subir** se a
  configuração quebraria o cadastro (§6.3). Em `development`, apenas avisos.
- **Liquidação de apostas:** worker `backend/scripts/settle_bets.py` (ou `POST /api/cron/settle-bets`)
  agendável — pós-jogo, consulta a API-Football, consome/estorna o crédito reservado.
- **Frontend:** rotas novas `/entrar`, `/cadastro`, `/carteira`, `/perfil`, `/admin`,
  `/documentos/[type]`, `/como-funciona`; auth via `lib/AuthContext.tsx` + `lib/authApi.ts`
  (JWT no localStorage + refresh automático). `NEXT_PUBLIC_API_URL` deve apontar para o backend.

Detalhes completos (domínios, fluxos, promoção, admin) em `docs/ARQUITETURA_MONETIZACAO.md` e
`DOCUMENTACAO_CENTRAL.md`.

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
