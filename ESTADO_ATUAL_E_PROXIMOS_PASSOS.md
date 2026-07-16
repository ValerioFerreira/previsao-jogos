# Estado atual e próximos passos (handoff)

> **Leia isto primeiro** (o índice de caminhos é o **`CLAUDE.md`** na raiz). Resume onde o projeto
> está e o que fazer a seguir. Última atualização: **2026-07-16**.
> Docs de apoio: `CLAUDE.md` (índice), `DOCUMENTACAO_CENTRAL.md` (doc-mestre; **§9 = testes já feitos,
> não repetir**, **§12 = monetização**), `ARCHITECTURE.md` (infra — **§3.1 Neon, §5 monetização, §6
> e-mail**), `docs/ARQUITETURA_MONETIZACAO.md`.

---

## 0. Sessão (2026-07-16) — código para Mercado Pago real + nota fiscal automática (NFE.io)

**O que foi feito:** implementado (ainda não commitado/deployado — ver "pendências" abaixo) o
código que falta para os dois últimos itens do checklist §2.1: ativar Mercado Pago de verdade e
emitir NFS-e automática via **NFE.io** (decisão do dono; dados fiscais já prontos).

- **Mercado Pago:** o adapter (`gateways/mercadopago.py`) já estava pronto de sessões anteriores.
  Único código novo: `backend/app/core/startup.py::_payment_problems()` — mesmo padrão de guarda
  fatal do e-mail, agora também para pagamento (derruba o boot em produção se
  `PAYMENT_PROVIDER=mercadopago` e faltar `MP_ACCESS_TOKEN`/`MP_PUBLIC_KEY`/`MP_WEBHOOK_SECRET`).
- **Nota fiscal (NFE.io), do zero:** `InvoiceProvider` (`invoicing.py`) expandido com
  `check_status()` (a emissão da NFE.io é **assíncrona** — POST devolve `pending` com um id, o
  status final só vem depois); novo adapter `invoicing_nfeio.py`; `get_invoice_provider()` agora
  ramifica por `INVOICE_PROVIDER` (`nfeio` | `noop`, mesmo formato do `get_gateway()`); migração
  `f7c1b2e9d4a3` adiciona `invoice_provider_id`/`invoice_number` em `app_payment_orders`
  (`down_revision=e1f2a3b4c5d6`, head único conferido à mão — `alembic` não está instalado neste
  ambiente); `request_invoice()` agora reconsulta em vez de reemitir quando já existe
  `invoice_provider_id` (evita nota duplicada); novo polling (`scripts/invoice_poll.py` +
  `POST /api/cron/poll-invoices`, mesmo formato do `settle_bets.py`) porque a emissão é assíncrona.
  Guarda de boot equivalente (`_invoice_problems()`): fatal em produção se `INVOICE_PROVIDER=nfeio`
  e faltar token/dados fiscais; **`noop` em produção só avisa, não derruba** (diferente de
  e-mail/pagamento — não emitir nota real não bloqueia o lançamento).
- **Testado ponta a ponta sem gastar dinheiro real nem emitir nota real:**
  `scripts/verify_startup_config.py` (7 cenários da validação de boot) e
  `scripts/verify_invoice_flow.py` (checkout mock → paga → nota `pending` → poll → `issued`,
  mais o caminho de erro do provedor e o não-duplicar do `request_invoice()`) — os dois passam
  100%. `verify_signup_flow.py` rodado de novo como regressão (também passa).
- **Exato JSON da NFE.io não confirmado contra o Swagger real** (`invoicing_nfeio.py` foi escrito
  a partir da documentação pública, não de uma chamada real) — nomes de campo
  (`cityServiceCode`, `federalTaxNumber`, enums de status) podem precisar de ajuste fino na
  primeira chamada real; isso não muda o resto do desenho (Protocol/factory/migration/config já
  são independentes desse detalhe).
- **Dependências instaladas** em `api/.venv` (fastapi/sqlalchemy/httpx já existiam parcialmente;
  faltavam `sqlalchemy`, `alembic`, `argon2-cffi`, `PyJWT`, `pydantic-settings`,
  `email-validator`, `psycopg2-binary` — instalados para rodar os scripts de verificação).

**Pendências (fora de escopo de código, do dono):**
1. Runbook Mercado Pago: credenciais de produção no Render + configurar webhook no painel MP
   (passo a passo em `DOCUMENTACAO_CENTRAL.md` §12.9 / commit desta sessão).
2. Runbook NFE.io: cadastrar empresa + subir certificado A1 no painel NFE.io (só dá pra fazer lá,
   não por API), copiar Company ID/API Key, setar env vars no Render, configurar o cron de
   `poll-invoices`.
3. `alembic upgrade head` em produção ainda não rodou para NENHUMA migração pendente desde a
   sessão anterior (inclui agora também a `f7c1b2e9d4a3`) — depende do dono.
4. Ainda não commitado/pushado — revisar o diff antes.

---

## −1. Sessão (2026-07-14) — coleta de clubes travava havia 1 semana (causa raiz + fix)

**Sintoma:** desde 07/07, o cron diário (`prefetch_wc.cmd`) nunca chegava nas etapas de
rebuild/precompute/`prefetch_clubs.py` — só a etapa de seleções rodava. `club_match_detail_cache`
não recebia registro novo há dias, mesmo sobrando ~70k requisições ociosas/dia.

**Causa raiz:** `app/db/connection.py` criava o engine do Neon sem `connect_timeout`/
`statement_timeout`. Quando o pooler do Neon derruba a conexão silenciosamente (comum, aparece
em todo log diário como `psycopg2.OperationalError: server closed the connection unexpectedly`),
o psycopg2 não tem timeout por padrão — o processo trava indefinidamente no `connect()`/query
seguinte em vez de levantar exceção (que o código já trata com try/except). Como `cache_get()` é
chamado por fixture (milhares de vezes por execução), bastava UMA queda de conexão no momento
errado para travar o job inteiro sem nenhum log adicional.

**Fix:**
1. `connect_args={"connect_timeout": 10, "options": "-c statement_timeout=20000"}` no engine
   (`app/db/connection.py`) — trava no máximo ~20s e levanta exceção, que já é tratada.
2. `prefetch_wc.cmd` reordenado: **clubes primeiro**, seleções depois. Seleções já saturou
   (~24,3k jogos, só entram dezenas novas/dia de jogos reais) e sempre para sozinha via
   "FIM (tudo coberto)" bem antes do limite diário — rodar depois não tira cota de ninguém.
   Clubes (prioridade atual, backlog grande em Brasil→Europa) passa a pegar a fatia grande da
   cota diária primeiro.

**Status da coleta de clubes ao investigar (ver commit):** só uma rodada MANUAL na noite de
10/07→11/07 avançou algo — cobriu Brasileirão A, Brasileirão B, Copa do Brasil, Premier League e
La Liga por completo (2015-2026), começou Serie A (Itália) e parou no meio da temporada 2025 sem
log de conclusão (também travou). **Bundesliga e Ligue 1 (2 das 8 ligas-alvo) ainda não foram
tocadas.** Nada avançou via cron automático desde 07/07.

**Próxima validação:** conferir `data/state/prefetch_wc.log` no dia seguinte — deve aparecer
`----- prefetch Clubes -----` seguido de `>> Clubs: N novos ...` e, depois, `----- prefetch
Selecoes -----`, `----- rebuild scorer model -----` etc., todos na mesma execução (sem gap de
dias). Se ainda travar, o próximo suspeito é o Task Scheduler matando a instância anterior antes
dela terminar (verificar config "Do not start a new instance" / limite de duração da tarefa).

---

## −1. Sessão (2026-07-13) — merge da `monetization` na `main` + nota fiscal sob demanda

- **Merge da branch `monetization` → `main`, com push.** A branch estava exatamente 3 commits à
  frente da `main` (mesmo merge-base) — fast-forward puro, sem conflitos. Os commits `13a6954`
  (throttle de coleta), `aacc67f` (monetização completa) e `42c4175` (docs) agora estão em
  `origin/main`. **Deploy no Render/Vercel e `alembic upgrade head` em produção ainda não foram
  confirmados** — depende do dono rodar/checar (ver §2).
- **Nota fiscal sob demanda:** a emissão automática continua rodando (best-effort, via
  `NoopInvoiceProvider`) para **toda** venda paga — mantém a declaração fiscal íntegra mesmo que o
  cliente nunca peça. O que mudou é a **exposição ao cliente**: nova coluna
  `invoice_requested_at`, endpoint `POST /payments/orders/{id}/request-invoice` e botão "Solicitar
  nota fiscal" na Carteira — o link/aviso só aparece depois que o cliente pede. Detalhes em
  `DOCUMENTACAO_CENTRAL.md` §12.8. Migração `b4d6e1f8a9c2` **ainda não aplicada em produção**.
- **Conta admin:** tentativa de promover `valerioeducfin@gmail.com` a admin **não pôde ser
  executada** neste ambiente — não há `backend/.env`/credencial do Neon disponível aqui. Comando
  repassado ao dono: `cd backend && python scripts/make_admin.py valerioeducfin@gmail.com`
  (a conta precisa já existir/estar ativa).
- **Contador:** texto preparado e enviado nesta sessão cobrindo CNAE (6319-4/00 vs 6203-1/00 +
  6311-9/00), Fator R com pró-labore de sócio único (sem CLT), e a obrigatoriedade de emitir NFS-e
  por venda independente do cliente pedir cópia. **Resposta do contador ainda pendente** — decide
  o CNAE final, o emissor (NFE.io vs Focus NFe) e se a emissão pode mesmo ser condicionada ao
  pedido do cliente ou só a exibição.

---

## −2. Sessão (2026-07-11) — Monetização completa (7 fases), branch `monetization` (já mergeada — ver §−1)

Implementadas as 7 fases do plano de monetização de conversão, todas testadas ponta a ponta contra
o Neon real (não é código não-testado). Branch **`monetization`** (a partir da `main`), commits
`13a6954` (throttle de coleta, pendência da sessão anterior) e `aacc67f` (monetização). Detalhes
completos em `DOCUMENTACAO_CENTRAL.md` §12.7.

- **Gateway Mercado Pago real** (Checkout Pro) substitui o `MockGateway` — `PAYMENT_PROVIDER=
  mercadopago` ativa; webhook valida assinatura HMAC (`x-signature`); `mockConfirm` só roda com
  `PAYMENT_PROVIDER=mock`. **Ainda sem credenciais reais** — ver checklist no §2 abaixo.
- **Cupons** tipados (percentual/fixo/créditos bônus), validados no checkout, resgatados só no
  pagamento confirmado. **Carteira redesenhada**: banner promocional, pacotes com selos ("mais
  vendido"/"melhor oferta"/"oferta limitada") e % de economia, campo de cupom, pacote recomendado
  (heurística de consumo), recuperação de PIX pendente, "Minhas compras".
- **Afiliados/influenciadores**: domínio novo (`app/domains/affiliates/`) com portal próprio
  (`/afiliado`), atribuição por link (`?ref=código`, janela de dias configurável) **independente**
  de cupom, comissão calculada no pagamento confirmado.
- **Campanhas** (`app/domains/campaigns/`): entidade guarda-chuva (banner+pacotes+cupons+afiliados+
  prioridade) + scaffold de A/B testing (`assign_variant()` determinístico por hash de usuário).
- **Analytics** (`app/domains/analytics/`): eventos de funil (signup/checkout/compra/etc.) +
  `GET /admin/analytics/dashboard` (faturamento, ticket médio, conversão, créditos vendidos/usados).
- **Notificações** (`app/domains/notifications/`) e **suporte** (`app/domains/support/`): domínios
  novos, mínimos — notificação `payment_approved` disparada automaticamente; tickets com CRUD admin.
- **Nota fiscal:** hook `NoopInvoiceProvider` (`app/domains/payments/invoicing.py`) roda após todo
  pagamento confirmado, pronto para trocar por emissor real (NFE.io/Focus NFe/Asaas).
- **Painel admin** ganhou 6 abas novas: Dashboard, Cupons, Pacotes, Afiliados, Banners,
  Configurações — além das 4 que já existiam.
- 4 migrations Alembic novas aplicadas no Neon (13 tabelas `app_*` novas: cupons ganharam campos
  tipados; pacotes ganharam selo/ordem; pedidos ganharam cupom/afiliação/nota fiscal; +
  `app_events`, `app_affiliates`, `app_affiliate_attributions`, `app_affiliate_commissions`,
  `app_campaigns` e associações, `app_experiments`, `app_experiment_variants`,
  `app_notifications`, `app_support_tickets`).
- **Efeito colateral corrigido:** `backend/app/services/fixture_fetch.py` tinha um `import time`
  órfão de uma tentativa de throttle já revertida (sessão anterior) — removido.

---

## −3. Sessão anterior (2026-07-09) — props de finalizações, cópula, Série A

Detalhes em `DOCUMENTACAO_CENTRAL.md` §12.6. Tudo na `main`.

- **Mercado "Jogador a finalizar" PROMOVIDO** (AUC 0,773, ECE 1,06%, 4/4): card **"Jogador"**
  agora com **MARCAR | FINALIZAR (0,5/1,5/2,5)**. Modelo rebuildado no cron.
- **Cópula gaussiana na odd combinada PROMOVIDA** (EXP7/13/14): combos ofensivos correlacionados
  têm odd combinada mais justa/menor. `bets/markets.py::combined_odd`.
- **Card H2H** enriquecido (barra de vitórias, chips, médias) e **equipes lado a lado** no bloco.
- **Cartão de jogador / Fator Árbitro nos cartões: REPROVADOS** (idiossincráticos). Fechados.
- **Coleta de seleções SATUROU** (~70k/75k ociosa/dia; auditoria da API confirma que só resta
  o re-teste de escalação, sem API nova; xG é muro de dados a 5,3%) → **começou a coleta de
  CLUBES** em tabela separada `club_match_detail_cache` (`scripts/prefetch_clubs.py`, no cron),
  prioridade **Brasil→Europa** (Série A/B, Copa do Brasil, depois Premier/La Liga/Serie A/
  Bundesliga/Ligue 1). Meta: exaurir a cota/dia com propósito.
- **Otimização de Network Transfer do Neon (2026-07-10):** um pico de 5,58 GB de egress vinha de
  escanear o `match_detail_cache` (44 MB) repetidamente. Corrigido: **agregados precomputados**
  (referee/minutagem/quadrantes em tabelas pequenas), **espelho local do bruto** (SQLite; rebuilds
  e precompute leem local, zero Neon), **column pruning + LIMIT** e **cache TTL no front**.
  Estimativa: ~5,58 GB → < 0,5 GB/mês. Detalhes em `ARCHITECTURE.md` §3.1. **Rodar o
  `precompute_aggregates.py` sempre após o rebuild** (já no cron `prefetch_wc.cmd`).
- **Próxima grande frente: modelar os CLUBES** quando o cache encher (dataset/Elo por liga,
  Dixon-Coles + contagens sob o gate §6; props ofensivos devem transferir). Ver §5.

---

## 0. Última sessão (2026-07-08, parte 2) — UX da Análise + regras de crédito/aposta

Produção agora em **`apostainfo.com.br`** (Vercel); cadastro por e-mail (ZeptoMail) funcional.
Detalhes em `DOCUMENTACAO_CENTRAL.md` §12.5. Resumo do que entrou na `main`:

- **8 créditos grátis** em toda conta nova (bônus idempotente na ativação).
- **Análise persiste em reload** (localStorage no `PredictionContext`) — corrige o bug de a
  análise sumir e forçar gasto de outro crédito.
- **Apostas: seleções interdependentes bloqueadas** (um por mercado-base — ex.: não combina
  Menos de 1,5 com Menos de 2,5 gols) no backend + BetBuilder.
- **Redesign da página de Análise:** mercados secundários com colapso individual; "Jogador a
  Marcar" dentro dos secundários; cards com só o nome da seleção centralizado; Handicaps com
  texto+cabeçalhos; Configuração do Confronto recolhível com cabeçalho flutuante "Alterar
  Equipes"; Funções Avançadas acima do Monte sua Aposta; últimos 5 jogos em linhas num bloco
  com o Resumo do Confronto Direto.
- **"Jogador a levar cartão": testado e REPROVADO** (AUC 0,62 vs goleador ~0,74; idiossincrático/
  árbitro). `scripts/test_player_cards.py`. Mercado não aberto.
- **Coleta contínua:** `PrefetchWorldCup` roda com `--all-nations` (preenche as ~185 seleções
  sem detalhe completo usando a cota ociosa de ~75k/dia). Mantê-la ligada.

---

## 1. O que foi feito nesta jornada (2026-07-08) — integração de e-mail com a Zoho

O objetivo era **destravar o cadastro no site**, que dependia de entregar o código OTP por e-mail.
Tudo está na `main`, commit **`e517740`**, já em `origin/main`.

### 1.1 Adapter de e-mail real (`backend/app/core/email.py`)
`EMAIL_PROVIDER` passa a aceitar `mock` | `zeptomail` | `smtp`.
- **ZeptoMail** (produto transacional da Zoho) é o provedor de produção — `POST /v1.1/email`,
  header `Authorization: Zoho-enczapikey <token>`, via `httpx` (já era dependência).
- **SMTP** é o fallback (`smtp.zoho.com:587` STARTTLS, ou `:465` com `SMTP_STARTTLS=false`).
  Exige **senha de aplicativo** do Zoho Mail, não a senha da conta.
- Escolhemos ZeptoMail e não a caixa do Zoho Mail porque caixa humana tem limite diário de envio;
  disparar OTP por ela leva a throttling e reputação de spam.

### 1.2 Três bugs encontrados e corrigidos (todos silenciosos)
1. **`get_email_sender()` devolvia `MockEmailSender` incondicionalmente.** `EMAIL_PROVIDER` era
   lido e descartado com um warning. Em produção isso significa `POST /auth/register` respondendo
   `201 "Enviamos um código"`, o OTP indo parar no log do servidor, e **nenhum usuário conseguindo
   concluir o cadastro — sem nada acusar erro**. Hoje um provider desconhecido ou credencial
   faltando levanta `EmailSendError`.
2. **`backend/.env` era silenciosamente ignorado.** `app.core.config` é importado **antes** de
   `app.db.connection` na cadeia do `app.main`, e era `connection._load_local_dotenv()` que lia o
   arquivo — tarde demais. Valia para *todas* as settings, inclusive `JWT_SECRET` e
   `EMAIL_PROVIDER`. Agora `config.py` declara `env_file=backend/.env` (env vars reais mantêm
   precedência). *Sintoma que isso causava: setar `EMAIL_PROVIDER=zeptomail` no `.env`, rodar
   local, e receber mock — culpando o adapter.*
3. **Nada validava a configuração no boot.** Ver 1.4.

### 1.3 Falha de envio aborta o cadastro — de propósito
`send_otp_email` roda em `auth/service.py::_create_and_send_otp`, **entre** o `db.add(OtpCode(...))`
e o `db.commit()` do chamador. `EmailSendError` vira `HTTPException 502`; como `get_session()` não
commita sozinho, a sessão fecha sem persistir **nem o OTP nem o usuário**.

Por que assim: engolir o erro persistiria o OTP e travaria o cooldown de reenvio de 60 s com um
código que nunca chegou. E é `HTTPException`, não exceção crua, porque um 500 não carrega header
CORS e o browser mascara o erro real como falha de CORS (o codebase já alertava para isso).

**Trade-off aceito e conhecido:** se o ZeptoMail cair, ninguém se cadastra até voltar. Desacoplar
exigiria enfileirar o envio num worker — não foi feito.

### 1.4 Validação de configuração no boot (`backend/app/core/startup.py`, novo)
Chamada no import de `app.main`. Nova env var **`APP_ENV`** (`development` | `production`).
Com `APP_ENV=production`, o processo **recusa subir** (`ConfigError`, listando todos os problemas
de uma vez) se: `EMAIL_PROVIDER=mock`; credencial do provedor ausente; `EMAIL_FROM` ainda no
placeholder `no-reply@apostai.local`; ou `JWT_SECRET` ainda no default de dev.
Em `development` isso vira apenas `logger.warning` — o mock segue sendo o fluxo local normal.

Boot bem-sucedido imprime em **stdout**: `[config] OK — app_env=… email_provider=… remetente=…`
(é `print`, não `logger.info`: sem handler configurado o root logger descarta INFO — é essa a
linha a procurar no log do Render depois de um deploy).

`settings.is_production` mudou de significado: era `jwt_secret != default`, agora é
`APP_ENV == "production"`. Não havia nenhum consumidor da versão antiga (verificado por grep).

### 1.5 Dois scripts novos (`backend/scripts/`)
```bash
cd backend
python -m scripts.send_test_email voce@dominio.com   # usa o MESMO adapter do cadastro; exit≠0 em falha
python -m scripts.verify_signup_flow                 # cadastro ponta a ponta; exit 0 = tudo passou
```
- `send_test_email.py` — valida a configuração da Zoho **antes** de um usuário real tentar se
  cadastrar. Imprime provider/remetente/token mascarado e, em falha, o checklist de causas.
- `verify_signup_flow.py` — sobe SQLite temporário + um servidor HTTP local que finge ser o
  ZeptoMail, lê o OTP do corpo capturado e percorre
  `register → verify-email → set-password → login → /auth/me`. Cobre também o 502-com-rollback e o
  retry imediato após o provedor voltar. **Não precisa de rede, banco nem token.**

### 1.6 O que foi verificado, e o que não foi
Verificado (todos passando): adapter (20 checks contra servidor HTTP local — endpoint, header,
payload, 401→erro tipado, host inacessível→erro tipado, STARTTLS vs SSL); validação de boot
(10 checks cobrindo dev/prod × cada problema); cadastro ponta a ponta (`verify_signup_flow`).

Durante o desenvolvimento, nada foi testado contra o ZeptoMail real (não havia token nem domínio
verificado no ambiente local) — toda a validação automatizada usa um servidor que imita o contrato
da API.

**Confirmado em produção (2026-07-08):** o dono configurou as env vars no Render e **fez um cadastro
real no site com sucesso** — o código OTP chegou por e-mail. O caminho ZeptoMail está funcionando
ponta a ponta.

## 2. Estado atual (produção)
- **Backend no ar:** `https://api-previsoes-jogos.onrender.com/health` → `200` (checado 2026-07-08).
- **Motor de previsão:** inalterado (Dixon-Coles NB / NB cascata / GP) + calibração O/U promovida.
- **Camada de monetização:** funcional ponta a ponta, validada ao vivo no Neon. **7 fases de
  conversão** (§−1) + **nota fiscal sob demanda** (§0) já **mergeadas e publicadas em
  `origin/main`** (2026-07-13). **Deploy no Render/Vercel e `alembic upgrade head` em produção
  ainda pendentes de confirmação do dono** — sem isso as tabelas/colunas novas não existem no
  banco de produção.
- **Cadastro: FUNCIONANDO em produção.** Env vars configuradas no Render; um cadastro real no site
  foi concluído com o código OTP chegando por e-mail (confirmado pelo dono em 2026-07-08).
  Logo, `EMAIL_PROVIDER=zeptomail` está setado e o domínio está verificado na Zoho.
- **Gateway de pagamento:** adapter Mercado Pago **implementado** (`backend/app/domains/payments/
  gateways/mercadopago.py`), mas continua rodando em **mock** em produção — faltam as credenciais
  reais (`MP_ACCESS_TOKEN`/`MP_WEBHOOK_SECRET`) e o merge/deploy da branch `monetization`.
- **Conta demo:** `demo.apostai@gmail.com` / `Demo1234` (admin, com créditos).

## 2.1 O que falta para a monetização vender de verdade (checklist)

Nada disto é código pendente — são decisões/credenciais que só o dono pode prover. A arquitetura
já está pronta para receber cada item sem refatoração (troca de adapter/credencial/conteúdo):

1. **Credenciais reais do Mercado Pago** — `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY`,
   `MP_WEBHOOK_SECRET` (sandbox primeiro, depois produção), e `PAYMENT_PROVIDER=mercadopago` no
   Render. Configurar a *notification URL* do MP apontando para
   `https://<backend>/payments/webhook/mercadopago`. Sem isso o gateway continua em mock.
2. ~~Merge da branch `monetization` na `main`~~ **feito (2026-07-13, §0)** — falta só o **deploy**
   no Render/Vercel e rodar `alembic upgrade head` em produção (inclui a migração
   `b4d6e1f8a9c2` da nota fiscal sob demanda).
3. **Textos jurídicos revisados por advogado** — Termos de Uso, Privacidade/LGPD, Política de
   Créditos, Regulamento de Promoção. Hoje são **templates** em `legal_documents`
   (`app/domains/legal/service.py`), com a marca `(Template inicial — substituir...)`. Publicar via
   `POST /admin/legal/publish` depois de prontos.
4. **Emissor de nota fiscal** — decidir com o contador (NFE.io vs Focus NFe) e trocar
   `NoopInvoiceProvider` por um adapter real em `app/domains/payments/invoicing.py` (mesmo padrão
   do gateway de pagamento — troca de adapter, sem mexer no fluxo). **A camada de opt-in do
   cliente já está pronta** (§0) — falta só o emissor de fato responder as chamadas.
5. **Regime tributário / CNPJ** — já existe CNPJ (confirmado com o dono), mas o enquadramento
   fiscal para emissão de NF sobre venda de créditos ainda não foi decidido com o contador.
6. **Popular dados reais no admin** — hoje os pacotes/cupons/banners/afiliados são os defaults de
   dev (`_DEFAULT_PACKAGES` em `payments/service.py`). Revisar preços/selos antes de anunciar.
7. **(Opcional, não bloqueia vendas)** Primeiro afiliado real cadastrado, primeira campanha
   configurada, primeiro teste A/B ligado (`app_experiments`) — a infraestrutura está pronta, falta
   só o conteúdo de negócio.

## 3. Pendência pequena, mas vale fechar
**Confirmar se `APP_ENV=production` está setado no Render.** O cadastro funcionar prova que o
ZeptoMail está configurado, mas **não** prova que a guarda de boot está armada: ela só é fatal com
`APP_ENV=production`. Sem essa env var, uma regressão futura de configuração (alguém remove o
`ZEPTOMAIL_TOKEN`, por exemplo) voltaria a subir em silêncio, com o OTP indo para o log.

No log de deploy do Render, procurar:
- `[config] OK — app_env=production email_provider=zeptomail …` → guarda armada, tudo certo.
- linhas `[config:dev] …` → `APP_ENV` **não** está em `production`; a validação está só avisando.

Para testar o envio sem criar usuário: `cd backend && python -m scripts.send_test_email <seu email>`
(mesmo caminho de código do cadastro; exit ≠ 0 em falha).

Pré-requisitos no lado da Zoho, para referência (não são código): domínio verificado, **SPF e DKIM
publicados no DNS**, Mail Agent criado, *Send Mail Token* copiado, e `EMAIL_FROM` pertencente ao
domínio verificado. Conta na UE ⇒ `ZEPTOMAIL_BASE_URL=https://api.zeptomail.eu`.

## 4. Como rodar / retomar
```bash
# Deps da camada de usuários (o .venv da raiz NÃO as tem — erro típico: ModuleNotFoundError:
# No module named 'pydantic_settings'):
pip install -r backend/requirements.txt

# Backend (Neon via backend/.env):
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Frontend (aponta para :8000 via frontend/.env.local = NEXT_PUBLIC_API_URL):
cd frontend && npm run dev          # http://localhost:3000
# Migrations da camada de app (idempotente):
cd backend && python -m alembic upgrade head
# Verificar o cadastro sem rede/banco/token:
cd backend && python -m scripts.verify_signup_flow
# Promover um usuário a admin / liquidar apostas:
cd backend && python scripts/make_admin.py email@dominio.com
cd backend && python scripts/settle_bets.py
```
Mapa do código: `backend/app/domains/{users,legal,wallet,payments,analysis,bets,promotions,admin,
affiliates,campaigns,analytics,notifications,support}` (`models/schemas/service/router` cada);
`backend/app/core/{config,email,startup,security,rate_limit}.py`;
`frontend/src/app/*` (páginas) + `frontend/src/lib/*` (`authApi`, `monetizationApi`, `adminApi`,
`AuthContext`, `PredictionContext`). O frontend já tem as 4 chamadas do cadastro em
`lib/authApi.ts` e o `raw()` propaga `body.detail` — a mensagem do 502 chega na tela.

## 5. Próximos passos (priorizados)

### E-mail (continuação direta desta jornada)
1. **Confirmar `APP_ENV=production` no Render** — ver §3. O envio já está confirmado; falta só
   garantir que a guarda de boot está armada contra regressões futuras.
2. **Recebimento de e-mail — decisão pendente.** Uma caixa `contato@seudominio.com` no Zoho Mail é
   **configuração, não código**. Fazer o *sistema* ler a caixa (abrir ticket a partir de uma
   resposta) exigiria IMAP ou a Zoho Mail API com OAuth2 + refresh token. **O dono ainda não disse
   qual dos dois quer.** Perguntar antes de construir.
3. **Corpo HTML nos e-mails** — hoje só `textbody`. O `Protocol EmailSender` teria de ganhar um
   parâmetro opcional; nenhum caller precisa mudar.

### Para ir a produção de verdade (monetização) — ver checklist completo em §2.1
4. ~~Gateway de pagamento real~~ **implementado e já na `main`** (Mercado Pago) — falta só
   credenciais reais + deploy/migração. Ver §2.1.1-2.
5. **Agendar a liquidação:** cron chamando `scripts/settle_bets.py` ou
   `POST /api/cron/settle-bets?token=$CRON_TOKEN` (a cada ~30 min). Definir `CRON_TOKEN`.
6. **Revisar textos legais** (Termos/Privacidade/LGPD/Créditos/Regulamento) — hoje são **templates**
   (`app/domains/legal/service.py`); publicar as versões reais via `POST /admin/legal/publish`.
   Ver §2.1.3.
7. **Nota fiscal + regime tributário** — ver §2.1.4-5.

### Dados de jogo na nuvem — planejado, NÃO iniciado
8. Os dados de jogo vivem hoje numa **máquina local**. O dono quer movê-los para a nuvem, mas
   **adiou explicitamente** esse trabalho. Antes de começar, ler `ARCHITECTURE.md` §3: a medição
   feita em 2026-07-08 mostra que `matches.parquet` tem **101 KB** e que o
   `historico_completo.json` de **205 MB nunca entrou no Neon** — o gargalo não é o que parece.
   O problema real é que o cache apontado por `fixture_index` é **efêmero no Render** (some a cada
   redeploy → o sistema reconsome cota da API-Football). Destino natural: **object storage**, não
   tabela de banco. **Não** mover o ledger (`app_credit_transactions`) para fora do Postgres: ele
   depende de transação multi-reg