from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Location, MovementType, Product, StockMovement, User
from app.services.stock import StockConflict, decrease_stock, increase_stock


class NotFound(Exception):
    """A referenced product or location does not exist (turned into HTTP 404)."""


@dataclass
class MovementResult:
    movement: StockMovement
    inventory: dict[int, int]


@contextmanager
def _all_or_nothing(db: Session) -> Iterator[None]:
    try:
        yield
    except Exception:
        db.rollback()
        raise


def _check_product(db: Session, product_id: int) -> None:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFound("Product not found")
    if not product.is_active:
        raise StockConflict("Product is inactive")


def _check_location(db: Session, location_id: int) -> None:
    location = db.get(Location, location_id)
    if location is None:
        raise NotFound("Location not found")
    if not location.is_active:
        raise StockConflict("Location is inactive")


def _record(
    db: Session,
    user: User,
    type_: MovementType,
    product_id: int,
    quantity: int,
    inventory: dict[int, int],
    from_location_id: int | None = None,
    to_location_id: int | None = None,
    reason: str | None = None,
) -> MovementResult:
    movement = StockMovement(
        type=type_,
        product_id=product_id,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        quantity=quantity,
        reason=reason,
        user_id=user.id,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return MovementResult(movement=movement, inventory=inventory)


def receive(
    db: Session,
    user: User,
    product_id: int,
    to_location_id: int,
    quantity: int,
    reason: str | None = None,
) -> MovementResult:
    with _all_or_nothing(db):
        _check_product(db, product_id)
        _check_location(db, to_location_id)
        new_quantity = increase_stock(db, product_id, to_location_id, quantity)
        return _record(
            db,
            user,
            MovementType.RECEIVE,
            product_id,
            quantity,
            {to_location_id: new_quantity},
            to_location_id=to_location_id,
            reason=reason,
        )


def pick(
    db: Session,
    user: User,
    product_id: int,
    from_location_id: int,
    quantity: int,
    reason: str | None = None,
) -> MovementResult:
    with _all_or_nothing(db):
        _check_product(db, product_id)
        _check_location(db, from_location_id)
        new_quantity = decrease_stock(db, product_id, from_location_id, quantity)
        return _record(
            db,
            user,
            MovementType.PICK,
            product_id,
            quantity,
            {from_location_id: new_quantity},
            from_location_id=from_location_id,
            reason=reason,
        )


def move(
    db: Session,
    user: User,
    product_id: int,
    from_location_id: int,
    to_location_id: int,
    quantity: int,
    reason: str | None = None,
) -> MovementResult:
    with _all_or_nothing(db):
        _check_product(db, product_id)
        _check_location(db, from_location_id)
        _check_location(db, to_location_id)
        from_quantity = decrease_stock(db, product_id, from_location_id, quantity)
        to_quantity = increase_stock(db, product_id, to_location_id, quantity)
        return _record(
            db,
            user,
            MovementType.MOVE,
            product_id,
            quantity,
            {from_location_id: from_quantity, to_location_id: to_quantity},
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            reason=reason,
        )


def adjust(
    db: Session,
    user: User,
    product_id: int,
    location_id: int,
    quantity_change: int,
    reason: str,
) -> MovementResult:
    with _all_or_nothing(db):
        _check_product(db, product_id)
        _check_location(db, location_id)
        quantity = abs(quantity_change)
        if quantity_change < 0:
            new_quantity = decrease_stock(db, product_id, location_id, quantity)
            sides = {"from_location_id": location_id}
        else:
            new_quantity = increase_stock(db, product_id, location_id, quantity)
            sides = {"to_location_id": location_id}
        return _record(
            db,
            user,
            MovementType.ADJUST,
            product_id,
            quantity,
            {location_id: new_quantity},
            reason=reason,
            **sides,
        )
