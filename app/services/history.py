from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import MovementType, StockMovement
from app.pagination import PageParams
from app.services.movements import NotFound


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def movement_history(
    db: Session,
    paging: PageParams,
    product_id: int | None = None,
    location_id: int | None = None,
    type_: MovementType | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[StockMovement], int]:
    """Movements, newest first. Every filter is optional; dates are whole days in UTC."""
    query = select(StockMovement)
    if product_id is not None:
        query = query.where(StockMovement.product_id == product_id)
    if location_id is not None:
        query = query.where(
            or_(
                StockMovement.from_location_id == location_id,
                StockMovement.to_location_id == location_id,
            )
        )
    if type_ is not None:
        query = query.where(StockMovement.type == type_)
    if user_id is not None:
        query = query.where(StockMovement.user_id == user_id)
    if date_from is not None:
        query = query.where(StockMovement.created_at >= _start_of_day(date_from))
    if date_to is not None:
        # "up to and including date_to" = before the start of the next day
        query = query.where(StockMovement.created_at < _start_of_day(date_to + timedelta(days=1)))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(paging.limit)
        .offset(paging.offset)
    ).all()
    return list(items), total


def get_movement(db: Session, movement_id: int) -> StockMovement:
    movement = db.get(StockMovement, movement_id)
    if movement is None:
        raise NotFound("Movement not found")
    return movement
