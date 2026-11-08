from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Numeric, case, cast, func, select
from sqlalchemy.orm import Session

from app.models import Inventory, MovementType, Product, StockMovement
from app.pagination import PageParams
from app.schemas.planner import PlannerRow

USAGE_WINDOW_DAYS = 30

PlannerSort = Literal["days_left", "sku"]


def planner_rows(
    db: Session,
    paging: PageParams,
    only_below: bool = False,
    sort: PlannerSort = "days_left",
) -> tuple[list[PlannerRow], int]:
    """Stock, usage and days left per active product.

    Usage = quantity picked in the last 30 days. Receive, move and adjust are not usage.
    days_left = total / average daily usage, or NULL when the product was not picked.
    """
    since = datetime.now(UTC) - timedelta(days=USAGE_WINDOW_DAYS)

    # Two separate subqueries, each summed on its own. Joining inventory AND movements
    # directly to products would multiply rows and make both sums wrong.
    stock = (
        select(Inventory.product_id, func.sum(Inventory.quantity).label("total"))
        .group_by(Inventory.product_id)
        .subquery()
    )
    usage = (
        select(StockMovement.product_id, func.sum(StockMovement.quantity).label("used"))
        .where(StockMovement.type == MovementType.PICK, StockMovement.created_at >= since)
        .group_by(StockMovement.product_id)
        .subquery()
    )

    total = func.coalesce(stock.c.total, 0)
    used = func.coalesce(usage.c.used, 0)
    days_left = case(
        (used > 0, cast(total, Numeric) * USAGE_WINDOW_DAYS / used),
        else_=None,
    )

    query = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.unit,
            Product.reorder_point,
            total.label("total"),
            used.label("used"),
            days_left.label("days_left"),
        )
        .outerjoin(stock, stock.c.product_id == Product.id)
        .outerjoin(usage, usage.c.product_id == Product.id)
        .where(Product.is_active)
    )
    if only_below:
        query = query.where(total < Product.reorder_point)

    if sort == "days_left":
        query = query.order_by(days_left.asc().nulls_last(), Product.sku)
    else:
        query = query.order_by(Product.sku)

    total_count = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.execute(query.limit(paging.limit).offset(paging.offset))
    items = [
        PlannerRow(
            product_id=row.id,
            sku=row.sku,
            name=row.name,
            unit=row.unit,
            reorder_point=row.reorder_point,
            total=row.total,
            below_reorder=row.total < row.reorder_point,
            used_last_30_days=row.used,
            avg_daily_usage=round(row.used / USAGE_WINDOW_DAYS, 2),
            days_left=None if row.days_left is None else round(float(row.days_left), 1),
        )
        for row in rows
    ]
    return items, total_count
