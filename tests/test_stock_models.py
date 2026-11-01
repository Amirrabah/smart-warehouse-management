import pytest
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


@pytest.fixture
def setup(db, make_user):
    user = make_user(role=UserRole.WORKER)
    product = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([product, a, b])
    db.commit()
    return {"user": user, "product": product, "a": a, "b": b}


def assert_rejected(db, row):
    db.add(row)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- inventory -----------------------------------------------------------------


def test_inventory_quantity_cannot_be_negative(db, setup):
    row = Inventory(product_id=setup["product"].id, location_id=setup["a"].id, quantity=-1)

    assert_rejected(db, row)


def test_inventory_has_one_row_per_product_and_location(db, setup):
    db.add(Inventory(product_id=setup["product"].id, location_id=setup["a"].id, quantity=5))
    db.commit()

    duplicate = Inventory(product_id=setup["product"].id, location_id=setup["a"].id, quantity=3)

    assert_rejected(db, duplicate)


def test_inventory_quantity_defaults_to_zero(db, setup):
    row = Inventory(product_id=setup["product"].id, location_id=setup["a"].id)
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.quantity == 0
    assert row.updated_at is not None


# --- stock movements -------------------------------------------------------------


def movement(setup, type_, from_=None, to=None, quantity=5, reason=None):
    return StockMovement(
        type=type_,
        product_id=setup["product"].id,
        from_location_id=setup[from_].id if from_ else None,
        to_location_id=setup[to].id if to else None,
        quantity=quantity,
        reason=reason,
        user_id=setup["user"].id,
    )


@pytest.mark.parametrize(
    ("type_", "from_", "to", "reason"),
    [
        (MovementType.RECEIVE, None, "a", None),
        (MovementType.PICK, "a", None, None),
        (MovementType.MOVE, "a", "b", None),
        (MovementType.ADJUST, "a", None, "Counted 2 fewer"),
        (MovementType.ADJUST, None, "a", "Found extra box"),
    ],
)
def test_valid_movements_are_accepted(db, setup, type_, from_, to, reason):
    row = movement(setup, type_, from_, to, reason=reason)
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.id is not None
    assert row.created_at is not None


@pytest.mark.parametrize(
    ("type_", "from_", "to", "reason"),
    [
        (MovementType.RECEIVE, "a", "b", None),  # receive has no from
        (MovementType.RECEIVE, None, None, None),  # receive needs a to
        (MovementType.PICK, "a", "b", None),  # pick has no to
        (MovementType.PICK, None, None, None),  # pick needs a from
        (MovementType.MOVE, "a", None, None),  # move needs both
        (MovementType.MOVE, "a", "a", None),  # move to the same location
        (MovementType.ADJUST, "a", None, None),  # adjust needs a reason
        (MovementType.ADJUST, "a", None, "   "),  # blank reason
        (MovementType.ADJUST, "a", "b", "Both sides"),  # adjust touches one location
    ],
)
def test_invalid_movement_directions_are_rejected(db, setup, type_, from_, to, reason):
    assert_rejected(db, movement(setup, type_, from_, to, reason=reason))


@pytest.mark.parametrize("quantity", [0, -5])
def test_movement_quantity_must_be_positive(db, setup, quantity):
    assert_rejected(db, movement(setup, MovementType.RECEIVE, to="a", quantity=quantity))
