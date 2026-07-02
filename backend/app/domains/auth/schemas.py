"""Schemas (Pydantic) da API de autenticação. Validação de CPF/telefone/e-mail e senha."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.validators import is_valid_cpf, is_valid_phone, normalize_cpf, normalize_phone


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=160)
    email: EmailStr
    cpf: str
    phone: str

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str) -> str:
        if not is_valid_cpf(v):
            raise ValueError("CPF inválido.")
        return normalize_cpf(v)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        if not is_valid_phone(v):
            raise ValueError("Telefone inválido.")
        return normalize_phone(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if " " not in v:
            raise ValueError("Informe o nome completo.")
        return v


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class PasswordSetupResponse(BaseModel):
    setup_token: str
    message: str = "E-mail verificado. Crie sua senha."


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("A senha deve ter ao menos 8 caracteres.")
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("A senha deve conter letras e números.")
    return v


class SetPasswordRequest(BaseModel):
    setup_token: str
    password: str

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ResendOtpRequest(BaseModel):
    email: EmailStr
    purpose: str = "email_verify"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)
    password: str

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)


class UserPublic(BaseModel):
    id: str
    full_name: str
    email: str
    cpf: str
    phone: str
    status: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
