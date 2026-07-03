"""
Configuração central da camada de usuários/monetização (pydantic-settings).

Lê de variáveis de ambiente (em produção, do Render; local, do backend/.env carregado
por app.db.connection). Defaults seguros para desenvolvimento. NUNCA colocar segredos
reais aqui — só nomes de env vars e defaults inócuos de dev.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

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
    email_provider: str = "mock"           # mock | resend | ses | smtp
    email_from: str = "no-reply@apostai.local"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # --- Gateway de pagamento ---
    payment_provider: str = "mock"         # mock | asaas | mercadopago | pagarme | stripe

    @property
    def is_production(self) -> bool:
        return self.jwt_secret != "dev-insecure-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
