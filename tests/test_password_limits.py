"""bcrypt accepts at most 72 BYTES. 72 characters can be up to 288 bytes (e.g. 'é' is 2 bytes),
and bcrypt 5 raises ValueError on longer input, which used to become a 500. Such passwords
must be refused cleanly as invalid input (422) instead."""

from app.models import UserRole

LONG_UTF8 = "é" * 72  # 72 characters, 144 bytes
FITS_UTF8 = "é" * 36  # 72 bytes exactly


def test_login_with_too_many_bytes_is_422_not_500(client):
    response = client.post("/auth/login", json={"email": "a@test.local", "password": LONG_UTF8})

    assert response.status_code == 422
    assert "72 bytes" in response.text
    assert LONG_UTF8 not in response.text  # the password is not echoed back


def test_create_user_with_too_many_bytes_is_422(client, make_user, auth_header):
    admin = make_user(UserRole.ADMIN, email="admin@test.local")
    body = {"name": "N", "email": "n@test.local", "password": LONG_UTF8, "role": "worker"}

    response = client.post("/users", json=body, headers=auth_header(admin))

    assert response.status_code == 422


def test_change_password_with_too_many_bytes_is_422(client, make_user, auth_header):
    admin = make_user(UserRole.ADMIN, email="admin@test.local")
    worker = make_user(UserRole.WORKER, email="worker@test.local")

    response = client.patch(
        f"/users/{worker.id}", json={"password": LONG_UTF8}, headers=auth_header(admin)
    )

    assert response.status_code == 422


def test_72_byte_non_ascii_password_works_end_to_end(client, make_user, auth_header):
    admin = make_user(UserRole.ADMIN, email="admin@test.local")
    body = {"name": "N", "email": "n@test.local", "password": FITS_UTF8, "role": "worker"}

    assert client.post("/users", json=body, headers=auth_header(admin)).status_code == 201
    login = client.post("/auth/login", json={"email": "n@test.local", "password": FITS_UTF8})
    assert login.status_code == 200
