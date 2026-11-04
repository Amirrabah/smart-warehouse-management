from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Inventory, Product
from app.pagination import PageParams
from app.schemas.stock import StockSummary

TOTAL = func.coalesce(func.sum(Inventory.quantity), 0)


def stock_summaries(
    db: Session,
    paging: PageParams,
    search: str | None = None,
    below_reorder: bool | None = None,
) -> tuple[list[StockSummary], int]:
    """Total stock per active product, summed over all locations.

    LEFT JOIN keeps products that have no inventory rows at all (total 0).
    """
    query = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.unit,
            Product.reorder_point,
            TOTAL.label("total"),
        )
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .where(Product.is_active)
        .group_by(Product.id)
    )
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)))
    if below_reorder is True:
        query = query.having(TOTAL < Product.reorder_point)
    elif below_reorder is False:
        query = query.having(TOTAL >= Product.reorder_point)

    total_count = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Product.sku).limit(paging.limit).offset(paging.offset))
    items = [
        StockSummary(
            product_id=row.id,
            sku=row.sku,
            name=row.name,
            unit=row.unit,
            reorder_point=row.reorder_point,
            total=row.total,
            below_reorder=row.total < row.reorder_point,
        )
        for row in rows
    ]
    return items, total_count
