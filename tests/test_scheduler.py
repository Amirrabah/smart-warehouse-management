import logging
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import app.main as main
from app import scheduler
from app.config import Settings
from app.models import Notification, Product, ProductUnit, UserRole
from app.scheduler import create_scheduler, nightly_low_stock_job


def test_job_runs_every_night_at_two_utc():
    job = create_scheduler().get_job("low_stock_check")

    noon = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert job.trigger.get_next_fire_time(None, noon) == datetime(2026, 1, 2, 2, 0, tzinfo=UTC)


def test_job_opens_its_own_session_and_runs_the_check(db, test_engine, make_user, monkeypatch):
    make_user(role=UserRole.ADMIN, email="admin@test.local")
    db.add(Product(sku="DRL-001", name="Drill", unit=ProductUnit.PCS, reorder_point=5))
    db.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", sessionmaker(bind=test_engine))

    nightly_low_stock_job()

    assert db.scalar(select(func.count()).select_from(Notification)) == 1


def test_job_failure_is_logged_not_raised(monkeypatch, caplog):
    def broken(db):
        raise RuntimeError("database is down")

    monkeypatch.setattr(scheduler, "run_low_stock_check", broken)

    with caplog.at_level(logging.ERROR):
        nightly_low_stock_job()  # must not raise, or the scheduler thread would log noise

    assert "Low-stock check failed" in caplog.text


class FakeScheduler:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def shutdown(self, wait=True):
        self.stopped = True


def test_scheduler_starts_and_stops_with_the_app_when_enabled(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr(main.settings, "scheduler_enabled", True)
    monkeypatch.setattr(main, "create_scheduler", lambda: fake)

    with TestClient(main.app):
        assert fake.started is True
    assert fake.stopped is True


def test_scheduler_stays_off_when_disabled(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr(main.settings, "scheduler_enabled", False)
    monkeypatch.setattr(main, "create_scheduler", lambda: fake)

    with TestClient(main.app):
        assert fake.started is False


def test_scheduler_is_off_unless_switched_on():
    assert Settings.model_fields["scheduler_enabled"].default is False
