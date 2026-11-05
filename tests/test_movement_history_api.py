from datetime import UTC, datetime

import pytest

from app.models import Location, MovementType, Product, ProductUnit, StockMovement, UserRole


def at(day, hour):
    return datetime(2026, 1, day, hour, 0, tzinfo=UTC)


@pytest.fixture
def history(db, make_user, auth_header):
    """Five movements over three days, by two users. m4 and m5 have the same timestamp."""
    worker = make_user(role=UserRole.WORKER, email="worker@test.local")
    admin = make_user(role=UserRole.ADMIN, email="admin@test.local")
    cable = Product(sku="CAB-001", name="Cable", unit=ProductUnit.PCS)
    drill = Product(sku="DRL-001", name="Drill", unit=ProductUnit.PCS)
    a = Location(code="A-01-01")
    b = Location(code="B-01-01")
    db.add_all([cable, drill, a, b])
    db.flush()

    def movement(type_, product, user, created_at, quantity, source=None, target=None, reason=None):
        return StockMovement(
            type=type_,
            product_id=product.id,
            from_location_id=source.id if source else None,
            to_location_id=target.id if target else None,
            quantity=quantity,
            reason=reason,
            user_id=user.id,
            created_at=created_at,
        )

    movements = [
        movement(MovementType.RECEIVE, cable, worker, at(1, 10), 10, target=a),
        movement(MovementType.RECEIVE, drill, admin, at(2, 9), 5, target=b),
        movement(MovementType.MOVE, cable, worker, at(2, 15), 3, source=a, target=b),
        movement(MovementType.PICK, cable, worker, at(3, 8), 1, source=b),
        movement(MovementType.ADJUST, drill, admin, at(3, 8), 1, source=b, reason="Broken"),
    ]
    for item in movements:  # one by one, so the ids are 1..5 in this order
        db.add(item)
        db.flush()
    db.commit()
    return {
        "headers": auth_header(worker),
        "m": {number: item.id for number, item in enumerate(movements, start=1)},
        "worker": worker.id,
        "admin": admin.id,
        "cable": cable.id,
        "drill": drill.id,
        "a": a.id,
        "b": b.id,
    }


def get_history(client, world, **params):
    response = client.get("/movements", params=params, headers=world["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def numbers(world, page):
    """Translate movement ids back to m1..m5 so failures are easy to read."""
    by_id = {movement_id: number for number, movement_id in world["m"].items()}
    return [by_id[item["id"]] for item in page["items"]]


# --- access -----------------------------------------------------------------------


def test_history_requires_login(client):
    assert client.get("/movements").status_code == 401


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.WORKER, UserRole.PLANNER])
def test_every_role_can_view_history(client, make_user, auth_header, role):
    user = make_user(role=role, email=f"{role.value}-viewer@test.local")
    assert client.get("/movements", headers=auth_header(user)).status_code == 200


# --- order and content ------------------------------------------------------------


def test_newest_first_and_same_time_by_highest_id(client, history):
    page = get_history(client, history)

    assert numbers(history, page) == [5, 4, 3, 2, 1]
    assert page["total"] == 5


def test_history_item_has_all_fields(client, history):
    page = get_history(client, history, type="move")

    item = page["items"][0]
    # compare as datetimes: "15:00+00:00" and "16:00+01:00" are the same moment
    assert datetime.fromisoformat(item.pop("created_at")) == at(2, 15)
    assert item == {
        "id": history["m"][3],
        "type": "move",
        "product_id": history["cable"],
        "from_location_id": history["a"],
        "to_location_id": history["b"],
        "quantity": 3,
        "reason": None,
        "user_id": history["worker"],
    }


# --- filters ----------------------------------------------------------------------


def test_filter_by_product(client, history):
    page = get_history(client, history, product_id=history["cable"])
    assert numbers(history, page) == [4, 3, 1]


def test_filter_by_location_matches_from_or_to(client, history):
    page = get_history(client, history, location_id=history["b"])
    assert numbers(history, page) == [5, 4, 3, 2]


def test_filter_by_type(client, history):
    assert numbers(history, get_history(client, history, type="move")) == [3]


def test_filter_by_user(client, history):
    page = get_history(client, history, user_id=history["admin"])
    assert numbers(history, page) == [5, 2]


def test_date_range_includes_whole_days(client, history):
    page = get_history(client, history, date_from="2026-01-02", date_to="2026-01-02")
    assert numbers(history, page) == [3, 2]


def test_date_from_alone(client, history):
    assert numbers(history, get_history(client, history, date_from="2026-01-03")) == [5, 4]


def test_date_to_alone(client, history):
    assert numbers(history, get_history(client, history, date_to="2026-01-01")) == [1]


def test_filters_combine(client, history):
    page = get_history(client, history, product_id=history["cable"], type="pick")
    assert numbers(history, page) == [4]


# --- pagination -------------------------------------------------------------------


def test_pagination_with_total(client, history):
    page = get_history(client, history, limit=2, offset=1)

    assert numbers(history, page) == [4, 3]
    assert page["total"] == 5


def test_total_respects_filters(client, history):
    assert get_history(client, history, product_id=history["cable"], limit=1)["total"] == 3


@pytest.mark.parametrize(
    "params",
    [
        {"type": "steal"},
        {"date_from": "not-a-date"},
        {"date_from": "2026-01-03", "date_to": "2026-01-01"},
        {"limit": 0},
        {"limit": 201},
    ],
)
def test_invalid_query_is_rejected(client, history, params):
    response = client.get("/movements", params=params, headers=history["headers"])
    assert response.status_code == 422


# --- GET /movements/{id} ----------------------------------------------------------


def test_get_one_movement(client, history):
    response = client.get(f"/movements/{history['m'][5]}", headers=history["headers"])

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "adjust"
    assert data["reason"] == "Broken"


def test_get_one_movement_requires_login(client, history):
    assert client.get(f"/movements/{history['m'][1]}").status_code == 401


def test_unknown_movement_is_404(client, history):
    response = client.get("/movements/9999", headers=history["headers"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Movement not found"}
