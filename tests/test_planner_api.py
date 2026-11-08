from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Inventory,
    Location,
    MovementType,
    Product,
    ProductUnit,
    StockMovement,
    UserRole,
)


def days_ago(days):
    return datetime.now(UTC) - timedelta(days=days)


@pytest.fixture
def planner_world(db, make_user, auth_header):
    """Usage is counted from PICK movements in the last 30 days.

    cable: 30 in stock, picked 30 in the window (+100 long ago) -> 1.0 per day, 30.0 days left
    drill: 5 in stock, reorder 10, picked 60 in the window      -> 2.0 per day, 2.5 days left
    glue:  50 in stock, never picked                            -> no usage, days_left null
    tape:  10 in stock, only receive / move / adjust            -> those are not usage
    """
    worker = make_user(role=UserRole.WORKER, email="worker@test.local")
    cable = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS, reorder_point=10)
    drill = Product(sku="DRL-001", name="Drill", unit=ProductUnit.PCS, reorder_point=10)
    glue = Product(sku="GLU-001", name="Glue", unit=ProductUnit.BOX, reorder_point=5)
    tape = Product(sku="TAP-001", name="Tape", unit=ProductUnit.PCS, reorder_point=0)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([cable, drill, glue, tape, a, b])
    db.flush()

    db.add_all(
        [
            Inventory(product_id=cable.id, location_id=a.id, quantity=20),
            Inventory(product_id=cable.id, location_id=b.id, quantity=10),
            Inventory(product_id=drill.id, location_id=a.id, quantity=5),
            Inventory(product_id=glue.id, location_id=a.id, quantity=50),
            Inventory(product_id=tape.id, location_id=a.id, quantity=10),
        ]
    )

    def movement(type_, product, quantity, when, source=None, target=None, reason=None):
        return StockMovement(
            type=type_,
            product_id=product.id,
            from_location_id=source.id if source else None,
            to_location_id=target.id if target else None,
            quantity=quantity,
            reason=reason,
            user_id=worker.id,
            created_at=when,
        )

    db.add_all(
        [
            movement(MovementType.PICK, cable, 10, days_ago(2), source=a),
            movement(MovementType.PICK, cable, 20, days_ago(10), source=b),
            movement(MovementType.PICK, cable, 100, days_ago(40), source=a),  # outside window
            movement(MovementType.PICK, drill, 60, days_ago(5), source=a),
            movement(MovementType.RECEIVE, tape, 100, days_ago(3), target=a),
            movement(MovementType.MOVE, tape, 5, days_ago(3), source=a, target=b),
            movement(MovementType.ADJUST, tape, 3, days_ago(3), source=a, reason="Broken"),
        ]
    )
    db.commit()
    return {"headers": auth_header(worker), "drill": drill.id}


def get_planner(client, world, **params):
    response = client.get("/planner", params=params, headers=world["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def row(page, sku):
    return next(item for item in page["items"] if item["sku"] == sku)


def skus(page):
    return [item["sku"] for item in page["items"]]


# --- access -----------------------------------------------------------------------


def test_planner_requires_login(client):
    assert client.get("/planner").status_code == 401


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.WORKER, UserRole.PLANNER])
def test_every_role_can_view_planner(client, make_user, auth_header, role):
    user = make_user(role=role, email=f"{role.value}-viewer@test.local")
    assert client.get("/planner", headers=auth_header(user)).status_code == 200


# --- the numbers ------------------------------------------------------------------


def test_usage_and_days_left_for_one_product(client, planner_world):
    cable = row(get_planner(client, planner_world), "CAB-001")

    assert cable["total"] == 30
    assert cable["used_last_30_days"] == 30  # the pick 40 days ago is ignored
    assert cable["avg_daily_usage"] == 1.0
    assert cable["days_left"] == 30.0
    assert cable["below_reorder"] is False


def test_low_product_runs_out_soon(client, planner_world):
    drill = row(get_planner(client, planner_world), "DRL-001")

    assert drill["avg_daily_usage"] == 2.0
    assert drill["days_left"] == 2.5
    assert drill["below_reorder"] is True


def test_product_never_picked_has_no_days_left(client, planner_world):
    glue = row(get_planner(client, planner_world), "GLU-001")

    assert glue["used_last_30_days"] == 0
    assert glue["avg_daily_usage"] == 0.0
    assert glue["days_left"] is None


def test_only_picks_count_as_usage(client, planner_world):
    tape = row(get_planner(client, planner_world), "TAP-001")

    assert tape["used_last_30_days"] == 0
    assert tape["days_left"] is None


def test_inactive_products_are_not_planned(client, db, planner_world):
    db.get(Product, planner_world["drill"]).is_active = False
    db.commit()

    assert "DRL-001" not in skus(get_planner(client, planner_world))


# --- sorting, filter, pagination --------------------------------------------------


def test_default_sort_is_days_left_with_no_usage_last(client, planner_world):
    assert skus(get_planner(client, planner_world)) == ["DRL-001", "CAB-001", "GLU-001", "TAP-001"]


def test_sort_by_sku(client, planner_world):
    page = get_planner(client, planner_world, sort="sku")
    assert skus(page) == ["CAB-001", "DRL-001", "GLU-001", "TAP-001"]


def test_only_below_reorder(client, planner_world):
    page = get_planner(client, planner_world, only_below=True)

    assert skus(page) == ["DRL-001"]
    assert page["total"] == 1


def test_pagination_keeps_the_sort_order(client, planner_world):
    page = get_planner(client, planner_world, limit=2, offset=1)

    assert skus(page) == ["CAB-001", "GLU-001"]
    assert page["total"] == 4


@pytest.mark.parametrize("params", [{"sort": "name"}, {"limit": 0}, {"only_below": "maybe"}])
def test_invalid_query_is_rejected(client, planner_world, params):
    response = client.get("/planner", params=params, headers=planner_world["headers"])
    assert response.status_code == 422
