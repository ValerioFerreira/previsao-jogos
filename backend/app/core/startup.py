"""Validação de configuração no boot — falha rápido em vez de falhar no primeiro usuário.

O cadastro depende de três coisas: e-mail entregável, JWT assinado com segredo real e
remetente verificado. Nenhuma delas se manifesta no boot por padrão: com `EMAIL_PROVIDER`
não setado a app sobe, o `POST /auth/register` devolve 201 ("enviamos um código"), e o OTP
vai parar no log do servidor. Ninguém consegue concluir o cadastro e nada acusa erro.

Em `APP_ENV=production` essas condições viram erro fatal de boot. Em desenvolvimento,
apenas avisos — o mock continua sendo o caminho normal de trabalho local.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.core.email import EmailSendError, get_email_sender

logger = logging.getLogger("app.startup")

_JWT_DEFAULT = "dev-insecure-change-me"
_EMAIL_FROM_DEFAULT = "no-reply@apostai.local"


class ConfigError(RuntimeError):
    """Configuração inválida para o ambiente atual. Impede o boot em produção."""


def _problems() -> list[str]:
    """Condições que quebrariam o cadastro em produção."""
    out: list[str] = []
    provider = (settings.email_provider or "mock").lower()

    if provider == "mock":
        out.append(
            "EMAIL_PROVIDER=mock — nenhum e-mail é entregue; o código OTP só aparece no log. "
            "Use 'zeptomail' (ou 'smtp')."
        )
    else:
        # Constrói o sender agora: credencial faltando levanta aqui, no boot,
        # e não como um 502 no primeiro cadastro de um usuário real.
        try:
            get_email_sender()
        except EmailSendError as e:
            out.append(f"Configuração de e-mail inválida: {e}")

    if settings.email_from == _EMAIL_FROM_DEFAULT:
        out.append(
            f"EMAIL_FROM ainda é o placeholder '{_EMAIL_FROM_DEFAULT}' — precisa ser um endereço "
            "de domínio verificado na Zoho, senão a entrega é recusada."
        )

    if settings.jwt_secret == _JWT_DEFAULT:
        out.append("JWT_SECRET ainda é o default de desenvolvimento — tokens seriam forjáveis.")

    out.extend(_payment_problems())
    out.extend(_invoice_problems())
    return out


def _payment_problems() -> list[str]:
    out: list[str] = []
    provider = (settings.payment_provider or "mock").lower()
    if provider == "mock":
        out.append(
            "PAYMENT_PROVIDER=mock — nenhum pagamento real é processado; "
            "use 'mercadopago' em produção."
        )
    elif provider == "mercadopago":
        if not settings.mp_access_token:
            out.append("MP_ACCESS_TOKEN ausente — obrigatório com PAYMENT_PROVIDER=mercadopago.")
        if not settings.mp_public_key:
            out.append("MP_PUBLIC_KEY ausente.")
        if not settings.mp_webhook_secret:
            out.append(
                "MP_WEBHOOK_SECRET ausente — verify_signature() sempre rejeitaria o webhook."
            )
    else:
        out.append(f"PAYMENT_PROVIDER='{provider}' desconhecido — sem adapter implementado.")
    return out


def _invoice_problems() -> list[str]:
    out: list[str] = []
    provider = (settings.invoice_provider or "noop").lower()
    if provider == "nfeio":
        required = {
            "NFEIO_API_TOKEN": settings.nfeio_api_token,
            "NFEIO_COMPANY_ID": settings.nfeio_company_id,
            "COMPANY_CNPJ": settings.company_cnpj,
            "COMPANY_RAZAO_SOCIAL": settings.company_razao_social,
            "COMPANY_INSCRICAO_MUNICIPAL": settings.company_inscricao_municipal,
            "COMPANY_CITY_SERVICE_CODE": settings.company_city_service_code,
        }
        for name, value in required.items():
            if not value:
                out.append(f"{name} ausente — obrigatório com INVOICE_PROVIDER=nfeio.")
    elif settings.is_production:
        # Diferente de e-mail/pagamento: não emitir nota real não bloqueia o lançamento
        # (é o default seguro documentado do NoopInvoiceProvider) — só avisa, sempre,
        # mesmo em produção, para não ser esquecido silenciosamente.
        logger.warning("[config:prod] INVOICE_PROVIDER=noop — nenhuma nota fiscal real será emitida.")
    return out


def validate_startup_config() -> None:
    """Chamada no import de `app.main`. Fatal em produção, aviso em desenvolvimento."""
    problems = _problems()

    if not problems:
        # print além do logger: sem handler configurado o root logger descarta INFO
        # (lastResort só emite >= WARNING), e esta linha é justamente a confirmação
        # que se procura no log do Render depois de um deploy.
        linha = (
            f"[config] OK — app_env={settings.app_env} "
            f"email_provider={settings.email_provider} remetente={settings.email_from} "
            f"payment_provider={settings.payment_provider} invoice_provider={settings.invoice_provider}"
        )
        logger.info(linha)
        print(linha, flush=True)
        return

    if settings.is_production:
        detalhe = "\n".join(f"  - {p}" for p in problems)
        raise ConfigError(f"Configuração inválida para APP_ENV=production:\n{detalhe}")

    for p in problems:
        logger.warning("[config:dev] %s", p)
