"""Rotas do Painel Administrativo — todas exigem papel admin/superadmin.
Cobrem: usuários, créditos, financeiro, análises, apostas, promoções, documentos,
settings, banners e auditoria. Toda mutação é registrada em AdminAuditLog."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.domains.admin import schemas, service
from app.domains.auth.deps import client_ip, get_db, require_admin
from app.domains.support.schemas import TicketPatch
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


# ---------- dashboard executivo ----------
@router.get("/analytics/dashboard")
def analytics_dashboard(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.analytics_dashboard(db)


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


# ---------- cupons ----------
@router.get("/coupons")
def list_coupons(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_coupons(db)


@router.post("/coupons", status_code=201)
def create_coupon(data: schemas.CouponRequest, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_coupon(db, admin, data, client_ip(request))


@router.patch("/coupons/{coupon_id}")
def patch_coupon(coupon_id: str, data: schemas.CouponPatch, request: Request,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_coupon(db, admin, coupon_id, data, client_ip(request))


@router.delete("/coupons/{coupon_id}", response_model=schemas.OkResponse)
def delete_coupon(coupon_id: str, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    service.delete_coupon(db, admin, coupon_id, client_ip(request))
    return schemas.OkResponse(detail="Cupom excluído.")


@router.get("/coupons/analytics")
def coupon_analytics(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.coupon_analytics(db)


# ---------- parceiros (afiliados) ----------
@router.get("/affiliates")
def list_affiliates(status: str | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_affiliates(db, status)


@router.get("/affiliates/{affiliate_id}")
def affiliate_detail(affiliate_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.get_affiliate_detail(db, affiliate_id)


@router.post("/affiliates", status_code=201)
def create_affiliate(data: schemas.AffiliateRequest, request: Request,
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_affiliate(db, admin, data, client_ip(request))


@router.patch("/affiliates/{affiliate_id}")
def patch_affiliate(affiliate_id: str, data: schemas.AffiliatePatch, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_affiliate(db, admin, affiliate_id, data, client_ip(request))


@router.post("/affiliates/{affiliate_id}/approve")
def approve_affiliate(affiliate_id: str, request: Request,
                      data: schemas.AffiliateApproveRequest = schemas.AffiliateApproveRequest(),
                      admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.approve_affiliate(db, admin, affiliate_id, client_ip(request), code=data.code)


@router.get("/demo-usage")
def demo_usage(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.demo_usage_by_cpf(db)


@router.post("/affiliates/{affiliate_id}/reject")
def reject_affiliate(affiliate_id: str, data: schemas.AffiliateRejectRequest, request: Request,
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.reject_affiliate(db, admin, affiliate_id, data, client_ip(request))


@router.post("/affiliates/{affiliate_id}/resend-invite")
def resend_affiliate_invite(affiliate_id: str, request: Request,
                            admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.resend_affiliate_invite(db, admin, affiliate_id, client_ip(request))


@router.patch("/affiliates/{affiliate_id}/demo-access")
def set_affiliate_demo_access(affiliate_id: str, data: schemas.AffiliateDemoAccessRequest, request: Request,
                              admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.set_affiliate_demo_access(db, admin, affiliate_id, data, client_ip(request))


@router.post("/affiliates/{affiliate_id}/payments", status_code=201)
def create_affiliate_payment(affiliate_id: str, data: schemas.AffiliatePaymentRequest, request: Request,
                             admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_affiliate_payment(db, admin, affiliate_id, data, client_ip(request))


@router.get("/affiliates/{affiliate_id}/payments")
def list_affiliate_payments(affiliate_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_affiliate_payments(db, affiliate_id)


# ---------- pacotes de crédito ----------
@router.get("/packages")
def list_packages(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_packages_admin(db)


@router.post("/packages", status_code=201)
def create_package(data: schemas.PackageRequest, request: Request,
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_package(db, admin, data, client_ip(request))


@router.patch("/packages/{package_id}")
def patch_package(package_id: str, data: schemas.PackagePatch, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_package(db, admin, package_id, data, client_ip(request))


# ---------- campanhas ----------
@router.get("/campaigns")
def list_campaigns(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_campaigns(db)


@router.post("/campaigns", status_code=201)
def create_campaign(data: schemas.CampaignRequest, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_campaign(db, admin, data, client_ip(request))


@router.patch("/campaigns/{campaign_id}")
def patch_campaign(campaign_id: str, data: schemas.CampaignPatch, request: Request,
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_campaign(db, admin, campaign_id, data, client_ip(request))


@router.delete("/campaigns/{campaign_id}", response_model=schemas.OkResponse)
def delete_campaign(campaign_id: str, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    service.delete_campaign(db, admin, campaign_id, client_ip(request))
    return schemas.OkResponse(detail="Campanha excluída.")


@router.get("/campaigns/{campaign_id}/dashboard")
def campaign_dashboard(campaign_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.campaign_dashboard(db, campaign_id)


@router.post("/campaigns/{campaign_id}/packages/{package_id}")
def add_campaign_package(campaign_id: str, package_id: str, request: Request,
                         admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.add_campaign_package(db, admin, campaign_id, package_id, client_ip(request))


@router.delete("/campaigns/{campaign_id}/packages/{package_id}")
def remove_campaign_package(campaign_id: str, package_id: str, request: Request,
                            admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.remove_campaign_package(db, admin, campaign_id, package_id, client_ip(request))


@router.post("/campaigns/{campaign_id}/coupons/{coupon_id}")
def add_campaign_coupon(campaign_id: str, coupon_id: str, request: Request,
                        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.add_campaign_coupon(db, admin, campaign_id, coupon_id, client_ip(request))


@router.delete("/campaigns/{campaign_id}/coupons/{coupon_id}")
def remove_campaign_coupon(campaign_id: str, coupon_id: str, request: Request,
                           admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.remove_campaign_coupon(db, admin, campaign_id, coupon_id, client_ip(request))


@router.post("/campaigns/{campaign_id}/affiliates/{affiliate_id}")
def add_campaign_affiliate(campaign_id: str, affiliate_id: str, request: Request,
                           admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.add_campaign_affiliate(db, admin, campaign_id, affiliate_id, client_ip(request))


@router.delete("/campaigns/{campaign_id}/affiliates/{affiliate_id}")
def remove_campaign_affiliate(campaign_id: str, affiliate_id: str, request: Request,
                              admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.remove_campaign_affiliate(db, admin, campaign_id, affiliate_id, client_ip(request))


# ---------- suporte ----------
@router.get("/support/tickets")
def list_tickets(status: str | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_tickets(db, status)


@router.patch("/support/tickets/{ticket_id}")
def patch_ticket(ticket_id: str, data: TicketPatch, request: Request,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_ticket(db, admin, ticket_id, data, client_ip(request))


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


@router.patch("/banners/{banner_id}")
def patch_banner(banner_id: str, data: schemas.BannerPatch, request: Request,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.patch_banner(db, admin, banner_id, data, client_ip(request))


@router.delete("/banners/{banner_id}", response_model=schemas.OkResponse)
def delete_banner(banner_id: str, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    service.delete_banner(db, admin, banner_id, client_ip(request))
    return schemas.OkResponse(detail="Banner excluído.")


# ---------- auditoria ----------
@router.get("/audit")
def audit_log(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_audit(db, limit, offset)
