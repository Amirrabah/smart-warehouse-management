from datetime import UTC, datetime, timedelta

import pytest

from app.models import Notification, UserRole


@pytest.fixture
def inbox(db, make_user, auth_header):
    """The planner has 3 notifications (one already read), the admin has 1."""
    planner = make_user(role=UserRole.PLANNER, email="planner@test.local")
    admin = make_user(role=UserRole.ADMIN, email="admin@test.local")
    start = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    rows = {
        "old_read": Notification(
            user_id=planner.id,
            title="Low stock: 1 product",
            body="CAB-001 Cable: 1 left (reorder point 5)",
            created_at=start,
            read_at=start + timedelta(hours=7),
        ),
        "middle": Notification(
            user_id=planner.id,
            title="Low stock: 2 products",
            body="...",
            created_at=start + timedelta(days=1),
        ),
        "newest": Notification(
            user_id=planner.id,
            title="Low stock: 3 products",
            body="...",
            created_at=start + timedelta(days=2),
        ),
        "admins": Notification(
            user_id=admin.id, title="Low stock: 1 product", body="...", created_at=start
        ),
    }
    for key in ["newest", "old_read", "middle", "admins"]:  # ids do NOT follow created_at
        db.add(rows[key])
        db.flush()
    db.commit()
    return {
        "planner": auth_header(planner),
        "admin": auth_header(admin),
        **{key: row.id for key, row in rows.items()},
    }


def ids(response):
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


# --- access -----------------------------------------------------------------------


def test_notifications_require_login(client):
    assert client.get("/notifications").status_code == 401
    assert client.post("/notifications/1/read").status_code == 401


def test_workers_have_no_notifications(client, make_user, auth_header, inbox):
    worker = auth_header(make_user(role=UserRole.WORKER, email="worker@test.local"))

    assert client.get("/notifications", headers=worker).status_code == 403
    assert client.post(f"/notifications/{inbox['newest']}/read", headers=worker).status_code == 403


# --- GET /notifications -----------------------------------------------------------


def test_list_shows_only_my_notifications_newest_first(client, inbox):
    response = client.get("/notifications", headers=inbox["planner"])

    assert ids(response) == [inbox["newest"], inbox["middle"], inbox["old_read"]]
    assert response.json()["total"] == 3


def test_admin_sees_only_their_own(client, inbox):
    assert ids(client.get("/notifications", headers=inbox["admin"])) == [inbox["admins"]]


def test_filter_unread(client, inbox):
    response = client.get("/notifications", params={"unread": True}, headers=inbox["planner"])

    assert ids(response) == [inbox["newest"], inbox["middle"]]


def test_filter_read(client, inbox):
    response = client.get("/notifications", params={"unread": False}, headers=inbox["planner"])

    assert ids(response) == [inbox["old_read"]]


def test_notification_fields(client, inbox):
    items = client.get("/notifications", headers=inbox["planner"]).json()["items"]
    item = items[-1]

    assert set(item) == {"id", "title", "body", "created_at", "read_at"}
    assert item["body"] == "CAB-001 Cable: 1 left (reorder point 5)"
    assert item["read_at"] is not None


def test_list_is_paginated(client, inbox):
    response = client.get("/notifications", params={"limit": 1}, headers=inbox["planner"])

    assert ids(response) == [inbox["newest"]]
    assert response.json()["total"] == 3


# --- POST /notifications/{id}/read ------------------------------------------------


def test_mark_as_read(client, inbox):
    response = client.post(f"/notifications/{inbox['newest']}/read", headers=inbox["planner"])

    assert response.status_code == 200
    assert response.json()["read_at"] is not None
    unread = client.get("/notifications", params={"unread": True}, headers=inbox["planner"])
    assert ids(unread) == [inbox["middle"]]


def test_marking_twice_keeps_the_first_read_time(client, inbox):
    url = f"/notifications/{inbox['old_read']}/read"

    response = client.post(url, headers=inbox["planner"])

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["read_at"]) == datetime(
        2026, 1, 1, 9, 0, tzinfo=UTC
    )


def test_someone_elses_notification_is_404_not_403(client, inbox):
    """403 would confirm that the id exists. 404 reveals nothing."""
    response = client.post(f"/notifications/{inbox['admins']}/read", headers=inbox["planner"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Notification not found"}


def test_unknown_notification_is_404(client, inbox):
    response = client.post("/notifications/9999/read", headers=inbox["planner"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Notification not found"}
