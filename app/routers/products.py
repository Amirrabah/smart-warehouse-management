from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Product, User, UserRole
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    ReorderPointUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])

DbSession = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrPlanner = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.PLANNER))]


def get_product_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("", response_model=list[ProductOut])
def list_products(
    _: AnyUser,
    db: DbSession,
    search: str | None = None,
    active: bool | None = None,
):
    query = select(Product).order_by(Product.sku)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)))
    if active is not None:
        query = query.where(Product.is_active == active)
    return db.scalars(query).all()


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, _: AdminUser, db: DbSession):
    product = Product(**data.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="SKU already exists"
        ) from None
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, _: AnyUser, db: DbSession):
    return get_product_or_404(db, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, _: AdminUser, db: DbSession):
    product = get_product_or_404(db, product_id)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}/reorder-point", response_model=ProductOut)
def update_reorder_point(
    product_id: int, data: ReorderPointUpdate, _: AdminOrPlanner, db: DbSession
):
    product = get_product_or_404(db, product_id)
    product.reorder_point = data.reorder_point
    db.commit()
    db.refresh(product)
    return product
