from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Inventory


class StockConflict(Exception):
    """The operation conflicts with the current stock (turned into HTTP 409)."""


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
        select(Inventory).where(
            Inventory.product_id == product_id, Inventory.location_id == location_id
        )
    )
    if row is None:
        raise StockConflict("No stock of this product at this location")
    if row.quantity < quantity:
        raise StockConflict(f"Insufficient stock: {row.quantity} available, {quantity} requested")
    row.quantity -= quantity
    db.flush()
    return row.quantity
