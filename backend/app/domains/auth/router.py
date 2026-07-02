"""Rotas de autenticação: cadastro -> OTP -> senha -> login/refresh/logout + recuperação."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.domains.auth import schemas, service
from app.domains.auth.deps import client_ip, get_current_user, get_db
from app.domains.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.MessageResponse, status_code=201)
def register(data: schemas.RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit.hit(f"register:{ip}", max_events=5, window_sec=300)
    service.register(db, data, ip)
    return {"message": "Cadastro iniciado. Enviamos um código de verificação para seu e-mail."}


@router.post("/resend-otp", response_model=schemas.MessageResponse)
def resend_otp(data: schemas.ResendOtpRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit.hit(f"resend:{ip}:{data.email}", max_events=3, window_sec=300)
    service.resend_otp(db, data.email, data.purpose, ip)
    return {"message": "Se o e-mail existir, um novo código foi enviado."}


@router.post("/verify-email", response_model=schemas.PasswordSetupResponse)
def verify_email(data: schemas.VerifyEmailRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit.hit(f"verify:{ip}:{data.email}", max_events=10, window_sec=300)
    token = service.verify_email(db, data.email, data.code, ip)
    return {"setup_token": token}


@router.post("/set-password", response_model=schemas.TokenResponse)
def set_password(data: schemas.SetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    return service.set_password(db, data.setup_token, data.password, client_ip(request))


@router.post("/login", response_model=schemas.TokenResponse)
def login(data: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit.hit(f"login:{ip}", max_events=10, window_sec=60)
    ua = request.headers.get("user-agent")
    return service.login(db, data.email, data.password, ip, ua)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(data: schemas.RefreshRequest, request: Request, db: Session = Depends(get_db)):
    ua = request.headers.get("user-agent")
    return service.refresh(db, data.refresh_token, client_ip(request), ua)


@router.post("/logout", response_model=schemas.MessageResponse)
def logout(data: schemas.RefreshRequest, request: Request, db: Session = Depends(get_db)):
    service.logout(db, data.refresh_token, client_ip(request))
    return {"message": "Sessão encerrada."}


@router.post("/forgot-password", response_model=schemas.MessageResponse)
def forgot_password(data: schemas.ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit.hit(f"forgot:{ip}", max_events=5, window_sec=300)
    service.forgot_password(db, data.email, ip)
    return {"message": "Se o e-mail existir, enviamos um código para redefinir a senha."}


@router.post("/reset-password", response_model=schemas.MessageResponse)
def reset_password(data: schemas.ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    service.reset_password(db, data.email, data.code, data.password, client_ip(request))
    return {"message": "Senha redefinida com sucesso."}


@router.get("/me", response_model=schemas.UserPublic)
def me(user: User = Depends(get_current_user)):
    return schemas.UserPublic(
        id=str(user.id), full_name=user.full_name, email=user.email, cpf=user.cpf,
        phone=user.phone, status=user.status.value, role=user.role.value,
    )
