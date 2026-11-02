import threading

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    Inventory,
    Location,
    MovementType,
    Product,
    ProductUnit,
    StockMovement,
    User,
    UserRole,
)
from app.services.movements import move, pick, receive
from app.services.stock import StockConflict

WAIT_SECONDS = 2


@pytest.fixture
def warehouse(db, make_user):
    user = make_user(role=UserRole.WORKER)
    product = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([product, a, b])
    db.commit()
    return {"user": user.id, "product": product.id, "a": a.id, "b": b.id}


def run_at_the_same_time(test_engine, *operations):
    """Run each operation in its own thread with its own database session.

    Every session pauses before its first write until all threads have read
    their data, so the threads always overlap. If one thread is blocked by a
    row lock, the others stop waiting after WAIT_SECONDS and carry on.
    """
    barrier = threading.Barrier(len(operations), timeout=WAIT_SECONDS)
    results = [None] * len(operations)

    def worker(index, operation):
        session = sessionmaker(bind=test_engine, autoflush=False)()
        original_flush = session.flush
        waited = False

        def flush_after_everyone_has_read(*args, **kwargs):
            nonlocal waited
            if not waited:
                waited = True
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return original_flush(*args, **kwargs)

        session.flush = flush_after_everyone_has_read
        try:
            operation(session)
            results[index] = "ok"
        except StockConflict:
            results[index] = "conflict"
        except Exception as error:  # noqa: BLE001  (any other error fails the test)
            results[index] = type(error).__name__
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i, op)) for i, op in enumerate(operations)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def stock(db, product_id, location_id):
    db.expire_all()
    return db.scalar(
        select(Inventory.quantity).where(
            Inventory.product_id == product_id, Inventory.location_id == location_id
        )
    )


def count_movements(db, type_):
    return db.scalar(
        select(func.count()).select_from(StockMovement).where(StockMovement.type == type_)
    )


def test_two_simultaneous_picks_of_the_last_item_only_one_succeeds(db, test_engine, warehouse):
    w = warehouse
    receive(db, db.get(User, w["user"]), w["product"], w["a"], quantity=1)

    def pick_one(session):
        pick(session, session.get(User, w["user"]), w["product"], w["a"], quantity=1)

    results = run_at_the_same_time(test_engine, pick_one, pick_one)

    assert sorted(results) == ["conflict", "ok"]
    assert stock(db, w["product"], w["a"]) == 0
    assert count_movements(db, MovementType.PICK) == 1


def test_opposite_moves_at_the_same_time_both_succeed(db, test_engine, warehouse):
    w = warehouse
    user = db.get(User, w["user"])
    receive(db, user, w["product"], w["a"], quantity=10)
    receive(db, user, w["product"], w["b"], quantity=10)

    def a_to_b(session):
        move(session, session.get(User, w["user"]), w["product"], w["a"], w["b"], quantity=3)

    def b_to_a(session):
        move(session, session.get(User, w["user"]), w["product"], w["b"], w["a"], quantity=5)

    results = run_at_the_same_time(test_engine, a_to_b, b_to_a)

    assert results == ["ok", "ok"]
    assert stock(db, w["product"], w["a"]) == 12
    assert stock(db, w["product"], w["b"]) == 8
