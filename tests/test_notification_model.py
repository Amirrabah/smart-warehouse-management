import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import DataError, IntegrityError

from app.models import Notification, UserRole


def save(db, notification):
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def assert_rejected(db, notification, error=IntegrityError):
    db.add(notification)
    with pytest.raises(error):
        db.commit()
    db.rollback()


def test_new_notification_is_unread_and_timestamped(db, make_user):
    user = make_user(role=UserRole.PLANNER)

    notification = save(db, Notification(user_id=user.id, title="Low stock", body="CAB-001: 2"))

    assert notification.id is not None
    assert notification.created_at is not None  # set by the database
    assert notification.read_at is None  # None = unread


def test_notification_needs_a_user(db):
    assert_rejected(db, Notification(title="Low stock", body="..."))


def test_notification_user_must_exist(db):
    assert_rejected(db, Notification(user_id=9999, title="Low stock", body="..."))


def test_notification_needs_title_and_body(db, make_user):
    user = make_user()

    assert_rejected(db, Notification(user_id=user.id, body="..."))
    assert_rejected(db, Notification(user_id=user.id, title="Low stock"))


def test_title_is_at_most_200_characters(db, make_user):
    user = make_user()

    assert_rejected(db, Notification(user_id=user.id, title="x" * 201, body="..."), DataError)


def test_unread_lookup_index_exists(test_engine):
    indexes = inspect(test_engine).get_indexes("notifications")

    assert {"name": "ix_notifications_user_read", "columns": ["user_id", "read_at"]} in [
        {"name": index["name"], "columns": index["column_names"]} for index in indexes
    ]
