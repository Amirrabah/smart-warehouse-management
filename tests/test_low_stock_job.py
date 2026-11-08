import pytest
from sqlalchemy import func, select

from app.models import Inventory, Location, Notification, Product, ProductUnit, UserRole
from app.services import alerts
from app.services.alerts import run_low_stock_check


@pytest.fixture
def warehouse(db, make_user):
    """cable is fine, drill and glue are low, tape has reorder point 0, old is inactive."""
    admin = make_user(role=UserRole.ADMIN, email="admin@test.local")
    planner = make_user(role=UserRole.PLANNER, email="planner@test.local")
    make_user(role=UserRole.WORKER, email="worker@test.local")
    make_user(role=UserRole.PLANNER, email="gone@test.local", is_active=False)

    a = Location(code="A-01-01")
    products = {
        "cable": Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS, reorder_point=10),
        "drill": Product(sku="DRL-001", name="Drill", unit=ProductUnit.PCS, reorder_point=5),
        "glue": Product(sku="GLU-001", name="Glue", unit=ProductUnit.BOX, reorder_point=3),
        "tape": Product(sku="TAP-001", name="Tape", unit=ProductUnit.PCS, reorder_point=0),
        "old": Product(
            sku="OLD-001", name="Old", unit=ProductUnit.PCS, reorder_point=9, is_active=False
        ),
    }
    db.add_all([a, *products.values()])
    db.flush()
    stock = {"cable": 15, "drill": 2}  # glue, tape and old have no stock at all
    for key, quantity in stock.items():
        db.add(Inventory(product_id=products[key].id, location_id=a.id, quantity=quantity))
    db.commit()
    return {"admin": admin, "planner": planner, "a": a, **products}


def set_stock(db, product, location, quantity):
    row = db.scalar(
        select(Inventory).where(
            Inventory.product_id == product.id, Inventory.location_id == location.id
        )
    )
    row.quantity = quantity
    db.commit()


def notifications(db):
    return db.scalars(select(Notification).order_by(Notification.id)).all()


def alerted_skus(db):
    db.expire_all()
    return sorted(db.scalars(select(Product.sku).where(Product.low_stock_alerted)).all())


# --- the first night --------------------------------------------------------------


def test_one_notification_per_active_admin_and_planner(db, warehouse):
    run_low_stock_check(db)

    recipients = sorted(n.user_id for n in notifications(db))
    assert recipients == sorted([warehouse["admin"].id, warehouse["planner"].id])


def test_notification_lists_every_low_product(db, warehouse):
    run_low_stock_check(db)

    notification = notifications(db)[0]
    assert notification.title == "Low stock: 2 products"
    assert notification.body == (
        "DRL-001 Drill: 2 left (reorder point 5)\nGLU-001 Glue: 0 left (reorder point 3)"
    )
    assert notification.read_at is None


def test_low_products_are_flagged(db, warehouse):
    run_low_stock_check(db)

    assert alerted_skus(db) == ["DRL-001", "GLU-001"]


def test_result_says_what_happened(db, warehouse):
    result = run_low_stock_check(db)

    assert result.alerted == ["DRL-001", "GLU-001"]
    assert result.restored == []
    assert result.notifications == 2


# --- no duplicates, and alert again after a restock -------------------------------


def test_second_run_creates_no_duplicates(db, warehouse):
    run_low_stock_check(db)
    result = run_low_stock_check(db)

    assert result.alerted == []
    assert len(notifications(db)) == 2


def test_restock_clears_the_flag_without_notifying(db, warehouse):
    run_low_stock_check(db)
    set_stock(db, warehouse["drill"], warehouse["a"], 5)  # exactly the reorder point = ok

    result = run_low_stock_check(db)

    assert result.restored == ["DRL-001"]
    assert alerted_skus(db) == ["GLU-001"]
    assert len(notifications(db)) == 2


def test_low_again_after_restock_alerts_again(db, warehouse):
    run_low_stock_check(db)
    set_stock(db, warehouse["drill"], warehouse["a"], 50)
    run_low_stock_check(db)
    set_stock(db, warehouse["drill"], warehouse["a"], 1)

    run_low_stock_check(db)

    newest = notifications(db)[-1]
    assert newest.title == "Low stock: 1 product"
    assert newest.body == "DRL-001 Drill: 1 left (reorder point 5)"
    assert len(notifications(db)) == 4


# --- edge cases -------------------------------------------------------------------


def test_nothing_low_means_no_notifications(db, warehouse):
    set_stock(db, warehouse["drill"], warehouse["a"], 100)
    warehouse["glue"].reorder_point = 0
    db.commit()

    result = run_low_stock_check(db)

    assert result.notifications == 0
    assert notifications(db) == []


def test_inactive_products_are_ignored(db, warehouse):
    run_low_stock_check(db)

    assert "OLD-001" not in alerted_skus(db)
    assert "OLD-001" not in notifications(db)[0].body


def test_without_recipients_products_stay_unflagged(db, warehouse):
    """If nobody can be told, do not mark the products as alerted, or the alert is lost."""
    warehouse["admin"].is_active = False
    warehouse["planner"].is_active = False
    db.commit()

    run_low_stock_check(db)

    assert notifications(db) == []
    assert alerted_skus(db) == []


def test_failure_saves_nothing(db, warehouse, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(alerts, "_message", broken)

    with pytest.raises(RuntimeError):
        run_low_stock_check(db)

    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    assert alerted_skus(db) == []
