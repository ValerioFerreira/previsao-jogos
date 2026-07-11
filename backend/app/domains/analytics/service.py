"""Instrumentação de eventos — chamada inline nos fluxos já existentes (signup, checkout,
análise). `track()` nunca lança: um evento perdido não pode derrubar o fluxo de negócio."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domains.analytics.models import Event

EVENT_TYPES = {
    "signup", "login", "checkout_started", "checkout_abandoned", "pix_generated",
    "pix_paid", "payment_failed", "coupon_applied", "referral_visit", "referral_signup",
    "referral_purchase", "credit_purchase", "credit_bonus", "credit_spent",
    "analysis_started", "analysis_finished",
}


def track(db: Session, event_type: str, user_id: uuid.UUID | None = None,
         session_id: str | None = None, **metadata) -> None:
    try:
        db.add(Event(event_type=event_type, user_id=user_id, session_id=session_id,
                     event_metadata=metadata or None))
    except Exception as e:
        print(f"[AVISO] analytics.track({event_type}): {e}")
