"""Promoções e campanhas — extensível por `type` + `config jsonb` (sem hardcode).
A promo "Só Paga se Acertar" é uma linha com type=refund_if_lose e max_odd=2.00.
Suporta futuramente cupons, cashback, indicação, bônus e campanhas sazonais."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import PromotionType


class Promotion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_promotions"

    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[PromotionType] = mapped_column(enum_type(PromotionType), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)   # regras específicas
    max_odd: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )


class PromotionParticipation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_promotion_participations"

    promotion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_promotions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)   # bet|analysis
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class Coupon(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_coupons"

    promotion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_promotions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    discount_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redemptions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Referral(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_referrals"

    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    referred_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    reward_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
