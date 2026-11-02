from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Inventory


class StockConflict(Exception):
    """The operation conflicts with the current stock (turned into HTTP 409)."""


def lock_stock_rows(db: Session, product_id: int, location_ids: list[int]) -> None:
    """Lock the inventory rows of several locations, always lowest location id first.

    Locking in one fixed order means two operations can never each hold the lock the
    other one needs, so they wait for each other instead of deadlocking.
    """
    db.execute(
        select(Inventory.id)
        .where(Inventory.product_id == product_id, Inventory.location_id.in_(location_ids))
        .order_by(Inventory.location_id)
        .with_for_update()
    )


def increase_stock(db: Session, product_id: int, location_id: int, quantity: int) -> int:
    statement = (
        insert(Inventory)
        .values(product_id=product_id, location_id=location_id, quantity=quantity)
        .on_conflict_do_update(
            index_elements=["product_id", "location_id"],
            set_={"quantity": Inventory.quantity + quantity, "updated_at": func.now()},
        )
        .returning(Inventory.quantity)
    )
    return db.execute(statement).scalar_one()


def decrease_stock(db: Session, product_id: int, location_id: int, quantity: int) -> int:
    row = db.scalar(
        select(Inventory)
        .where(Inventory.product_id == product_id, Inventory.location_id == location_id)
        .with_for_update()
    )
    if row is None:
        raise StockConflict("No stock of this product at this location")
    if row.quantity < quantity:
        raise StockConflict(f"Insufficient stock: {row.quantity} available, {quantity} requested")
    row.quantity -= quantity
    db.flush()
    return row.quantity
