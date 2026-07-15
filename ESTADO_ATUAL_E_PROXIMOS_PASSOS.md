# Estado atual e próximos passos (handoff)

> **Leia isto primeiro** (o índice de caminhos é o **`CLAUDE.md`** na raiz). Resume onde o projeto
> está e o que fazer a seguir. Última atualização: **2026-07-15**.
> Docs de apoio: `CLAUDE.md` (índice), `DOCUMENTACAO_CENTRAL.md` (doc-mestre; **§9 = testes já feitos,
> não repetir**, **§12 = monetização**, **§13 = pesquisa de clubes**), `ARCHITECTURE.md` (infra —
> **§3.1 Neon, §5 monetização, §6 e-mail, §7 ambiente de pesquisa reproduzível**),
> `docs/ARQUITETURA_MONETIZACAO.md`, `backend/docs/PESQUISA_CLUBES.md` (diário completo),
> `backend/docs/RELATORIO_FINAL_PESQUISA_CLUBES.md` (números consolidados).

---

## −1. Sessão (2026-07-15) — pesquisa de modelos para clubes (branch `clubs`, 9 fases) + expansão de coleta

**O que foi feito:** com a coleta de clubes saturada (54.072 jogos, 13 competições, 2010→2026),
executada a diretriz completa de pesquisa (ver [[diretriz]] no CLAUDE code / memória do agente):
duas linhas paralelas comparando a arquitetura ATUAL de produção (DC-NB) retreinada em clubes
(Linha A) contra uma pesquisa aberta sem viés das decisões históricas (Linha B — pi/Berrar/GAP
ratings, GBMs, Dixon-Coles clássico, Poisson bivariado, state-space score-driven, ensemble, MLP).
**9 fases**, tudo sob o protocolo único (5 folds temporais + RPS, novo) na branch `clubs`.

**Resultado principal: a arquitetura de produção venceu TUDO.** DC-NB retreinado em clubes bateu
os 7 candidatos B da Fase 1 (inclusive o SOTA da literatura, CatBoost+pi-ratings — RPS 0,1925 nos
challenges), a bateria avançada da Fase 6 (sweep extensivo de hiperparâmetros, state-space
Koopman-Lit-like, ensemble, MLP) e o tuning de hiperparâmetros (Fase 2.5) confirmou que a config
de produção (100 árvores, prof.3, lr=0.05) já é literalmente a melhor entre 18 testadas.
**Nenhuma transferência de clubes→seleções bateu a produção real** (zero-shot piora, pooled é
empate estatístico) — **sem exceção de push**, tudo fica documentado na branch `clubs`.
**Achado que abre porta:** blend DC+HistGBM no BTTS passou a valer com mais dados (não testado
em seleções ainda). Detalhes completos: `backend/docs/RELATORIO_FINAL_PESQUISA_CLUBES.md`.

**Descoberta operacional crítica:** a assinatura API-Football "Ultra" **expira em
2026-07-19T01:21 UTC** (poucos dias após esta sessão). Cota diária (75k) verificada em tempo real
via `/status`. Decisão tomada com autorização do usuário: **12 novas competições** adicionadas a
`backend/scripts/prefetch_clubs.py::LEAGUES` (Eredivisie, Primeira Liga, Jupiler Pro League,
Premiership escocês, Süper Lig, Liga Profesional Argentina, Liga MX, MLS, Pro League saudita,
Championship inglês, AFC Champions League Elite, CAF Champions League, CONCACAF Champions
League) para consumir a cota restante nos dias antes do vencimento — o cron diário
(`prefetch_wc.cmd`, 06:30) já pega esse backlog automaticamente. Também criado
`collect_club_odds_forward.py` (preenche a lacuna de odds de clubes, zero antes desta sessão).

**Reboot inesperado da máquina** (~12:48, provável Windows Update) matou os jobs em background
no meio da execução — recuperado por serem resumíveis por design (CSV incremental). **Lição para
sessões futuras:** Windows recicla PIDs após reboot — sempre conferir `CreationDate`/
`LastBootUpTime` antes de assumir que um PID "vivo" é o processo esperado.

---

## −2. Sessão (2026-07-14) — coleta de clubes travava havia 1 semana (causa raiz + fix)

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

## −3. Sessão (2026-07-11) — Monetização completa (7 fases) + branch `monetization`

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

## −4. Sessão (2026-07-09) — props de finalizações, cópula, Série A

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
  conversão implementadas na branch `monetization`** (§−1) — ainda **não mergeada na `main`** nem
  em produção.
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
2. **Merge da branch `monetization` na `main`** (após revisão) + deploy no Render/Vercel.
3. **Textos jurídicos revisados por advogado** — Termos de Uso, Privacidade/LGPD, Política de
   Créditos, Regulamento de Promoção. Hoje são **templates** em `legal_documents`
   (`app/domains/legal/service.py`), com a marca `(Template inicial — substituir...)`. Publicar via
   `POST /admin/legal/publish` depois de prontos.
4. **Emissor de nota fiscal** — decidir com o contador (NFE.io/Focus NFe/Asaas) e trocar
   `NoopInvoiceProvider` por um adapter real em `app/domains/payments/invoicing.py` (mesmo padrão
   do gateway de pagamento — troca de adapter, sem mexer no fluxo).
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
4. ~~Gateway de pagamento real~~ **implementado** (Mercado Pago, branch `monetization`) — falta só
   credenciais reais + merge/deploy. Ver §2.1.1-2.
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