"""Campanha = entidade guarda-chuva que amarra banner + período + pacotes participantes +
cupons vinculados + afiliados participantes + prioridade de exibição, para não espalhar
configuração de promoção entre vários módulos soltos. Promotion/Coupon continuam sendo os
mecanismos de benefício; Campaign é só a camada de orquestração/exibição.

Inclui também a estrutura mínima de A/B testing (Experiment/ExperimentVariant) — sem
motor de decisão completo, só o suficiente para ligar testes reais depois sem migração."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_campaigns"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    banner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_banners.id", ondelete="SET NULL"), nullable=True
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CampaignPackage(Base):
    __tablename__ = "app_campaign_packages"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_credit_packages.id", ondelete="CASCADE"), primary_key=True
    )


class CampaignCoupon(Base):
    __tablename__ = "app_campaign_coupons"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    coupon_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_coupons.id", ondelete="CASCADE"), primary_key=True
    )


class CampaignAffiliate(Base):
    __tablename__ = "app_campaign_affiliates"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), primary_key=True
    )


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_experiments"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ExperimentVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_experiment_variants"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_experiments.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
