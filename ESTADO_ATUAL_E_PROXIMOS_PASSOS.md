# Estado atual e próximos passos (handoff)

> **Leia isto primeiro.** Resume onde o projeto está e o que fazer a seguir, para retomar
> exatamente de onde paramos. Última atualização: **2026-07-09**.
> Docs de apoio: `DOCUMENTACAO_CENTRAL.md` (doc-mestre), `ARCHITECTURE.md` (infra — **§6 é o
> e-mail transacional**), `docs/ARQUITETURA_MONETIZACAO.md` (desenho da monetização).

---

## −1. Última sessão (2026-07-09) — props de finalizações, cópula, Série A

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
- **Camada de monetização:** funcional ponta a ponta, validada ao vivo no Neon.
- **Cadastro: FUNCIONANDO em produção.** Env vars configuradas no Render; um cadastro real no site
  foi concluído com o código OTP chegando por e-mail (confirmado pelo dono em 2026-07-08).
  Logo, `EMAIL_PROVIDER=zeptomail` está setado e o domínio está verificado na Zoho.
- **Gateway de pagamento:** ainda em **mock** (`POST /payments/mock/confirm/{id}`).
- **Conta demo:** `demo.apostai@gmail.com` / `Demo1234` (admin, com créditos).

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
Mapa do código: `backend/app/domains/{users,legal,wallet,payments,analysis,bets,promotions,admin}`
(`models/schemas/service/router` cada); `backend/app/core/{config,email,startup,security,rate_limit}.py`;
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

### Para ir a produção de verdade (monetização)
4. **Gateway de pagamento real:** escolher (Asaas/MercadoPago/Pagar.me/Stripe), implementar o
   adapter em `app/domains/payments/gateways/` + webhook assinado, setar `PAYMENT_PROVIDER`.
5. **Agendar a liquidação:** cron chamando `scripts/settle_bets.py` ou
   `POST /api/cron/settle-bets?token=$CRON_TOKEN` (a cada ~30 min). Definir `CRON_TOKEN`.
6. **Revisar textos legais** (Termos/Privacidade/LGPD/Créditos/Regulamento) — hoje são **templates**
   (`app/domains/legal/service.py`); publicar as versões reais via `POST /admin/legal/publish`.

### Dados de jogo na nuvem — planejado, NÃO iniciado
7. Os dados de jogo vivem hoje numa **máquina local**. O dono quer movê-los para a nuvem, mas
   **adiou explicitamente** esse trabalho. Antes de começar, ler `ARCHITECTURE.md` §3: a medição
   feita em 2026-07-08 mostra que `matches.parquet` tem **101 KB** e que o
   `historico_completo.json` de **205 MB nunca entrou no Neon** — o gargalo não é o que parece.
   O problema real é que o cache apontado por `fixture_index` é **efêmero no Render** (some a cada
   redeploy → o sistema reconsome cota da API-Football). Destino natural: **object storage**, não
   tabela de banco. **Não** mover o ledger (`app_credit_transactions`) para fora do Postgres: ele
   depende de transação multi-registro + `idempotency_key UNIQUE` atômica.

### Refinos
8. **Rate limit é em memória** (`app/core/rate_limit.py` já documenta). Com mais de um worker no
   Render, o limite passa a ser por processo. Não bloqueia o lançamento — o lockout por conta é
   persistido no banco e segue íntegro. Trocar por Redis mantendo a interface `hit()`.
9. **Testes automatizados** — `scripts/verify_signup_flow.py` é o primeiro do repo; não há runner
   (pytest não está nas deps). Os demais checks desta jornada rodaram em scratchpad e se perderam.
10. **Nomes de seleções restantes:** ~77 entidades sem `team_id` são não-FIFA/históricas
    (Abkhazia, Catalonia, Padania…), ausentes da API-Football — sem solução via API.

### Analytics (motor de previsão) — janelas abertas (ver `DOCUMENTACAO_CENTRAL.md` §9)
11. **Backtest financeiro (ROI/yield) + RPS** — a validação que mais falta (acumular odds de fechamento).
12. **xG denso / tracking** — única fonte plausível de sinal novo ortogonal ao Elo.
> Já fechado/não repetir: forma de jogador no resultado, GP vs NB, calibração do resultado,
> posse/passes, XGBoost/LightGBM, cadeia de regressão, cópula, ataque×defesa, dispersão dinâmica.

## 6. Notas / gotchas
- **`EMAIL_PROVIDER` sem valor = `mock` = cadastro silenciosamente quebrado.** É o motivo de existir
  a validação de boot. Nunca reintroduzir fallback para mock em provider desconhecido.
- **Nunca logar o corpo do e-mail** — ele contém o código OTP. O `ZeptoMailSender` loga só o status
  HTTP e o destinatário.
- O `.venv/` da raiz **não** tem as deps da camada de usuários (`pydantic_settings`, `fastapi`…).
- A camada `app_*` é **isolada** do pipeline de dados; migrations não tocam as tabelas de previsão.
- O harness do Claude **bloqueia** escrever/apagar `backend/.env` (arquivo de credencial não
  rastreado) e migração em produção por auto-mode. Rodar `alembic upgrade head` como dono do ambiente.
- Odd justa é referência analítica (sem margem de casa) e **nunca < 1,00**; a plataforma remunera o
  uso da IA, a promoção é campanha de estorno — não é aposta.
- `ARCHITECTURE.md` §3 foi **corrigido** em 2026-07-08: a versão anterior descrevia um "Raw Data
  Lake" em coluna `JSONB` que nunca existiu no código.
