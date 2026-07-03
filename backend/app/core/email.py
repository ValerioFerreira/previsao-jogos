"""Abstração de envio de e-mail (adapter trocável). Hoje: 'mock' (loga o conteúdo).
Adapters reais (Resend/SES/SMTP) plugam pela mesma interface, escolhidos por settings."""
from __future__ import annotations

import logging
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger("app.email")


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class MockEmailSender:
    """Não envia nada — loga (para o revisor ver o código OTP no console do backend)."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("[EMAIL:mock] para=%s | assunto=%s\n%s", to, subject, body)
        print(f"\n[EMAIL:mock] -> {to}\n  {subject}\n  {body}\n", flush=True)


def get_email_sender() -> EmailSender:
    provider = (settings.email_provider or "mock").lower()
    # Adapters reais entram aqui (resend/ses/smtp) quando configurados.
    if provider != "mock":
        logger.warning("email_provider=%s ainda não implementado; usando mock.", provider)
    return MockEmailSender()


def send_otp_email(to: str, code: str, purpose: str) -> None:
    assunto = "Seu código de verificação" if purpose == "email_verify" else "Recuperação de senha"
    corpo = (
        f"Seu código é: {code}\n"
        f"Ele expira em {settings.otp_ttl_min} minutos.\n"
        "Se você não solicitou, ignore este e-mail."
    )
    get_email_sender().send(to, assunto, corpo)
