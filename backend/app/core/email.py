"""Abstração de envio de e-mail (adapter trocável), escolhido por `settings.email_provider`.

- `mock`      — não envia, loga o conteúdo (código OTP visível no console do backend).
- `zeptomail` — ZeptoMail (transacional da Zoho). Provedor preferido para OTP.
- `smtp`      — SMTP genérico; para Zoho Mail use smtp.zoho.com:587 + senha de app.

Falha de envio levanta `EmailSendError`. Isso é deliberado: `_create_and_send_otp` grava
a linha de OTP e só então envia, commitando depois. Ao levantar antes do commit, a sessão
fecha sem persistir o OTP — o usuário não fica com um código que nunca chegou nem preso
no cooldown de reenvio, e pode tentar de novo na hora.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger("app.email")


class EmailSendError(RuntimeError):
    """Falha ao entregar o e-mail ao provedor. O chamador traduz para um erro HTTP limpo."""


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class MockEmailSender:
    """Não envia nada — loga (para o revisor ver o código OTP no console do backend)."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("[EMAIL:mock] para=%s | assunto=%s\n%s", to, subject, body)
        print(f"\n[EMAIL:mock] -> {to}\n  {subject}\n  {body}\n", flush=True)


class ZeptoMailSender:
    """ZeptoMail via API HTTP. Autentica com o Send Mail Token no header Authorization."""

    def __init__(self, token: str, base_url: str, from_addr: str, from_name: str, timeout: float):
        self._url = f"{base_url.rstrip('/')}/v1.1/email"
        # O token já vem prefixado com "Zoho-enczapikey " em algumas telas do painel;
        # aceitamos as duas formas para não depender de como foi colado na env var.
        self._auth = token if token.startswith("Zoho-enczapikey") else f"Zoho-enczapikey {token}"
        self._from = {"address": from_addr, "name": from_name}
        self._timeout = timeout

    def send(self, to: str, subject: str, body: str) -> None:
        payload = {
            "from": self._from,
            "to": [{"email_address": {"address": to}}],
            "subject": subject,
            "textbody": body,
        }
        try:
            resp = httpx.post(
                self._url,
                json=payload,
                headers={"Authorization": self._auth, "Accept": "application/json"},
                timeout=self._timeout,
            )
        except httpx.RequestError as e:
            raise EmailSendError(f"ZeptoMail inacessível: {e}") from e

        if resp.status_code >= 400:
            # Nunca logar o corpo do e-mail (contém o código OTP); só o erro do provedor.
            logger.error("[EMAIL:zeptomail] HTTP %s para=%s: %s", resp.status_code, to, resp.text[:300])
            raise EmailSendError(f"ZeptoMail respondeu HTTP {resp.status_code}")
        logger.info("[EMAIL:zeptomail] enviado para=%s assunto=%s", to, subject)


class SmtpEmailSender:
    """SMTP genérico. Para Zoho Mail: smtp.zoho.com:587, STARTTLS, senha de aplicativo."""

    def __init__(self, host: str, port: int, user: str, password: str,
                 from_addr: str, from_name: str, starttls: bool, timeout: float):
        self._host, self._port = host, port
        self._user, self._password = user, password
        self._from_addr, self._from_name = from_addr, from_name
        self._starttls, self._timeout = starttls, timeout

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = f"{self._from_name} <{self._from_addr}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            if self._starttls:
                with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as s:
                    s.starttls()
                    s.login(self._user, self._password)
                    s.send_message(msg)
            else:  # porta 465 — TLS implícito
                with smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout) as s:
                    s.login(self._user, self._password)
                    s.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise EmailSendError(f"SMTP falhou: {e}") from e
        logger.info("[EMAIL:smtp] enviado para=%s assunto=%s", to, subject)


def _build_sender() -> EmailSender:
    provider = (settings.email_provider or "mock").lower()

    if provider == "mock":
        return MockEmailSender()

    if provider == "zeptomail":
        if not settings.zeptomail_token:
            raise EmailSendError("EMAIL_PROVIDER=zeptomail mas ZEPTOMAIL_TOKEN está vazio.")
        return ZeptoMailSender(
            token=settings.zeptomail_token,
            base_url=settings.zeptomail_base_url,
            from_addr=settings.email_from,
            from_name=settings.email_from_name,
            timeout=settings.email_timeout_sec,
        )

    if provider == "smtp":
        if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
            raise EmailSendError("EMAIL_PROVIDER=smtp mas SMTP_HOST/USER/PASSWORD estão incompletos.")
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            from_addr=settings.email_from,
            from_name=settings.email_from_name,
            starttls=settings.smtp_starttls,
            timeout=settings.email_timeout_sec,
        )

    raise EmailSendError(f"email_provider={provider!r} não é suportado.")


def get_email_sender() -> EmailSender:
    return _build_sender()


def send_otp_email(to: str, code: str, purpose: str) -> None:
    assunto = "Seu código de verificação" if purpose == "email_verify" else "Recuperação de senha"
    corpo = (
        f"Seu código é: {code}\n"
        f"Ele expira em {settings.otp_ttl_min} minutos.\n"
        "Se você não solicitou, ignore este e-mail."
    )
    get_email_sender().send(to, assunto, corpo)
