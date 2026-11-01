import pytest

from app.models import UserRole

CABLE = {"sku": "CAB-001", "name": "USB-C cable", "unit": "pcs", "reorder_point": 20}


@pytest.fixture
def admin_headers(make_user, auth_header):
    return auth_header(make_user(role=UserRole.ADMIN, email="admin@test.local"))


@pytest.fixture
def product(client, admin_headers):
    response = client.post("/products", json=CABLE, headers=admin_headers)
    assert response.status_code == 201
    return response.json()


# --- Permissions --------------------------------------------------------------


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.PLANNER])
def test_only_admin_can_create_products(client, make_user, auth_header, role):
    user = make_user(role=role)

    response = client.post("/products", json=CABLE, headers=auth_header(user))

    assert response.status_code == 403


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.PLANNER])
def test_only_admin_can_edit_products(client, make_user, auth_header, product, role):
    user = make_user(role=role)

    response = client.patch(
        f"/products/{product['id']}", json={"name": "Hacked"}, headers=auth_header(user)
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("role", "expected"),
    [(UserRole.ADMIN, 200), (UserRole.PLANNER, 200), (UserRole.WORKER, 403)],
)
def test_reorder_point_can_be_changed_by_admin_and_planner_only(
    client, make_user, auth_header, product, role, expected
):
    user = make_user(role=role, email=f"{role.value}-2@test.local")

    response = client.patch(
        f"/products/{product['id']}/reorder-point",
        json={"reorder_point": 50},
        headers=auth_header(user),
    )

    assert response.status_code == expected


@pytest.mark.parametrize("role", list(UserRole))
def test_all_roles_can_view_products(client, make_user, auth_header, product, role):
    headers = auth_header(make_user(role=role, email=f"{role.value}-view@test.local"))

    assert client.get("/products", headers=headers).status_code == 200
    assert client.get(f"/products/{product['id']}", headers=headers).status_code == 200


def test_products_require_login(client):
    assert client.get("/products").status_code == 401


# --- Create and validation -----------------------------------------------------


def test_create_product_normalises_sku_and_name(client, admin_headers):
    response = client.post(
        "/products",
        json={"sku": " cab-002 ", "name": "  Cable  ", "unit": "box"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "CAB-002"
    assert body["name"] == "Cable"
    assert body["reorder_point"] == 0
    assert body["is_active"] is True


def test_duplicate_sku_returns_409(client, admin_headers, product):
    duplicate = {**CABLE, "sku": "cab-001", "name": "Other"}

    response = client.post("/products", json=duplicate, headers=admin_headers)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "bad_field",
    [
        {"sku": "CAB 001"},
        {"sku": ""},
        {"name": "   "},
        {"unit": "litre"},
        {"reorder_point": -1},
    ],
)
def test_create_product_with_invalid_data_returns_422(client, admin_headers, bad_field):
    response = client.post("/products", json={**CABLE, **bad_field}, headers=admin_headers)

    assert response.status_code == 422


# --- Update -------------------------------------------------------------------


@pytest.mark.parametrize("locked_field", [{"sku": "NEW-SKU"}, {"unit": "box"}])
def test_sku_and_unit_cannot_be_changed(client, admin_headers, product, locked_field):
    response = client.patch(f"/products/{product['id']}", json=locked_field, headers=admin_headers)

    assert response.status_code == 422


def test_admin_can_rename_and_deactivate_product(client, admin_headers, product):
    response = client.patch(
        f"/products/{product['id']}",
        json={"name": "USB-C cable 2m", "is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "USB-C cable 2m"
    assert body["is_active"] is False
    assert body["sku"] == "CAB-001"


def test_reorder_point_cannot_be_negative(client, admin_headers, product):
    response = client.patch(
        f"/products/{product['id']}/reorder-point",
        json={"reorder_point": -5},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_reorder_point_endpoint_only_accepts_reorder_point(client, make_user, auth_header, product):
    planner = make_user(role=UserRole.PLANNER, email="p@test.local")

    response = client.patch(
        f"/products/{product['id']}/reorder-point",
        json={"reorder_point": 5, "name": "Planner rename"},
        headers=auth_header(planner),
    )

    assert response.status_code == 422


def test_unknown_product_returns_404(client, admin_headers):
    assert client.get("/products/9999", headers=admin_headers).status_code == 404
    assert (
        client.patch("/products/9999", json={"name": "X"}, headers=admin_headers).status_code == 404
    )


# --- List, search and filter ----------------------------------------------------


def test_search_matches_sku_or_name_case_insensitive(client, admin_headers):
    for sku, name in [("CAB-001", "USB-C cable"), ("BOX-010", "Shipping box"), ("TAPE-1", "Tape")]:
        client.post(
            "/products", json={"sku": sku, "name": name, "unit": "pcs"}, headers=admin_headers
        )

    by_name = client.get("/products", params={"search": "CABLE"}, headers=admin_headers).json()
    by_sku = client.get("/products", params={"search": "box-0"}, headers=admin_headers).json()

    assert [p["sku"] for p in by_name] == ["CAB-001"]
    assert [p["sku"] for p in by_sku] == ["BOX-010"]


def test_filter_by_active(client, admin_headers, product):
    client.post(
        "/products", json={"sku": "OLD-1", "name": "Old", "unit": "pcs"}, headers=admin_headers
    )
    old = client.get("/products", params={"search": "OLD"}, headers=admin_headers).json()[0]
    client.patch(f"/products/{old['id']}", json={"is_active": False}, headers=admin_headers)

    active = client.get("/products", params={"active": True}, headers=admin_headers).json()
    inactive = client.get("/products", params={"active": False}, headers=admin_headers).json()

    assert [p["sku"] for p in active] == ["CAB-001"]
    assert [p["sku"] for p in inactive] == ["OLD-1"]
