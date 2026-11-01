import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Inventory,
    Location,
    MovementType,
    Product,
    ProductUnit,
    StockMovement,
    UserRole,
)
from app.services.movements import NotFound, adjust, move, pick, receive
from app.services.stock import StockConflict


@pytest.fixture
def ctx(db, make_user):
    user = make_user(role=UserRole.WORKER)
    product = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([product, a, b])
    db.commit()
    return {"db": db, "user": user, "product": product.id, "a": a.id, "b": b.id}


def stock(db, product_id, location_id):
    db.expire_all()
    return db.scalar(
        select(Inventory.quantity).where(
            Inventory.product_id == product_id, Inventory.location_id == location_id
        )
    )


def movement_count(db):
    return db.scalar(select(func.count()).select_from(StockMovement))


# --- receive -------------------------------------------------------------------


def test_receive_adds_stock_and_records_movement(ctx):
    db = ctx["db"]

    result = receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=200)

    assert result.inventory == {ctx["a"]: 200}
    assert stock(db, ctx["product"], ctx["a"]) == 200
    m = result.movement
    assert m.type == MovementType.RECEIVE
    assert (m.from_location_id, m.to_location_id) == (None, ctx["a"])
    assert m.quantity == 200
    assert m.user_id == ctx["user"].id


def test_receive_twice_adds_up(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=200)

    result = receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=50)

    assert result.inventory == {ctx["a"]: 250}
    assert movement_count(db) == 2


# --- pick ----------------------------------------------------------------------


def test_pick_removes_stock_and_records_movement(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=200)

    result = pick(db, ctx["user"], ctx["product"], ctx["a"], quantity=5)

    assert result.inventory == {ctx["a"]: 195}
    assert result.movement.type == MovementType.PICK
    assert (result.movement.from_location_id, result.movement.to_location_id) == (ctx["a"], None)


def test_pick_more_than_available_changes_nothing(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=3)

    with pytest.raises(StockConflict):
        pick(db, ctx["user"], ctx["product"], ctx["a"], quantity=5)

    assert stock(db, ctx["product"], ctx["a"]) == 3
    assert movement_count(db) == 1


# --- move ----------------------------------------------------------------------


def test_move_transfers_stock_between_locations(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=100)

    result = move(db, ctx["user"], ctx["product"], ctx["a"], ctx["b"], quantity=40)

    assert result.inventory == {ctx["a"]: 60, ctx["b"]: 40}
    assert stock(db, ctx["product"], ctx["a"]) == 60
    assert stock(db, ctx["product"], ctx["b"]) == 40
    assert result.movement.type == MovementType.MOVE


def test_failed_move_changes_neither_location(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=10)
    receive(db, ctx["user"], ctx["product"], ctx["b"], quantity=5)

    with pytest.raises(StockConflict):
        move(db, ctx["user"], ctx["product"], ctx["a"], ctx["b"], quantity=11)

    assert stock(db, ctx["product"], ctx["a"]) == 10
    assert stock(db, ctx["product"], ctx["b"]) == 5
    assert movement_count(db) == 2


# --- adjust --------------------------------------------------------------------


def test_negative_adjust_removes_stock_with_reason(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=10)

    result = adjust(db, ctx["user"], ctx["product"], ctx["a"], -2, reason="Counted 2 fewer")

    assert result.inventory == {ctx["a"]: 8}
    m = result.movement
    assert m.type == MovementType.ADJUST
    assert (m.from_location_id, m.to_location_id, m.quantity) == (ctx["a"], None, 2)
    assert m.reason == "Counted 2 fewer"


def test_positive_adjust_adds_stock(ctx):
    db = ctx["db"]

    result = adjust(db, ctx["user"], ctx["product"], ctx["a"], 3, reason="Found a box")

    assert result.inventory == {ctx["a"]: 3}
    assert (result.movement.from_location_id, result.movement.to_location_id) == (None, ctx["a"])
    assert result.movement.quantity == 3


def test_adjust_below_zero_is_rejected(ctx):
    db = ctx["db"]
    receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=1)

    with pytest.raises(StockConflict):
        adjust(db, ctx["user"], ctx["product"], ctx["a"], -2, reason="Recount")

    assert stock(db, ctx["product"], ctx["a"]) == 1


# --- inactive and unknown --------------------------------------------------------


def test_inactive_product_cannot_be_moved(ctx):
    db = ctx["db"]
    db.get(Product, ctx["product"]).is_active = False
    db.commit()

    with pytest.raises(StockConflict, match="Product is inactive"):
        receive(db, ctx["user"], ctx["product"], ctx["a"], quantity=1)

    assert movement_count(db) == 0


def test_inactive_location_cannot_receive(ctx):
    db = ctx["db"]
    db.get(Location, ctx["b"]).is_active = False
    db.commit()

    with pytest.raises(StockConflict, match="Location is inactive"):
        receive(db, ctx["user"], ctx["product"], ctx["b"], quantity=1)


@pytest.mark.parametrize("missing", ["product", "location"])
def test_unknown_product_or_location_is_not_found(ctx, missing):
    db = ctx["db"]
    product_id = 9999 if missing == "product" else ctx["product"]
    location_id = 9999 if missing == "location" else ctx["a"]

    with pytest.raises(NotFound):
        receive(db, ctx["user"], product_id, location_id, quantity=1)


# --- all or nothing ------------------------------------------------------------


def test_database_rejection_rolls_back_the_stock_change(ctx):
    db = ctx["db"]

    with pytest.raises(IntegrityError):
        adjust(db, ctx["user"], ctx["product"], ctx["a"], 5, reason="   ")

    assert stock(db, ctx["product"], ctx["a"]) is None
    assert movement_count(db) == 0
