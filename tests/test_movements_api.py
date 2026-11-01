import pytest

from app.models import Location, Product, ProductUnit, UserRole


@pytest.fixture
def world(db, make_user, auth_header):
    product = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([product, a, b])
    db.commit()
    worker = make_user(role=UserRole.WORKER, email="worker@test.local")
    return {
        "product": product.id,
        "a": a.id,
        "b": b.id,
        "worker": worker,
        "headers": auth_header(worker),
    }


def receive(client, world, quantity=100, location="a"):
    return client.post(
        "/movements/receive",
        json={
            "product_id": world["product"],
            "to_location_id": world[location],
            "quantity": quantity,
        },
        headers=world["headers"],
    )


def body(world, operation):
    p, a, b = world["product"], world["a"], world["b"]
    return {
        "receive": {"product_id": p, "to_location_id": a, "quantity": 1},
        "pick": {"product_id": p, "from_location_id": a, "quantity": 1},
        "move": {"product_id": p, "from_location_id": a, "to_location_id": b, "quantity": 1},
        "adjust": {"product_id": p, "location_id": a, "quantity_change": 1, "reason": "Count"},
    }[operation]


OPERATIONS = ["receive", "pick", "move", "adjust"]


# --- permissions ------------------------------------------------------------------


@pytest.mark.parametrize("operation", OPERATIONS)
def test_planner_cannot_change_stock(client, make_user, auth_header, world, operation):
    planner = make_user(role=UserRole.PLANNER, email="planner@test.local")

    response = client.post(
        f"/movements/{operation}", json=body(world, operation), headers=auth_header(planner)
    )

    assert response.status_code == 403


@pytest.mark.parametrize("operation", OPERATIONS)
def test_stock_changes_require_login(client, world, operation):
    response = client.post(f"/movements/{operation}", json=body(world, operation))

    assert response.status_code == 401


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.WORKER])
def test_admin_and_worker_can_receive(client, make_user, auth_header, world, role):
    user = make_user(role=role, email=f"{role.value}-2@test.local")

    response = client.post(
        "/movements/receive", json=body(world, "receive"), headers=auth_header(user)
    )

    assert response.status_code == 201
    assert response.json()["movement"]["user_id"] == user.id


# --- happy path -------------------------------------------------------------------


def test_receive_returns_movement_and_new_stock(client, world):
    response = receive(client, world, quantity=200)

    assert response.status_code == 201
    data = response.json()
    assert data["movement"]["type"] == "receive"
    assert data["movement"]["to_location_id"] == world["a"]
    assert data["movement"]["quantity"] == 200
    assert data["inventory"] == [{"location_id": world["a"], "quantity": 200}]


def test_full_flow_receive_pick_move_adjust(client, world):
    h, p, a, b = world["headers"], world["product"], world["a"], world["b"]
    receive(client, world, quantity=200)

    pick = client.post(
        "/movements/pick",
        json={"product_id": p, "from_location_id": a, "quantity": 5},
        headers=h,
    )
    move = client.post(
        "/movements/move",
        json={"product_id": p, "from_location_id": a, "to_location_id": b, "quantity": 40},
        headers=h,
    )
    adjust = client.post(
        "/movements/adjust",
        json={"product_id": p, "location_id": a, "quantity_change": -2, "reason": "Recount"},
        headers=h,
    )

    assert pick.json()["inventory"] == [{"location_id": a, "quantity": 195}]
    assert move.json()["inventory"] == [
        {"location_id": a, "quantity": 155},
        {"location_id": b, "quantity": 40},
    ]
    assert adjust.json()["inventory"] == [{"location_id": a, "quantity": 153}]
    assert adjust.json()["movement"]["from_location_id"] == a
    assert adjust.json()["movement"]["quantity"] == 2


# --- conflicts and not found ------------------------------------------------------


def test_pick_more_than_available_returns_409(client, world):
    receive(client, world, quantity=3)

    response = client.post(
        "/movements/pick",
        json={"product_id": world["product"], "from_location_id": world["a"], "quantity": 5},
        headers=world["headers"],
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Insufficient stock: 3 available, 5 requested"


def test_pick_with_no_stock_returns_409(client, world):
    response = client.post("/movements/pick", json=body(world, "pick"), headers=world["headers"])

    assert response.status_code == 409


def test_inactive_product_returns_409(client, world, db):
    db.get(Product, world["product"]).is_active = False
    db.commit()

    response = receive(client, world)

    assert response.status_code == 409
    assert response.json()["detail"] == "Product is inactive"


def test_unknown_product_returns_404(client, world):
    response = client.post(
        "/movements/receive",
        json={"product_id": 9999, "to_location_id": world["a"], "quantity": 1},
        headers=world["headers"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


# --- validation (422) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "change"),
    [
        ("receive", {"quantity": 0}),
        ("pick", {"quantity": -1}),
        ("move", {"to_location_id": None}),
        ("adjust", {"quantity_change": 0}),
        ("adjust", {"reason": "   "}),
        ("receive", {"from_location_id": 1}),
    ],
)
def test_invalid_input_returns_422(client, world, operation, change):
    data = {**body(world, operation), **change}
    if change == {"to_location_id": None}:
        data["to_location_id"] = world["a"]

    response = client.post(f"/movements/{operation}", json=data, headers=world["headers"])

    assert response.status_code == 422


def test_adjust_without_reason_returns_422(client, world):
    data = body(world, "adjust")
    del data["reason"]

    response = client.post("/movements/adjust", json=data, headers=world["headers"])

    assert response.status_code == 422


# --- location deactivation (from Phase 2) ------------------------------------------


@pytest.fixture
def admin_headers(make_user, auth_header):
    return auth_header(make_user(role=UserRole.ADMIN, email="admin@test.local"))


def test_location_with_stock_cannot_be_deactivated(client, world, admin_headers):
    receive(client, world, quantity=5)

    response = client.patch(
        f"/locations/{world['a']}", json={"is_active": False}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Location still holds stock"


def test_emptied_location_can_be_deactivated(client, world, admin_headers):
    assert receive(client, world, quantity=5).status_code == 201
    emptied = client.post(
        "/movements/pick",
        json={"product_id": world["product"], "from_location_id": world["a"], "quantity": 5},
        headers=world["headers"],
    )
    assert emptied.json()["inventory"] == [{"location_id": world["a"], "quantity": 0}]

    response = client.patch(
        f"/locations/{world['a']}", json={"is_active": False}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
