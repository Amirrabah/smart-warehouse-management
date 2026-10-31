from app.models import UserRole
from app.seed import create_admin


def test_login_returns_token_for_valid_credentials(client, make_user):
    make_user(email="anna@test.local", password="password123")

    response = client.post(
        "/auth/login", json={"email": "anna@test.local", "password": "password123"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_email_is_case_insensitive(client, make_user):
    make_user(email="anna@test.local", password="password123")

    response = client.post(
        "/auth/login", json={"email": "  ANNA@Test.Local ", "password": "password123"}
    )

    assert response.status_code == 200


def test_login_wrong_password_returns_401(client, make_user):
    make_user(email="anna@test.local", password="password123")

    response = client.post(
        "/auth/login", json={"email": "anna@test.local", "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_gives_same_error_as_wrong_password(client):
    response = client.post(
        "/auth/login", json={"email": "nobody@test.local", "password": "password123"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_inactive_user_returns_401(client, make_user):
    make_user(email="anna@test.local", password="password123", is_active=False)

    response = client.post(
        "/auth/login", json={"email": "anna@test.local", "password": "password123"}
    )

    assert response.status_code == 401


def test_me_returns_current_user_without_password(client, make_user, auth_header):
    user = make_user(role=UserRole.PLANNER, name="Paula")

    response = client.get("/auth/me", headers=auth_header(user))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["name"] == "Paula"
    assert body["role"] == "planner"
    assert "password" not in body
    assert "password_hash" not in body


def test_me_without_token_returns_401(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_me_with_token_of_deactivated_user_returns_401(client, make_user, auth_header, db):
    user = make_user()
    headers = auth_header(user)
    user.is_active = False
    db.commit()

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401


def test_seed_create_admin_is_idempotent(db):
    assert create_admin(db, "Admin", "Admin@Test.Local", "password123") is True
    assert create_admin(db, "Admin", "admin@test.local", "password123") is False