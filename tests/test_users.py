import pytest

from app.models import UserRole

NON_ADMIN_ROLES = [UserRole.WORKER, UserRole.PLANNER]

NEW_USER = {
    "name": "New Worker",
    "email": "new.worker@test.local",
    "password": "password123",
    "role": "worker",
}


# --- Permissions: only admin may manage users -------------------------------


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_non_admin_cannot_list_users(client, make_user, auth_header, role):
    user = make_user(role=role)

    response = client.get("/users", headers=auth_header(user))

    assert response.status_code == 403


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_non_admin_cannot_create_users(client, make_user, auth_header, role):
    user = make_user(role=role)

    response = client.post("/users", json=NEW_USER, headers=auth_header(user))

    assert response.status_code == 403


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_non_admin_cannot_update_users(client, make_user, auth_header, role):
    user = make_user(role=role)

    response = client.patch(
        f"/users/{user.id}", json={"role": "admin"}, headers=auth_header(user)
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/users"), ("post", "/users"), ("patch", "/users/1")],
)
def test_user_endpoints_require_login(client, method, path):
    response = client.request(method.upper(), path, json={})

    assert response.status_code == 401


# --- Admin: list and create ---------------------------------------------------


def test_admin_can_list_users(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)
    make_user(role=UserRole.WORKER)

    response = client.get("/users", headers=auth_header(admin))

    assert response.status_code == 200
    users = response.json()
    assert [u["role"] for u in users] == ["admin", "worker"]
    assert all("password_hash" not in u for u in users)


def test_admin_can_create_user_who_can_then_log_in(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)

    response = client.post("/users", json=NEW_USER, headers=auth_header(admin))

    assert response.status_code == 201
    assert response.json()["email"] == "new.worker@test.local"
    login = client.post(
        "/auth/login",
        json={"email": NEW_USER["email"], "password": NEW_USER["password"]},
    )
    assert login.status_code == 200


def test_create_user_with_duplicate_email_returns_409(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)
    client.post("/users", json=NEW_USER, headers=auth_header(admin))

    duplicate = {**NEW_USER, "email": "NEW.Worker@test.local"}
    response = client.post("/users", json=duplicate, headers=auth_header(admin))

    assert response.status_code == 409


@pytest.mark.parametrize(
    "bad_field",
    [
        {"role": "superadmin"},
        {"password": "short"},
        {"email": "not-an-email"},
        {"name": ""},
    ],
)
def test_create_user_with_invalid_data_returns_422(
    client, make_user, auth_header, bad_field
):
    admin = make_user(role=UserRole.ADMIN)

    response = client.post(
        "/users", json={**NEW_USER, **bad_field}, headers=auth_header(admin)
    )

    assert response.status_code == 422


# --- Admin: update ------------------------------------------------------------


def test_admin_can_change_role_and_deactivate_other_user(
    client, make_user, auth_header
):
    admin = make_user(role=UserRole.ADMIN)
    worker = make_user(role=UserRole.WORKER)

    response = client.patch(
        f"/users/{worker.id}",
        json={"role": "planner", "is_active": False},
        headers=auth_header(admin),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "planner"
    assert response.json()["is_active"] is False


def test_patch_only_changes_fields_that_are_sent(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)
    worker = make_user(role=UserRole.WORKER, name="Old Name")

    response = client.patch(
        f"/users/{worker.id}", json={"name": "New Name"}, headers=auth_header(admin)
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert response.json()["role"] == "worker"
    assert response.json()["is_active"] is True


def test_admin_can_reset_password(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)
    worker = make_user(email="w@test.local", password="old-password")

    response = client.patch(
        f"/users/{worker.id}",
        json={"password": "new-password"},
        headers=auth_header(admin),
    )

    assert response.status_code == 200
    old = client.post("/auth/login", json={"email": "w@test.local", "password": "old-password"})
    new = client.post("/auth/login", json={"email": "w@test.local", "password": "new-password"})
    assert old.status_code == 401
    assert new.status_code == 200


@pytest.mark.parametrize("change", [{"role": "worker"}, {"is_active": False}])
def test_admin_cannot_demote_or_deactivate_self(
    client, make_user, auth_header, change
):
    admin = make_user(role=UserRole.ADMIN)

    response = client.patch(
        f"/users/{admin.id}", json=change, headers=auth_header(admin)
    )

    assert response.status_code == 409


def test_patch_email_is_not_allowed(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)
    worker = make_user(role=UserRole.WORKER)

    response = client.patch(
        f"/users/{worker.id}", json={"email": "x@test.local"}, headers=auth_header(admin)
    )

    assert response.status_code == 422


def test_patch_unknown_user_returns_404(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)

    response = client.patch(
        "/users/9999", json={"name": "Ghost"}, headers=auth_header(admin)
    )

    assert response.status_code == 404


def test_deactivated_user_is_blocked_immediately(client, make_user, auth_header):
    admin = make_user(role=UserRole.ADMIN)
    worker = make_user(role=UserRole.WORKER)
    worker_headers = auth_header(worker)

    client.patch(
        f"/users/{worker.id}", json={"is_active": False}, headers=auth_header(admin)
    )
    response = client.get("/auth/me", headers=worker_headers)

    assert response.status_code == 401