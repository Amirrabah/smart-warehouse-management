import pytest

from app.models import Inventory, Location, Product, ProductUnit, UserRole


@pytest.fixture
def shelves(db, make_user, auth_header):
    """Cable on A (8) and B (7), drill on A (2), an empty row for cable on C, glue nowhere."""
    cable = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS, reorder_point=10)
    drill = Product(sku="DRL-001", name="Drill", unit=ProductUnit.PCS, reorder_point=5)
    glue = Product(sku="GLU-001", name="Glue", unit=ProductUnit.BOX)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    c = Location(code="C-01-01")
    db.add_all([cable, drill, glue, a, b, c])
    db.flush()
    db.add_all(
        [
            Inventory(product_id=cable.id, location_id=b.id, quantity=7),
            Inventory(product_id=cable.id, location_id=a.id, quantity=8),
            Inventory(product_id=cable.id, location_id=c.id, quantity=0),
            Inventory(product_id=drill.id, location_id=a.id, quantity=2),
        ]
    )
    db.commit()
    worker = make_user(role=UserRole.WORKER, email="worker@test.local")
    ids = {name: obj.id for name, obj in [("cable", cable), ("drill", drill), ("glue", glue)]}
    ids.update({"a": a.id, "b": b.id, "c": c.id})
    return {"headers": auth_header(worker), **ids}


def get_ok(client, world, url):
    response = client.get(url, headers=world["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# --- GET /stock/{product_id} ------------------------------------------------------


def test_product_stock_requires_login(client, shelves):
    assert client.get(f"/stock/{shelves['cable']}").status_code == 401


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.WORKER, UserRole.PLANNER])
def test_every_role_can_view_product_stock(client, make_user, auth_header, shelves, role):
    user = make_user(role=role, email=f"{role.value}-viewer@test.local")
    response = client.get(f"/stock/{shelves['cable']}", headers=auth_header(user))
    assert response.status_code == 200


def test_product_stock_shows_total_and_each_location(client, shelves):
    data = get_ok(client, shelves, f"/stock/{shelves['cable']}")

    assert data == {
        "product_id": shelves["cable"],
        "sku": "CAB-001",
        "name": "Cable",
        "unit": "pcs",
        "reorder_point": 10,
        "total": 15,
        "below_reorder": False,
        "locations": [
            {"location_id": shelves["a"], "code": "A-01-01", "quantity": 8},
            {"location_id": shelves["b"], "code": "B-01-01", "quantity": 7},
        ],
    }


def test_product_stock_is_below_reorder_when_low(client, shelves):
    data = get_ok(client, shelves, f"/stock/{shelves['drill']}")

    assert data["total"] == 2
    assert data["below_reorder"] is True


def test_product_without_stock_has_no_locations(client, shelves):
    data = get_ok(client, shelves, f"/stock/{shelves['glue']}")

    assert data["total"] == 0
    assert data["locations"] == []


def test_unknown_product_is_404(client, shelves):
    response = client.get("/stock/9999", headers=shelves["headers"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


# --- GET /locations/{id}/stock ----------------------------------------------------


def test_location_stock_requires_login(client, shelves):
    assert client.get(f"/locations/{shelves['a']}/stock").status_code == 401


def test_location_stock_lists_every_product_on_the_shelf(client, shelves):
    data = get_ok(client, shelves, f"/locations/{shelves['a']}/stock")

    assert data == [
        {
            "product_id": shelves["cable"],
            "sku": "CAB-001",
            "name": "Cable",
            "unit": "pcs",
            "quantity": 8,
        },
        {
            "product_id": shelves["drill"],
            "sku": "DRL-001",
            "name": "Drill",
            "unit": "pcs",
            "quantity": 2,
        },
    ]


def test_location_stock_hides_rows_with_zero_quantity(client, shelves):
    assert get_ok(client, shelves, f"/locations/{shelves['c']}/stock") == []


def test_unknown_location_is_404(client, shelves):
    response = client.get("/locations/9999/stock", headers=shelves["headers"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}
