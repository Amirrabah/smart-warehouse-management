from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import User, UserRole
from app.pagination import Page, Paging
from app.schemas.notification import NotificationOut
from app.services.notifications import mark_as_read, my_notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])

DbSession = Annotated[Session, Depends(get_db)]
InboxUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.PLANNER))]


@router.get("", response_model=Page[NotificationOut])
def list_notifications(user: InboxUser, db: DbSession, paging: Paging, unread: bool | None = None):
    items, total = my_notifications(db, user.id, paging, unread=unread)
    return Page(items=items, total=total)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_notification(notification_id: int, user: InboxUser, db: DbSession):
    return mark_as_read(db, user.id, notification_id)
