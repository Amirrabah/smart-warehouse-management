import pytest
from sqlalchemy import select

from app.models import Inventory, Location, Product, ProductUnit
from app.services.stock import StockConflict, decrease_stock, increase_stock


@pytest.fixture
def ids(db):
    product = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS)
    location = Location(code="A-01-01")
    db.add_all([product, location])
    db.commit()
    return product.id, location.id


def stock_in_db(db, product_id, location_id):
    db.expire_all()
    return db.scalar(
        select(Inventory.quantity).where(
            Inventory.product_id == product_id, Inventory.location_id == location_id
        )
    )


def test_increase_creates_inventory_row_when_none_exists(db, ids):
    new_quantity = increase_stock(db, *ids, quantity=10)
    db.commit()

    assert new_quantity == 10
    assert stock_in_db(db, *ids) == 10


def test_increase_adds_to_existing_stock(db, ids):
    increase_stock(db, *ids, quantity=10)
    new_quantity = increase_stock(db, *ids, quantity=5)
    db.commit()

    assert new_quantity == 15
    assert stock_in_db(db, *ids) == 15


def test_decrease_reduces_stock(db, ids):
    increase_stock(db, *ids, quantity=10)

    new_quantity = decrease_stock(db, *ids, quantity=3)
    db.commit()

    assert new_quantity == 7
    assert stock_in_db(db, *ids) == 7


def test_decrease_to_exactly_zero_keeps_the_row(db, ids):
    increase_stock(db, *ids, quantity=4)

    new_quantity = decrease_stock(db, *ids, quantity=4)
    db.commit()

    assert new_quantity == 0
    assert stock_in_db(db, *ids) == 0


def test_decrease_more_than_available_is_rejected_and_stock_unchanged(db, ids):
    increase_stock(db, *ids, quantity=3)
    db.commit()

    with pytest.raises(StockConflict, match="3 available, 5 requested"):
        decrease_stock(db, *ids, quantity=5)
    db.rollback()

    assert stock_in_db(db, *ids) == 3


def test_decrease_without_any_stock_row_is_rejected(db, ids):
    with pytest.raises(StockConflict, match="No stock"):
        decrease_stock(db, *ids, quantity=1)


def test_mixed_operations_in_one_transaction_use_the_latest_stock(db, ids):
    increase_stock(db, *ids, quantity=10)
    decrease_stock(db, *ids, quantity=3)
    increase_stock(db, *ids, quantity=5)

    new_quantity = decrease_stock(db, *ids, quantity=12)
    db.commit()

    assert new_quantity == 0
    assert stock_in_db(db, *ids) == 0
