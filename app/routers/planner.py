from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.pagination import Page, Paging
from app.schemas.planner import PlannerRow
from app.services.planner import PlannerSort, planner_rows

router = APIRouter(prefix="/planner", tags=["planner"])

DbSession = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=Page[PlannerRow])
def get_planner(
    _: AnyUser,
    db: DbSession,
    paging: Paging,
    only_below: bool = False,
    sort: PlannerSort = "days_left",
):
    items, total = planner_rows(db, paging, only_below=only_below, sort=sort)
    return Page(items=items, total=total)
