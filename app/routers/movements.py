from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import User, UserRole
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
from app.services.movements import MovementResult

router = APIRouter(prefix="/movements", tags=["movements"])

DbSession = Annotated[Session, Depends(get_db)]
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
