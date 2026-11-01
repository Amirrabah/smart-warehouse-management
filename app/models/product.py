import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductUnit(enum.StrEnum):
    PCS = "pcs"
    BOX = "box"
    KG = "kg"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("reorder_point >= 0", name="ck_products_reorder_point_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[ProductUnit] = mapped_column(
        Enum(
            ProductUnit,
            native_enum=False,
            create_constraint=True,
            length=10,
            values_callable=lambda units: [unit.value for unit in units],
        )
    )
    reorder_point: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    low_stock_alerted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
