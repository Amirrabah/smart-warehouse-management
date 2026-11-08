from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Notification
from app.pagination import PageParams
from app.services.movements import NotFound


def my_notifications(
    db: Session, user_id: int, paging: PageParams, unread: bool | None = None
) -> tuple[list[Notification], int]:
    """The user's own notifications, newest first. unread=True/False filters on read_at."""
    query = select(Notification).where(Notification.user_id == user_id)
    if unread is True:
        query = query.where(Notification.read_at.is_(None))
    elif unread is False:
        query = query.where(Notification.read_at.is_not(None))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(paging.limit)
        .offset(paging.offset)
    ).all()
    return list(items), total


def mark_as_read(db: Session, user_id: int, notification_id: int) -> Notification:
    """Set read_at once. Someone else's notification is treated exactly like a missing one."""
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    if notification is None:
        raise NotFound("Notification not found")
    if notification.read_at is None:
        notification.read_at = func.now()
        db.commit()
        db.refresh(notification)
    return notification
