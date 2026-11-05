from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import MovementType, User, UserRole
from app.pagination import Page, Paging
from app.schemas.movement import (
    AdjustRequest,
    InventoryLevel,
    MovementOut,
    MovementResponse,
    MoveRequest,
    PickRequest,
    ReceiveRequest,
)
from app.services import movements
from app.services.history import get_movement, movement_history
from app.services.movements import MovementResult

router = APIRouter(prefix="/movements", tags=["movements"])

DbSession = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(get_current_user)]
StockUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.WORKER))]


def _response(result: MovementResult) -> MovementResponse:
    return MovementResponse(
        movement=MovementOut.model_validate(result.movement),
        inventory=[
            InventoryLevel(location_id=location_id, quantity=quantity)
            for location_id, quantity in result.inventory.items()
        ],
    )


@router.post("/receive", response_model=MovementResponse, status_code=status.HTTP_201_CREATED)
def receive(data: ReceiveRequest, user: StockUser, db: DbSession):
    result = movements.receive(
        db, user, data.product_id, data.to_location_id, data.quantity, data.reason
    )
    return _response(result)


@router.post("/pick", response_model=MovementResponse, status_code=status.HTTP_201_CREATED)
def pick(data: PickRequest, user: StockUser, db: DbSession):
    result = movements.pick(
        db, user, data.product_id, data.from_location_id, data.quantity, data.reason
    )
    return _response(result)


@router.post("/move", response_model=MovementResponse, status_code=status.HTTP_201_CREATED)
def move(data: MoveRequest, user: StockUser, db: DbSession):
    result = movements.move(
        db,
        user,
        data.product_id,
        data.from_location_id,
        data.to_location_id,
        data.quantity,
        data.reason,
    )
    return _response(result)


@router.post("/adjust", response_model=MovementResponse, status_code=status.HTTP_201_CREATED)
def adjust(data: AdjustRequest, user: StockUser, db: DbSession):
    result = movements.adjust(
        db, user, data.product_id, data.location_id, data.quantity_change, data.reason
    )
    return _response(result)


@router.get("", response_model=Page[MovementOut])
def list_movements(
    _: AnyUser,
    db: DbSession,
    paging: Paging,
    product_id: int | None = None,
    location_id: int | None = None,
    movement_type: Annotated[MovementType | None, Query(alias="type")] = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from must not be after date_to",
        )
    items, total = movement_history(
        db,
        paging,
        product_id=product_id,
        location_id=location_id,
        type_=movement_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Page(items=items, total=total)


@router.get("/{movement_id}", response_model=MovementOut)
def get_one_movement(movement_id: int, _: AnyUser, db: DbSession):
    return get_movement(db, movement_id)
