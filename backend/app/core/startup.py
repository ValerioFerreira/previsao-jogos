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
            f"email_provider={settings.email_provider} remetente={settings.email_from}"
        )
        logger.info(linha)
        print(linha, flush=True)
        return

    if settings.is_production:
        detalhe = "\n".join(f"  - {p}" for p in problems)
        raise ConfigError(f"Configuração inválida para APP_ENV=production:\n{detalhe}")

    for p in problems:
        logger.warning("[config:dev] %s", p)
