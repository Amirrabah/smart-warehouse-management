from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Inventory, Location, Product
from app.pagination import PageParams
from app.schemas.stock import LocationQuantity, ProductStock, ShelfItem, StockSummary
from app.services.movements import NotFound

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


def product_stock(db: Session, product_id: int) -> ProductStock:
    """One product with its stock per location. Empty rows (quantity 0) are left out."""
    product = db.get(Product, product_id)
    if product is None:
        raise NotFound("Product not found")
    rows = db.execute(
        select(Location.id, Location.code, Inventory.quantity)
        .join(Location, Location.id == Inventory.location_id)
        .where(Inventory.product_id == product_id, Inventory.quantity > 0)
        .order_by(Location.code)
    )
    locations = [
        LocationQuantity(location_id=row.id, code=row.code, quantity=row.quantity) for row in rows
    ]
    total = sum(location.quantity for location in locations)
    return ProductStock(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        unit=product.unit,
        reorder_point=product.reorder_point,
        total=total,
        below_reorder=total < product.reorder_point,
        locations=locations,
    )


def location_stock(db: Session, location_id: int) -> list[ShelfItem]:
    """Every product on one shelf (quantity > 0), sorted by SKU. Used when counting stock."""
    if db.get(Location, location_id) is None:
        raise NotFound("Location not found")
    rows = db.execute(
        select(Product.id, Product.sku, Product.name, Product.unit, Inventory.quantity)
        .join(Product, Product.id == Inventory.product_id)
        .where(Inventory.location_id == location_id, Inventory.quantity > 0)
        .order_by(Product.sku)
    )
    return [
        ShelfItem(
            product_id=row.id,
            sku=row.sku,
            name=row.name,
            unit=row.unit,
            quantity=row.quantity,
        )
        for row in rows
    ]
