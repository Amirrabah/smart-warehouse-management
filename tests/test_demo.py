"""Demo mode: realistic data with history, one login per role, reset every night."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import app.main as main
from app import scheduler
from app.config import settings
from app.demo import DEMO_PASSWORD, DEMO_USERS, ensure_demo_data, reset_demo
from app.models import (
    Inventory,
    Location,
    MovementType,
    Notification,
    Product,
    ProductUnit,
    StockMovement,
    User,
    UserRole,
)
from app.scheduler import create_scheduler, nightly_demo_reset_job
from app.security import verify_password


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- The demo data --------------------------------------------------------


def test_reset_creates_one_active_user_per_role_with_the_demo_password(db):
    reset_demo(db)

    users = db.scalars(select(User).order_by(User.id)).all()
    assert {user.role for user in users} == {UserRole.ADMIN, UserRole.WORKER, UserRole.PLANNER}
    assert [user.email for user in users] == [account.email for account in DEMO_USERS]
    assert all(user.is_active for user in users)
    assert all(verify_password(DEMO_PASSWORD, user.password_hash) for user in users)


def test_reset_creates_products_locations_and_stock(db):
    reset_demo(db)

    assert count(db, Product) >= 10
    assert count(db, Location) >= 8
    assert db.scalar(select(func.sum(Inventory.quantity))) > 0


def test_reset_spreads_movements_over_the_last_month(db):
    reset_demo(db)

    times = db.scalars(select(StockMovement.created_at)).all()
    now = datetime.now(UTC)
    assert len(times) >= 100
    assert min(times) < now - timedelta(days=25)
    assert max(times) <= now
    types = set(db.scalars(select(StockMovement.type)).all())
    assert types == set(MovementType)  # receive, pick, move and adjust all appear


def test_inventory_matches_the_movement_history(db):
    """The demo goes through the real services, so stock and history always agree."""
    reset_demo(db)

    for product in db.scalars(select(Product)):
        stored = db.scalar(
            select(func.coalesce(func.sum(Inventory.quantity), 0)).where(
                Inventory.product_id == product.id
            )
        )
        moved = 0
        for m in db.scalars(select(StockMovement).where(StockMovement.product_id == product.id)):
            if m.type == MovementType.RECEIVE or (
                m.type == MovementType.ADJUST and m.to_location_id is not None
            ):
                moved += m.quantity
            elif m.type == MovementType.PICK or (
                m.type == MovementType.ADJUST and m.from_location_id is not None
            ):
                moved -= m.quantity
        assert stored == moved, product.sku


def test_planner_has_something_to_show(client, db, auth_header):
    reset_demo(db)
    planner = db.scalar(select(User).where(User.role == UserRole.PLANNER))

    rows = client.get("/planner?limit=200", headers=auth_header(planner)).json()["items"]

    assert any(row["below_reorder"] for row in rows)
    assert any(not row["below_reorder"] for row in rows)
    assert sum(row["days_left"] is not None for row in rows) >= 5


def test_admin_and_planner_have_a_low_stock_notification(db):
    reset_demo(db)

    recipients = db.scalars(select(User.role).join(Notification)).all()
    assert sorted(recipients) == sorted([UserRole.ADMIN, UserRole.PLANNER])


def test_reset_replaces_everything_and_can_run_again(db, make_user):
    make_user(UserRole.ADMIN, email="someone@test.local")
    db.add(Product(sku="OLD-1", name="Old", unit=ProductUnit.PCS))
    db.commit()

    reset_demo(db)
    first = (count(db, User), count(db, Product), count(db, StockMovement))
    reset_demo(db)
    second = (count(db, User), count(db, Product), count(db, StockMovement))

    assert first == second
    assert db.scalar(select(Product).where(Product.sku == "OLD-1")) is None
    assert db.scalar(select(User).where(User.email == "someone@test.local")) is None


def test_ensure_seeds_an_empty_database(db):
    assert ensure_demo_data(db) is True
    assert count(db, User) == len(DEMO_USERS)


def test_ensure_leaves_existing_data_alone(db, make_user):
    make_user(UserRole.ADMIN, email="real@test.local")

    assert ensure_demo_data(db) is False
    assert count(db, User) == 1


# --- Demo logins on the login page ----------------------------------------


def test_no_demo_accounts_when_demo_mode_is_off(client):
    # 200 with an empty list (not 404), so the login page can ask without a console error.
    response = client.get("/auth/demo-accounts")

    assert response.status_code == 200
    assert response.json() == []


def test_demo_accounts_are_listed_in_demo_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)

    accounts = client.get("/auth/demo-accounts").json()

    assert [a["role"] for a in accounts] == ["admin", "worker", "planner"]
    assert all(a["password"] == DEMO_PASSWORD for a in accounts)
    assert [a["email"] for a in accounts] == [u.email for u in DEMO_USERS]


def test_demo_accounts_can_log_in(client, db, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    reset_demo(db)

    for account in client.get("/auth/demo-accounts").json():
        response = client.post(
            "/auth/login", json={"email": account["email"], "password": account["password"]}
        )
        assert response.status_code == 200, account["email"]


# --- Nightly reset and startup --------------------------------------------


def test_no_demo_reset_job_outside_demo_mode():
    assert create_scheduler().get_job("demo_reset") is None


def test_demo_reset_job_runs_every_night_at_three_utc(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "demo_mode", True)

    job = create_scheduler().get_job("demo_reset")

    noon = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert job.trigger.get_next_fire_time(None, noon) == datetime(2026, 1, 2, 3, 0, tzinfo=UTC)


def test_demo_reset_job_uses_its_own_session(db, test_engine, monkeypatch):
    monkeypatch.setattr(scheduler, "SessionLocal", sessionmaker(bind=test_engine))

    nightly_demo_reset_job()

    assert count(db, User) == len(DEMO_USERS)


def test_demo_reset_job_failure_is_logged_not_raised(monkeypatch, caplog):
    def broken(db):
        raise RuntimeError("database is down")

    monkeypatch.setattr(scheduler, "reset_demo", broken)

    nightly_demo_reset_job()

    assert "Demo reset failed" in caplog.text


@pytest.mark.parametrize("demo_mode", [True, False])
def test_app_start_seeds_demo_data_only_in_demo_mode(monkeypatch, demo_mode):
    calls = []
    monkeypatch.setattr(main.settings, "demo_mode", demo_mode)
    monkeypatch.setattr(main, "seed_demo_if_empty", lambda: calls.append(True))

    with TestClient(main.app):
        pass

    assert calls == ([True] if demo_mode else [])
