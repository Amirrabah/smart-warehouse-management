import pytest

from app.models import Inventory, Location, Product, ProductUnit, UserRole


@pytest.fixture
def stock_world(db, make_user, auth_header):
    """Three products: cable (stock in two places), drill (low), glue (no stock at all)."""
    cable = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS, reorder_point=10)
    drill = Product(sku="DRL-001", name="Drill", unit=ProductUnit.PCS, reorder_point=5)
    glue = Product(sku="GLU-001", name="Glue", unit=ProductUnit.BOX, reorder_point=0)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([cable, drill, glue, a, b])
    db.flush()
    db.add_all(
        [
            Inventory(product_id=cable.id, location_id=a.id, quantity=8),
            Inventory(product_id=cable.id, location_id=b.id, quantity=7),
            Inventory(product_id=drill.id, location_id=a.id, quantity=2),
        ]
    )
    db.commit()
    worker = make_user(role=UserRole.WORKER, email="worker@test.local")
    return {"headers": auth_header(worker), "cable": cable.id, "drill": drill.id}


def get_stock(client, world, **params):
    response = client.get("/stock", params=params, headers=world["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def skus(page):
    return [item["sku"] for item in page["items"]]


# --- access -----------------------------------------------------------------------


def test_stock_requires_login(client):
    assert client.get("/stock").status_code == 401


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.WORKER, UserRole.PLANNER])
def test_every_role_can_view_stock(client, make_user, auth_header, role):
    user = make_user(role=role, email=f"{role.value}@test.local")
    assert client.get("/stock", headers=auth_header(user)).status_code == 200


# --- content ----------------------------------------------------------------------


def test_total_is_the_sum_over_all_locations(client, stock_world):
    page = get_stock(client, stock_world)

    cable = next(item for item in page["items"] if item["sku"] == "CAB-001")
    assert cable == {
        "product_id": stock_world["cable"],
        "sku": "CAB-001",
        "name": "Cable",
        "unit": "pcs",
        "reorder_point": 10,
        "total": 15,
        "below_reorder": False,
    }


def test_product_without_any_stock_shows_zero(client, stock_world):
    page = get_stock(client, stock_world)

    glue = next(item for item in page["items"] if item["sku"] == "GLU-001")
    assert glue["total"] == 0
    assert glue["below_reorder"] is False  # 0 is not below a reorder point of 0


def test_below_reorder_is_true_when_total_is_under_the_reorder_point(client, stock_world):
    page = get_stock(client, stock_world)

    drill = next(item for item in page["items"] if item["sku"] == "DRL-001")
    assert drill["total"] == 2
    assert drill["below_reorder"] is True


def test_list_is_sorted_by_sku(client, stock_world):
    assert skus(get_stock(client, stock_world)) == ["CAB-001", "DRL-001", "GLU-001"]


def test_inactive_products_are_not_listed(client, db, stock_world):
    db.get(Product, stock_world["drill"]).is_active = False
    db.commit()

    assert skus(get_stock(client, stock_world)) == ["CAB-001", "GLU-001"]


# --- filters ----------------------------------------------------------------------


def test_filter_below_reorder_true(client, stock_world):
    assert skus(get_stock(client, stock_world, below_reorder=True)) == ["DRL-001"]


def test_filter_below_reorder_false(client, stock_world):
    assert skus(get_stock(client, stock_world, below_reorder=False)) == ["CAB-001", "GLU-001"]


@pytest.mark.parametrize("search", ["drl", "dril", " Drill "])
def test_search_matches_sku_or_name(client, stock_world, search):
    assert skus(get_stock(client, stock_world, search=search)) == ["DRL-001"]


# --- pagination -------------------------------------------------------------------


def test_total_counts_all_matches_not_just_the_page(client, stock_world):
    page = get_stock(client, stock_world, limit=2)

    assert skus(page) == ["CAB-001", "DRL-001"]
    assert page["total"] == 3


def test_offset_skips_items(client, stock_world):
    page = get_stock(client, stock_world, limit=2, offset=2)

    assert skus(page) == ["GLU-001"]
    assert page["total"] == 3


def test_total_respects_filters(client, stock_world):
    page = get_stock(client, stock_world, below_reorder=True)

    assert page["total"] == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"limit": "abc"}])
def test_invalid_pagination_is_rejected(client, stock_world, params):
    response = client.get("/stock", params=params, headers=stock_world["headers"])

    assert response.status_code == 422
