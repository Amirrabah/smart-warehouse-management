import pytest

from app.models import UserRole


@pytest.fixture
def admin_headers(make_user, auth_header):
    return auth_header(make_user(role=UserRole.ADMIN, email="admin@test.local"))


@pytest.fixture
def location(client, admin_headers):
    response = client.post(
        "/locations",
        json={"code": "A-01-03", "description": "Aisle A, rack 1"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


# --- Permissions --------------------------------------------------------------


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.PLANNER])
def test_only_admin_can_create_locations(client, make_user, auth_header, role):
    user = make_user(role=role)

    response = client.post("/locations", json={"code": "B-02-01"}, headers=auth_header(user))

    assert response.status_code == 403


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.PLANNER])
def test_only_admin_can_edit_locations(client, make_user, auth_header, location, role):
    user = make_user(role=role)

    response = client.patch(
        f"/locations/{location['id']}", json={"is_active": False}, headers=auth_header(user)
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", list(UserRole))
def test_all_roles_can_view_locations(client, make_user, auth_header, location, role):
    headers = auth_header(make_user(role=role, email=f"{role.value}-view@test.local"))

    assert client.get("/locations", headers=headers).status_code == 200
    assert client.get(f"/locations/{location['id']}", headers=headers).status_code == 200


def test_locations_require_login(client):
    assert client.get("/locations").status_code == 401


# --- Create and validation -----------------------------------------------------


def test_create_location_normalises_code(client, admin_headers):
    response = client.post("/locations", json={"code": " b-02-01 "}, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["code"] == "B-02-01"
    assert response.json()["description"] is None
    assert response.json()["is_active"] is True


@pytest.mark.parametrize("bad_code", ["A-1-3", "AA-01-03", "A-01-03-X", "A0103", "1-01-03", ""])
def test_invalid_location_code_returns_422(client, admin_headers, bad_code):
    response = client.post("/locations", json={"code": bad_code}, headers=admin_headers)

    assert response.status_code == 422


def test_duplicate_location_code_returns_409(client, admin_headers, location):
    response = client.post("/locations", json={"code": "a-01-03"}, headers=admin_headers)

    assert response.status_code == 409


# --- Update and list -------------------------------------------------------------


def test_admin_can_update_description_and_deactivate(client, admin_headers, location):
    response = client.patch(
        f"/locations/{location['id']}",
        json={"description": "Top shelf", "is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Top shelf"
    assert response.json()["is_active"] is False
    assert response.json()["code"] == "A-01-03"


def test_location_code_cannot_be_changed(client, admin_headers, location):
    response = client.patch(
        f"/locations/{location['id']}", json={"code": "B-01-01"}, headers=admin_headers
    )

    assert response.status_code == 422


def test_unknown_location_returns_404(client, admin_headers):
    assert client.get("/locations/9999", headers=admin_headers).status_code == 404


def test_list_locations_sorted_and_filtered(client, admin_headers):
    for code in ["C-01-01", "A-02-01", "B-01-01"]:
        client.post("/locations", json={"code": code}, headers=admin_headers)
    all_locations = client.get("/locations", headers=admin_headers).json()
    b = next(loc for loc in all_locations if loc["code"] == "B-01-01")
    client.patch(f"/locations/{b['id']}", json={"is_active": False}, headers=admin_headers)

    codes = [loc["code"] for loc in client.get("/locations", headers=admin_headers).json()]
    active = client.get("/locations", params={"active": True}, headers=admin_headers).json()

    assert codes == ["A-02-01", "B-01-01", "C-01-01"]
    assert [loc["code"] for loc in active] == ["A-02-01", "C-01-01"]
