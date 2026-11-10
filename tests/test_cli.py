"""The two command-line scripts: `py -m app.seed` and `py -m app.demo`."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import demo, seed
from app.models import User, UserRole


@pytest.fixture
def scripts_use_test_db(test_engine, monkeypatch):
    session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(seed, "SessionLocal", session)
    monkeypatch.setattr(demo, "SessionLocal", session)


def test_seed_needs_email_and_password(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with pytest.raises(SystemExit, match="ADMIN_EMAIL"):
        seed.main()


def test_seed_refuses_short_password(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@test.local")
    monkeypatch.setenv("ADMIN_PASSWORD", "short")

    with pytest.raises(SystemExit, match="8 characters"):
        seed.main()


def test_seed_creates_admin_once(db, scripts_use_test_db, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", " Boss@Test.local ")
    monkeypatch.setenv("ADMIN_PASSWORD", "long-enough-password")

    seed.main()
    seed.main()

    out = capsys.readouterr().out
    assert "Admin created: boss@test.local" in out
    assert "already exists" in out
    admin = db.scalar(select(User))
    assert (admin.email, admin.role) == ("boss@test.local", UserRole.ADMIN)


def test_demo_script_refuses_outside_demo_mode(db, scripts_use_test_db, make_user, monkeypatch):
    make_user(UserRole.ADMIN, email="real@test.local")
    monkeypatch.setattr(demo.settings, "demo_mode", False)

    with pytest.raises(SystemExit, match="DEMO_MODE"):
        demo.main()

    assert db.scalar(select(User.email)) == "real@test.local"  # nothing deleted


def test_demo_script_resets_in_demo_mode(db, scripts_use_test_db, monkeypatch, capsys):
    monkeypatch.setattr(demo.settings, "demo_mode", True)

    demo.main()

    assert "Demo data reset" in capsys.readouterr().out
    assert db.scalar(select(func.count()).select_from(User)) == len(demo.DEMO_USERS)


def test_seed_demo_if_empty_logs_when_it_loads(db, scripts_use_test_db, caplog):
    with caplog.at_level("INFO"):
        demo.seed_demo_if_empty()

    assert "Demo data loaded" in caplog.text
