"""Campanhas (orquestração de exibição) + scaffold de A/B testing."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.admin.models import Banner
from app.domains.campaigns.models import Campaign, Experiment, ExperimentVariant


def list_active_campaigns(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = db.execute(select(Campaign).where(
        Campaign.active.is_(True),
        or_(Campaign.starts_at.is_(None), Campaign.starts_at <= now),
        or_(Campaign.ends_at.is_(None), Campaign.ends_at >= now),
    ).order_by(Campaign.priority.desc(), Campaign.created_at.desc())).scalars().all()
    out = []
    for c in rows:
        banner = db.get(Banner, c.banner_id) if c.banner_id else None
        out.append({
            "id": str(c.id), "name": c.name, "priority": c.priority,
            "banner": {"title": banner.title, "body": banner.body, "type": banner.type} if banner else None,
        })
    return out


def assign_variant(db: Session, experiment_key: str, user_id: uuid.UUID) -> str | None:
    """Seleção determinística por hash — mesmo usuário sempre cai na mesma variante,
    proporcional ao peso de cada uma. Retorna None se o experimento não existe/inativo."""
    exp = db.execute(select(Experiment).where(
        Experiment.key == experiment_key, Experiment.active.is_(True))).scalar_one_or_none()
    if exp is None:
        return None
    variants = db.execute(select(ExperimentVariant).where(
        ExperimentVariant.experiment_id == exp.id).order_by(ExperimentVariant.key)).scalars().all()
    if not variants:
        return None
    total_weight = sum(v.weight for v in variants) or 1
    h = int(hashlib.sha256(f"{experiment_key}:{user_id}".encode()).hexdigest(), 16)
    bucket = h % total_weight
    acc = 0
    for v in variants:
        acc += v.weight
        if bucket < acc:
            return v.key
    return variants[-1].key
