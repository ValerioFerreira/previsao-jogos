# Arquitetura — Camada de Usuários, Créditos, Promoções e Monetização

> Etapa 1 (obrigatória): análise da arquitetura existente + desenho da arquitetura-alvo,
> escalável e preparada para o Painel Administrativo. A implementação deve seguir este documento.
> Status: **desenho para aprovação** (nenhum código de negócio escrito ainda). Data: 2026-07-02.

## 1. Estado atual (análise)

| Camada | Hoje | Impacto |
|---|---|---|
| Backend | FastAPI **stateless**, só leitura (previsões/estatísticas). `app/main.py`, `app/services/*`, `app/db/connection.py`. | Precisa ganhar estado transacional (usuários, carteira, apostas) sem tocar nas rotas de previsão. |
| Persistência | SQLAlchemy **Core** + pandas (`upsert_df`, `truncate_and_append`). Sem ORM, sem migrations. | Introduzir **ORM declarativo + Alembic** (migrations versionadas). O pipeline de dados continua como está. |
| Auth | **Inexistente.** `AuthContext.jsx`/`base44` é código morto (deps ausentes). | Construir auth do zero. Remover o resquício Base44. |
| Frontend | Next.js App Router + shadcn/ui. Páginas `page.tsx` (Previsões), `construir-aposta/`, `estatisticas/`. Já tem `input-otp`. | Unificar Previsões+Construir Aposta em **Análise**; adicionar auth, perfil, carteira. |
| Banco | Neon Postgres (tabelas de dados). | Adicionar schema transacional isolado (prefixo/So schema `app_*`). |

**Princípios inegociáveis:** (1) saldo **nunca** é alterado direto — toda mudança é um **lançamento** no ledger; (2) **idempotência** em todo movimento financeiro (chave de idempotência + constraints + transação); (3) tudo **auditável**; (4) **snapshots imutáveis** de análise; (5) segredos e PII protegidos; (6) modelado para o **Painel Admin** desde já.

## 2. Arquitetura-alvo (visão)

Backend FastAPI **modular por domínio** (`app/domains/{auth,users,wallet,payments,analysis,bets,promotions,legal,admin}`), cada um com `models.py` (ORM), `schemas.py` (Pydantic), `service.py` (regra de negócio), `router.py` (HTTP). ORM + **Alembic**. As rotas de previsão atuais ficam intactas (`predictor_service`), agora consumidas **por dentro** pelo domínio de análise.

```
Frontend (Next.js)  →  API FastAPI
                        ├─ auth/      (registro, OTP, login, refresh, recuperação)
                        ├─ users/     (perfil, dados, documentos aceitos)
                        ├─ wallet/    (ledger de créditos: disponível/reservado)
                        ├─ payments/  (gateway abstrato + webhooks idempotentes)
                        ├─ analysis/  (gera previsão + snapshot imutável + versão)
                        ├─ bets/      (aposta promocional, odd ≤2.00, imutável, estados)
                        ├─ promotions/(promo "Só Paga se Acertar", cupons, campanhas…)
                        ├─ legal/     (documentos versionados + aceite)
                        └─ admin/     (gestão total — próxima etapa, já modelado)
Worker/cron  →  liquidação automática de apostas (pós-jogo, delay de segurança, API-Football)
```

## 3. Modelo de dados (schema `app_*`, admin-ready)

### Identidade & segurança
- **users**: `id uuid pk`, `full_name`, `email citext unique`, `cpf char(11) unique`, `phone unique`, `password_hash`, `email_verified_at`, `status` [`pending_verification`|`active`|`blocked`|`deleted`], `role` [`user`|`admin`|`superadmin`], `created_at`, `signup_ip`, `last_login_at`, `last_login_ip`. (CPF/phone com criptografia em repouso ou coluna de acesso restrito.)
- **otp_codes**: `id`, `user_id`, `purpose` [`email_verify`|`password_reset`], `code_hash`, `expires_at`, `attempts`, `max_attempts`, `consumed_at`, `created_ip`.
- **auth_sessions**: `id`, `user_id`, `refresh_token_hash`, `user_agent`, `ip`, `expires_at`, `revoked_at`.
- **auth_events** (auditoria): `id`, `user_id`, `event`, `ip`, `user_agent`, `metadata jsonb`, `created_at`.

### Legal / LGPD
- **legal_documents**: `id`, `type` [`terms`|`privacy`|`lgpd`|`credits_policy`|`promo_regulation`], `version`, `title`, `body_md`, `published_at`, `is_current bool`, `created_by`.
- **user_document_acceptances**: `id`, `user_id`, `document_id`, `accepted_at`, `ip`. (Re-aceite exigido quando `is_current` muda.)

### Carteira & créditos (ledger — fonte de verdade)
- **wallets**: `id`, `user_id unique`, `available_balance`, `reserved_balance` (cache derivado, atualizado **na mesma transação** do lançamento).
- **credit_transactions**: `id`, `wallet_id`, `type` [`purchase`|`bonus`|`promo_credit`|`reservation`|`reservation_release`|`consumption`|`refund`|`chargeback`|`manual_adjustment`|`cashback`], `amount` (assinado), `balance_after`, `reserved_after`, `status` [`pending`|`completed`|`reversed`], `reference_type`, `reference_id`, `description`, `idempotency_key unique`, `created_by` (admin, se manual), `created_at`.
- Saldo = soma do ledger. **Nunca** `UPDATE saldo = x` fora de um lançamento.

### Pagamentos (gateway abstrato)
- **credit_packages**: `id`, `name`, `credits`, `price_brl`, `bonus_credits`, `active`. (1 crédito = R$1,00 no pacote base; pacotes/bônus/descontos futuros.)
- **payment_orders**: `id`, `user_id`, `provider` [`asaas`|`mercadopago`|`pagarme`|`stripe`], `provider_order_id`, `amount_brl`, `credits`, `package_id?`, `status` [`created`|`pending`|`paid`|`failed`|`canceled`|`refunded`], `method`, `idempotency_key`, `raw_payload jsonb`, `paid_at`.
- **payment_webhooks**: `id`, `provider`, `event`, `payload jsonb`, `signature_verified`, `received_at`, `processed_at`. (Processamento idempotente.)
- **payment_cards**: `id`, `user_id`, `provider`, `provider_token`, `brand`, `last4`, `exp_month/year`, `is_default`. **Só token** — nunca PAN/CVV.

### Análise (previsão) — snapshot imutável + versão
- **analyses**: `id`, `user_id`, `type` [`independent`|`future_match`], `home_team`, `away_team`, `tournament`, `fixture_id?`, `algo_version`, `data_version`, `model_hash`, `generated_at`, `snapshot jsonb` (probabilidades, mercados, odds, indicadores, dados de gráfico), `credit_tx_id`, `status`. **`snapshot` nunca muda.**

### Apostas promocionais — imutáveis, com estados
- **bets**: `id`, `user_id`, `analysis_id`, `fixture_id`, `match_datetime`, `combined_odd` (≤ 2.00), `reserved_tx_id`, `status` [`awaiting_start`|`in_progress`|`awaiting_settlement`|`won`|`lost`|`credit_consumed`|`credit_refunded`|`canceled`], `created_at`. **Imutável após confirmação.**
- **bet_selections**: `id`, `bet_id`, `market_key`, `selection`, `odd`, `snapshot_ref`. (Mercados escolhidos, imutáveis.)
- **bet_settlements**: `id`, `bet_id`, `safety_delay_until`, `settled_at`, `api_result jsonb`, `outcome` [`won`|`lost`|`void`], `attempts`.

### Promoções & campanhas (extensível)
- **promotions**: `id`, `code`, `name`, `type` [`refund_if_lose`|`bonus_credit`|`coupon`|`cashback`|`referral`|`seasonal`], `config jsonb` (regras), `max_odd`, `starts_at`, `ends_at`, `active`, `created_by`.
- **promotion_participations**, **coupons** (`usage_limit`, `per_user_limit`), **referrals** (`referrer`, `referred`, `reward`).
- A promo **"Só Paga se Acertar"** = uma linha em `promotions` com `type=refund_if_lose`, `max_odd=2.00`, config apontando para a mecânica de reserva→consumo/estorno. Nada hardcoded.

### Admin & operação (próxima etapa, já modelado)
- **admin_audit_log**: `id`, `admin_id`, `action`, `target_type`, `target_id`, `before jsonb`, `after jsonb`, `ip`, `created_at`.
- **platform_settings**: `key`, `value jsonb` (gateway ativo, feature flags, delays de liquidação, banners).
- **banners**: `id`, `title`, `body`, `type`, `active`, `starts_at`, `ends_at`.

## 4. Fluxos-chave

**Cadastro:** dados (nome/email/CPF/telefone) → valida CPF (dígitos verificadores) + formato telefone + unicidade → cria `user(pending_verification)` → OTP por e-mail (hash, expira, tentativas) → verifica OTP → cria senha definitiva → `active`. Recuperação de senha e reenvio pelo mesmo mecanismo de OTP.

**Comprar créditos:** `payment_orders(created)` → gateway (adapter) → webhook idempotente confirma `paid` → lançamento `purchase` no ledger (idempotente pela `idempotency_key`).

**Análise Independente:** consome **1 crédito imediatamente** (`consumption`), gera snapshot, **sem** promoção nem "Aposta Escolhida".

**Análise de Partida Futura:** **reserva 1 crédito** (`reservation`), gera snapshot, habilita "Aposta Escolhida".

**Aposta Escolhida:** usuário combina mercados **da própria análise**; sistema calcula a odd combinada em tempo real e **bloqueia se > 2.00**; confirmação mostra tudo e torna a aposta **imutável**.

**Liquidação (worker):** após o fim do jogo + **delay de segurança** → consulta API-Football → avalia cada seleção contra o snapshot → **acertou** ⇒ `consumption` do crédito reservado; **errou** ⇒ `reservation_release` (estorno para disponível). Idempotente, com retries e auditoria.

## 5. Segurança (transversal)
Hash de senha **argon2/bcrypt**; **JWT de acesso curto + refresh rotativo** em cookie `httpOnly/Secure/SameSite`; **CSRF** (double-submit) nos endpoints com cookie; **rate limiting** por IP e por conta; **lockout** anti-brute-force; OTP com expiração e limite de tentativas; **SQLi** evitado pelo ORM parametrizado; **XSS** pelo escaping do React + CSP; validação de entrada por Pydantic; **logs de autenticação**; PII (CPF/telefone) com acesso restrito/cripto; idempotência e transações em todo movimento financeiro; segredos só em env vars.

## 6. Escalabilidade & extensões futuras
Assinaturas/planos (`subscriptions`, `plans`), cupons, créditos promocionais, cashback, campanhas sazonais, indicação e bônus — todos **encaixam no schema acima** via `promotions.type`+`config jsonb` e novos lançamentos no ledger, sem refatoração. Gateway trocável por adapter. Painel Admin opera tudo por cima dos mesmos serviços + `admin_audit_log`.

## 7. Roadmap de implementação (fases reviewáveis)
0. **Fundação:** ORM + Alembic + config, sem tocar nas rotas de previsão.
1. **Migrations** de todos os domínios (schema acima).
2. **Auth core:** cadastro→OTP→senha→login, refresh, recuperação, rate limit, CSRF, auditoria, validação CPF/telefone.
3. **Carteira + ledger + compra de créditos** (gateway abstrato + 1 adapter; webhooks idempotentes).
4. **Documentos legais** versionados + aceite + re-aceite.
5. **Página "Análise" unificada** (front) + snapshot/versão persistidos; consumo/reserva ao gerar.
6. **"Aposta Escolhida"** (≤2.00 em tempo real) + confirmação imutável + estados.
7. **Worker de liquidação** (pós-jogo, delay, API, consumo/estorno).
8. **Perfil** (seções) + históricos (financeiro, análises, apostas).
9. **APIs/permA-issões prontas para o Painel Admin.**
Transversal a todas: segurança, LGPD, testes.
