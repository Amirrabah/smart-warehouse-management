from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Location, User, UserRole
from app.schemas.location import LocationCreate, LocationOut, LocationUpdate

router = APIRouter(prefix="/locations", tags=["locations"])

DbSession = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def get_location_or_404(db: Session, location_id: int) -> Location:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.get("", response_model=list[LocationOut])
def list_locations(_: AnyUser, db: DbSession, active: bool | None = None):
    query = select(Location).order_by(Location.code)
    if active is not None:
        query = query.where(Location.is_active == active)
    return db.scalars(query).all()


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(data: LocationCreate, _: AdminUser, db: DbSession):
    location = Location(**data.model_dump())
    db.add(location)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Location code already exists"
        ) from None
    db.refresh(location)
    return location


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: int, _: AnyUser, db: DbSession):
    return get_location_or_404(db, location_id)


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(location_id: int, data: LocationUpdate, _: AdminUser, db: DbSession):
    location = get_location_or_404(db, location_id)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(location, field, value)
    db.commit()
    db.refresh(location)
    return location
