"""dados iniciais de monetização (migração pontual — não repetir; dali em diante tudo é
gerenciável pelo painel admin): 4 pacotes, 4 banners, 4 cupons, 1 campanha de exemplo

Revision ID: c4f7e2a891bd
Revises: 8b3d1a6f9c02
Create Date: 2026-07-14 12:30:00.000000
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4f7e2a891bd'
down_revision: Union[str, None] = '8b3d1a6f9c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    # ---------------- pacotes: UPDATE in-place se já existirem os 4 antigos de dev
    # (por posição/credits, preservando id -> pedidos históricos continuam válidos);
    # senão INSERT dos 4 novos.
    existing = bind.execute(sa.text(
        "SELECT id, credits FROM app_credit_packages ORDER BY sort_order, credits"
    )).fetchall()

    packages_spec = [
        # name, credits, price, bonus, badge, sort_order
        ("Pacote Inicial", 10, "10.00", 0, None, 0),
        ("Pacote Essencial", 20, "17.00", 0, "melhor_para_comecar", 1),
        ("Pacote Premium", 50, "35.00", 0, "mais_vendido", 2),
        ("Pacote Ultimate", 100, "50.00", 0, "melhor_custo_beneficio", 3),
    ]
    package_ids = []
    if len(existing) >= len(packages_spec):
        for row, (name, credits, price, bonus, badge, sort_order) in zip(existing, packages_spec):
            bind.execute(sa.text(
                "UPDATE app_credit_packages SET name=:name, credits=:credits, price_brl=:price, "
                "bonus_credits=:bonus, featured_badge=:badge, sort_order=:sort_order, status='ativo' "
                "WHERE id=:id"
            ), {"name": name, "credits": credits, "price": price, "bonus": bonus,
                "badge": badge, "sort_order": sort_order, "id": row.id})
            package_ids.append(row.id)
    else:
        for name, credits, price, bonus, badge, sort_order in packages_spec:
            pid = uuid.uuid4()
            bind.execute(sa.text(
                "INSERT INTO app_credit_packages "
                "(id, created_at, updated_at, name, credits, price_brl, bonus_credits, "
                "featured_badge, sort_order, status) VALUES "
                "(:id, :now, :now, :name, :credits, :price, :bonus, :badge, :sort_order, 'ativo')"
            ), {"id": pid, "now": now, "name": name, "credits": credits, "price": price,
                "bonus": bonus, "badge": badge, "sort_order": sort_order})
            package_ids.append(pid)
    pkg_by_name = dict(zip([p[0] for p in packages_spec], package_ids))

    # ---------------- banners
    banners_spec = [
        ("🔥 Economize mais comprando pacotes maiores!",
         "Quanto maior o pacote, menor o custo por crédito.", "promo", 0, 0),
        ("🎁 Convide amigos e ganhe créditos grátis!",
         "Você e seu amigo recebem 5 créditos quando ele utilizar seu código de indicação.", "promo", 0, 1),
        ("⚽ Mais créditos, mais análises!",
         "Aproveite o melhor custo-benefício adquirindo o pacote Ultimate.", "promo", 0, 2),
        ("🚀 Comece agora!",
         "Adquira seus créditos e tenha acesso às análises completas do ApostAInfo.", "info", 0, 3),
    ]
    banner_ids = []
    for title, body, btype, priority, sort_order in banners_spec:
        bid = uuid.uuid4()
        bind.execute(sa.text(
            "INSERT INTO app_banners (id, created_at, updated_at, title, body, type, active, "
            "priority, sort_order) VALUES (:id, :now, :now, :title, :body, :type, true, :priority, :sort_order)"
        ), {"id": bid, "now": now, "title": title, "body": body, "type": btype,
            "priority": priority, "sort_order": sort_order})
        banner_ids.append(bid)

    # ---------------- cupons (cada um com sua Promotion)
    coupons_spec = [
        # code, name, discount_type, discount_value, bonus_credits, min_purchase, first_purchase_only,
        # valid_to (dias a partir de agora, None=sem prazo), description
        ("BEMVINDO10", "Bem-vindo 10%", "percentage", "10.00", None, None, True, None,
         "10% de desconto — válido apenas na primeira compra."),
        ("PREMIUM15", "Premium 15%", "percentage", "15.00", None, "30.00", False, None,
         "15% de desconto para compras acima de R$ 30."),
        ("COPA20", "Copa do Mundo 20%", "percentage", "20.00", None, None, False, 30,
         "20% de desconto — campanha temporária da Copa do Mundo 2026."),
        ("BONUS10", "Bônus 10 créditos", "bonus_credits", None, 10, None, False, None,
         "Concede 10 créditos extras, sem desconto financeiro."),
    ]
    coupon_ids = {}
    for code, name, dtype, dvalue, bonus, min_purchase, first_only, valid_days, description in coupons_spec:
        promo_id = uuid.uuid4()
        bind.execute(sa.text(
            "INSERT INTO app_promotions (id, created_at, updated_at, code, name, type, active) "
            "VALUES (:id, :now, :now, :code, :name, 'coupon', true)"
        ), {"id": promo_id, "now": now, "code": f"PROMO_{code}", "name": name})
        coupon_id = uuid.uuid4()
        valid_to = (now + timedelta(days=valid_days)) if valid_days else None
        bind.execute(sa.text(
            "INSERT INTO app_coupons (id, created_at, updated_at, promotion_id, code, discount_type, "
            "discount_value, bonus_credits, min_purchase_brl, valid_to, first_purchase_only, "
            "description, redemptions, active) VALUES (:id, :now, :now, :promotion_id, :code, :dtype, "
            ":dvalue, :bonus, :min_purchase, :valid_to, :first_only, :description, 0, true)"
        ), {"id": coupon_id, "now": now, "promotion_id": promo_id, "code": code, "dtype": dtype,
            "dvalue": dvalue, "bonus": bonus, "min_purchase": min_purchase, "valid_to": valid_to,
            "first_only": first_only, "description": description})
        coupon_ids[code] = coupon_id

    # ---------------- campanha de exemplo: Copa do Mundo 2026 (banner 3 + cupom COPA20 +
    # pacotes Premium/Ultimate), prioridade alta
    campaign_id = uuid.uuid4()
    bind.execute(sa.text(
        "INSERT INTO app_campaigns (id, created_at, updated_at, name, banner_id, priority, active) "
        "VALUES (:id, :now, :now, 'Copa do Mundo 2026', :banner_id, 10, true)"
    ), {"id": campaign_id, "now": now, "banner_id": banner_ids[2]})
    bind.execute(sa.text(
        "INSERT INTO app_campaign_coupons (campaign_id, coupon_id) VALUES (:cid, :coid)"
    ), {"cid": campaign_id, "coid": coupon_ids["COPA20"]})
    for pkg_name in ("Pacote Premium", "Pacote Ultimate"):
        bind.execute(sa.text(
            "INSERT INTO app_campaign_packages (campaign_id, package_id) VALUES (:cid, :pid)"
        ), {"cid": campaign_id, "pid": pkg_by_name[pkg_name]})


def downgrade() -> None:
    # Migração de dados pontual — downgrade não tenta reverter cirurgicamente (arriscaria
    # apagar edições feitas depois pelo painel admin); só documenta a intenção.
    pass
