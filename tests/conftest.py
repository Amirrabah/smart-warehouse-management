import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole
from app.security import create_access_token, hash_password

_dev_url = make_url(settings.database_url)
TEST_DB_URL = _dev_url.set(database=f"{_dev_url.database}_test")


def _ensure_test_database_exists() -> None:
    admin_engine = create_engine(
        TEST_DB_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_URL.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def test_engine():
    _ensure_test_database_exists()
    engine = create_engine(TEST_DB_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(test_engine):
    session = sessionmaker(bind=test_engine, autoflush=False)()
    yield session
    session.close()
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with test_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db):
    def _make_user(
        role: UserRole = UserRole.WORKER,
        email: str | None = None,
        password: str = "password123",
        name: str = "Test User",
        is_active: bool = True,
    ) -> User:
        user = User(
            name=name,
            email=email or f"{role.value}@test.local",
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make_user


@pytest.fixture
def auth_header():
    def _auth_header(user: User) -> dict:
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    return _auth_header