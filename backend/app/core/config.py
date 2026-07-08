"""
Configuração central da camada de usuários/monetização (pydantic-settings).

Lê de variáveis de ambiente (em produção, do Render) e de `backend/.env` (local).
Defaults seguros para desenvolvimento. NUNCA colocar segredos reais aqui — só nomes
de env vars e defaults inócuos de dev.

O `.env` é lido aqui, e não via `app.db.connection._load_local_dotenv()`: este módulo é
importado antes de `app.db.connection` na cadeia de imports do `app.main`, então depender
daquele carregamento fazia o `.env` ser silenciosamente ignorado para todas as settings
abaixo. Variáveis de ambiente reais continuam tendo precedência sobre o `.env`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]   # .../backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Ambiente ---
    # "production" torna fatais as configurações que em dev são apenas avisos
    # (e-mail em mock, JWT_SECRET default). Setar APP_ENV=production no Render.
    app_env: str = "development"

    # --- Autenticação / tokens ---
    jwt_secret: str = "dev-insecure-change-me"          # OBRIGATÓRIO trocar em produção
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 30

    # --- OTP (verificação de e-mail / recuperação de senha) ---
    otp_length: int = 6
    otp_ttl_min: int = 10
    otp_max_attempts: int = 5
    otp_resend_cooldown_sec: int = 60

    # --- Rate limiting / anti-brute-force ---
    login_max_attempts: int = 5           # tentativas antes do lockout
    login_lockout_min: int = 15
    rate_limit_window_sec: int = 60

    # --- Créditos / monetização ---
    credit_unit_price_brl: float = 1.00   # 1 crédito = R$ 1,00 (pacote base)
    max_combined_odd: float = 2.00        # teto da odd combinada da "Aposta Escolhida"

    # --- Liquidação de apostas ---
    settlement_safety_delay_min: int = 30  # espera pós-jogo antes de liquidar
    settlement_max_attempts: int = 6

    # --- E-mail (OTP) ---
    email_provider: str = "mock"           # mock | zeptomail | smtp
    email_from: str = "no-reply@apostai.local"
    email_from_name: str = "ApostAI"
    email_timeout_sec: float = 10.0

    # ZeptoMail (transacional da Zoho — provedor preferido para OTP).
    # O remetente (email_from) precisa estar num domínio verificado na conta ZeptoMail.
    zeptomail_token: str = ""              # "Send Mail Token" do ZeptoMail (sem o prefixo)
    zeptomail_base_url: str = "https://api.zeptomail.com"  # conta na UE: https://api.zeptomail.eu

    # SMTP (fallback — Zoho Mail: smtp.zoho.com:587 STARTTLS, senha de app)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # --- Gateway de pagamento ---
    payment_provider: str = "mock"         # mock | asaas | mercadopago | pagarme | stripe

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
