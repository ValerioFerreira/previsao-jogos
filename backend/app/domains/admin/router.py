"""Rotas do Painel Administrativo — todas exigem papel admin/superadmin.
Cobrem: usuários, créditos, financeiro, análises, apostas, promoções, documentos,
settings, banners e auditoria. Toda mutação é registrada em AdminAuditLog."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.domains.admin import schemas, service
from app.domains.auth.deps import client_ip, get_db, require_admin
from app.domains.users.models import User

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- usuários ----------
@router.get("/users", response_model=schemas.AdminUsersPage)
def users(q: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
          _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_users(db, q, limit, offset)


@router.get("/users/{user_id}", response_model=schemas.AdminUserItem)
def user_detail(user_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.get_user(db, user_id)


@router.post("/users/{user_id}/block", response_model=schemas.OkResponse)
def block(user_id: str, data: schemas.BlockRequest, request: Request,
          admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    service.set_blocked(db, admin, user_id, True, data.reason, client_ip(request))
    return schemas.OkResponse(detail="Usuário bloqueado.")


@router.post("/users/{user_id}/unblock", response_model=schemas.OkResponse)
def unblock(user_id: str, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    service.set_blocked(db, admin, user_id, False, None, client_ip(request))
    return schemas.OkResponse(detail="Usuário desbloqueado.")


@router.post("/users/{user_id}/credits")
def adjust_credits(user_id: str, data: schemas.CreditAdjustRequest, request: Request,
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.adjust_credits(db, admin, user_id, data, client_ip(request))


# ---------- financeiro / listagens ----------
@router.get("/payments")
def payments(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
             _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_payments(db, limit, offset)


@router.get("/transactions")
def transactions(user_id: str | None = None, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_transactions(db, user_id, limit, offset)


@router.get("/analyses")
def analyses(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
             _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_analyses(db, limit, offset)


@router.get("/bets")
def bets(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
         _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_bets(db, limit, offset)


# ---------- promoções ----------
@router.get("/promotions")
def list_promotions(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_promotions(db)


@router.post("/promotions", status_code=201)
def create_promotion(data: schemas.PromotionRequest, request: Request,
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_promotion(db, admin, data, client_ip(request))


@router.patch("/promotions/{promo_id}")
def patch_promotion(promo_id: str, data: schemas.PromotionPatch, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_promotion(db, admin, promo_id, data, client_ip(request))


# ---------- documentos legais ----------
@router.post("/legal/publish", status_code=201)
def publish_document(data: schemas.LegalPublishRequest, request: Request,
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.publish_document(db, admin, data, client_ip(request))


# ---------- settings / banners ----------
@router.get("/settings")
def get_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.get_settings(db)


@router.put("/settings/{key}")
def set_setting(key: str, data: schemas.SettingRequest, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.set_setting(db, admin, key, data, client_ip(request))


@router.get("/banners")
def list_banners(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_banners(db)


@router.post("/banners", status_code=201)
def create_banner(data: schemas.BannerRequest, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_banner(db, admin, data, client_ip(request))


# ---------- auditoria ----------
@router.get("/audit")
def audit_log(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_audit(db, limit, offset)
