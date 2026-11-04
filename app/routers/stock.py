from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.pagination import Page, Paging
from app.schemas.stock import StockSummary
from app.services.overview import stock_summaries

router = APIRouter(prefix="/stock", tags=["stock"])

DbSession = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=Page[StockSummary])
def list_stock(
    _: AnyUser,
    db: DbSession,
    paging: Paging,
    search: str | None = None,
    below_reorder: bool | None = None,
):
    items, total = stock_summaries(db, paging, search=search, below_reorder=below_reorder)
    return Page(items=items, total=total)
